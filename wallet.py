"""
Carteira de gastos — um banco SQLite por usuário em gastos/<user_id>.db
"""
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

GASTOS_DIR = Path("gastos")

CATEGORIAS = {
    "alimentacao": "🍔 Alimentação",
    "transporte":  "🚗 Transporte",
    "saude":       "🏥 Saúde",
    "lazer":       "🎮 Lazer",
    "moradia":     "🏠 Moradia",
    "outros":      "📦 Outros",
}

MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

_easyocr_reader = None


# ─── DB ──────────────────────────────────────────────────────────────────────

def _get_conn(user_id: int) -> sqlite3.Connection:
    GASTOS_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(GASTOS_DIR / f"{user_id}.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT    NOT NULL,
            valor     REAL    NOT NULL,
            descricao TEXT    DEFAULT '',
            data      TEXT    DEFAULT (date('now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS saldo (
            id    INTEGER PRIMARY KEY CHECK (id = 1),
            valor REAL    NOT NULL DEFAULT 0
        )
    """)
    conn.execute("INSERT OR IGNORE INTO saldo (id, valor) VALUES (1, 0)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lista_compras (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            nome       TEXT    NOT NULL,
            valor_unit REAL    NOT NULL,
            quantidade INTEGER NOT NULL DEFAULT 1,
            subtotal   REAL    NOT NULL
        )
    """)
    conn.commit()
    return conn


def _lancar(user_id: int, categoria: str, valor: float, descricao: str) -> int:
    with _get_conn(user_id) as conn:
        cur = conn.execute(
            "INSERT INTO gastos (categoria, valor, descricao) VALUES (?, ?, ?)",
            (categoria, valor, descricao),
        )
        return cur.lastrowid


def _listar(user_id: int, mes: int, ano: int) -> list:
    with _get_conn(user_id) as conn:
        return conn.execute(
            """SELECT id, categoria, valor, descricao, data
               FROM gastos
               WHERE strftime('%m', data) = ? AND strftime('%Y', data) = ?
               ORDER BY data DESC, id DESC
               LIMIT 20""",
            (f"{mes:02d}", str(ano)),
        ).fetchall()


def _resumo(user_id: int, mes: int, ano: int) -> list:
    with _get_conn(user_id) as conn:
        return conn.execute(
            """SELECT categoria, SUM(valor)
               FROM gastos
               WHERE strftime('%m', data) = ? AND strftime('%Y', data) = ?
               GROUP BY categoria
               ORDER BY SUM(valor) DESC""",
            (f"{mes:02d}", str(ano)),
        ).fetchall()


def _deletar(user_id: int, gasto_id: int) -> bool:
    with _get_conn(user_id) as conn:
        row = conn.execute("SELECT valor FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
        if not row:
            return False
        cur = conn.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
        if cur.rowcount > 0:
            conn.execute("UPDATE saldo SET valor = valor + ? WHERE id = 1", (row[0],))
            return True
        return False


# ─── Saldo ────────────────────────────────────────────────────────────────────

def _get_saldo(user_id: int) -> float:
    with _get_conn(user_id) as conn:
        row = conn.execute("SELECT valor FROM saldo WHERE id = 1").fetchone()
        return row[0] if row else 0.0


def _add_saldo(user_id: int, valor: float) -> float:
    with _get_conn(user_id) as conn:
        conn.execute("UPDATE saldo SET valor = valor + ? WHERE id = 1", (valor,))
        row = conn.execute("SELECT valor FROM saldo WHERE id = 1").fetchone()
        return row[0]


def _deduct_saldo(user_id: int, valor: float) -> float:
    with _get_conn(user_id) as conn:
        conn.execute("UPDATE saldo SET valor = valor - ? WHERE id = 1", (valor,))
        row = conn.execute("SELECT valor FROM saldo WHERE id = 1").fetchone()
        return row[0]


# ─── Lista de compras ─────────────────────────────────────────────────────────

def _lista_add(user_id: int, nome: str, valor_unit: float, quantidade: int) -> int:
    subtotal = round(valor_unit * quantidade, 2)
    with _get_conn(user_id) as conn:
        cur = conn.execute(
            "INSERT INTO lista_compras (nome, valor_unit, quantidade, subtotal) VALUES (?, ?, ?, ?)",
            (nome, valor_unit, quantidade, subtotal),
        )
        return cur.lastrowid


def _lista_get(user_id: int) -> list:
    with _get_conn(user_id) as conn:
        return conn.execute(
            "SELECT id, nome, valor_unit, quantidade, subtotal FROM lista_compras ORDER BY id"
        ).fetchall()


def _lista_remove(user_id: int, item_id: int) -> bool:
    with _get_conn(user_id) as conn:
        cur = conn.execute("DELETE FROM lista_compras WHERE id = ?", (item_id,))
        return cur.rowcount > 0


def _lista_clear(user_id: int) -> None:
    with _get_conn(user_id) as conn:
        conn.execute("DELETE FROM lista_compras")


def _lista_total(items: list) -> float:
    return round(sum(row[4] for row in items), 2)


# ─── OCR ─────────────────────────────────────────────────────────────────────

def _get_ocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(['pt', 'en'], gpu=False, verbose=False)
    return _easyocr_reader


async def _ocr_from_photo(photo_file) -> str:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp_path = tmp.name
        await photo_file.download_to_drive(tmp_path)
        reader = _get_ocr_reader()
        results = reader.readtext(tmp_path)
        texts = [text for _, text, conf in results if conf > 0.3]
        return ' '.join(texts)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _parse_item_text(text: str) -> tuple:
    """Extrai (nome, valor) de 'feijão 13' ou 'arroz R$ 8,50'."""
    text = text.strip()
    match = re.search(r'R?\$?\s*(\d+(?:[.,]\d{1,2})?)', text)
    if not match:
        return None, None
    try:
        valor = float(match.group(1).replace(',', '.'))
        if valor <= 0:
            raise ValueError
    except ValueError:
        return None, None
    nome = re.sub(r'R?\$?\s*\d+(?:[.,]\d{1,2})?', '', text).strip()
    nome = re.sub(r'\s+', ' ', nome).strip()
    return (nome or None), valor


# ─── Visual helpers ───────────────────────────────────────────────────────────

def _mes_nome(mes: int, ano: int) -> str:
    return f"{MESES_PT[mes]}/{ano}"


def _barra(pct: float, largura: int = 10) -> str:
    preenchido = round(pct / 100 * largura)
    return "█" * preenchido + "░" * (largura - preenchido)


def _fmt(v: float) -> str:
    """Formata valor em reais no padrão brasileiro: R$ 1.234,56"""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _esc(text: str) -> str:
    """Escapa caracteres especiais do Markdown v1."""
    for ch in ("*", "_", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


# ─── Teclados ─────────────────────────────────────────────────────────────────

def _kbd_wallet() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Lançar Gasto", callback_data="wallet_lancar"),
            InlineKeyboardButton("💳 Saldo",        callback_data="wallet_saldo"),
        ],
        [InlineKeyboardButton("🛒 Lista de Compras", callback_data="wallet_lista")],
        [
            InlineKeyboardButton("📋 Ver Gastos",    callback_data="wallet_ver"),
            InlineKeyboardButton("📊 Resumo do Mês", callback_data="wallet_resumo"),
        ],
        [InlineKeyboardButton("◀️ Voltar", callback_data="voltar")],
    ])


def _kbd_categorias() -> InlineKeyboardMarkup:
    items = list(CATEGORIAS.items())
    rows = [
        [InlineKeyboardButton(label, callback_data=f"wallet_cat_{key}")
         for key, label in items[i:i + 2]]
        for i in range(0, len(items), 2)
    ]
    rows.append([InlineKeyboardButton("❌ Cancelar", callback_data="carteira")])
    return InlineKeyboardMarkup(rows)


def _back_kbd() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Voltar", callback_data="carteira")]])


def _kbd_saldo() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar Saldo", callback_data="wallet_saldo_add")],
        [InlineKeyboardButton("◀️ Voltar",          callback_data="carteira")],
    ])


def _kbd_lista_vazia() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Texto", callback_data="wallet_lista_add_texto"),
            InlineKeyboardButton("📷 Foto",  callback_data="wallet_lista_add_foto"),
        ],
        [InlineKeyboardButton("◀️ Voltar", callback_data="carteira")],
    ])


def _kbd_lista_com_itens() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Texto", callback_data="wallet_lista_add_texto"),
            InlineKeyboardButton("📷 Foto",  callback_data="wallet_lista_add_foto"),
        ],
        [
            InlineKeyboardButton("🗑️ Remover item", callback_data="wallet_lista_remover"),
            InlineKeyboardButton("✅ Finalizar",     callback_data="wallet_lista_finalizar"),
        ],
        [InlineKeyboardButton("◀️ Voltar", callback_data="carteira")],
    ])


def _kbd_lista_mais() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Mais itens", callback_data="wallet_lista"),
            InlineKeyboardButton("✅ Finalizar",  callback_data="wallet_lista_finalizar"),
        ],
    ])


def _kbd_confirmar_ocr() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="wallet_lista_confirma"),
            InlineKeyboardButton("✏️ Corrigir",  callback_data="wallet_lista_corrige"),
        ],
        [InlineKeyboardButton("❌ Cancelar", callback_data="wallet_lista")],
    ])


def _kbd_abater() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Sim, abater", callback_data="wallet_lista_abater_sim"),
            InlineKeyboardButton("❌ Não",         callback_data="wallet_lista_abater_nao"),
        ],
    ])


def _kbd_pos_abater() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💾 Salvar no histórico", callback_data="wallet_lista_salvar"),
            InlineKeyboardButton("🗑️ Apagar lista",        callback_data="wallet_lista_apagar"),
        ],
    ])


# ─── Renderers ────────────────────────────────────────────────────────────────

def _render_gastos(rows: list, mes: int, ano: int) -> tuple:
    """Retorna (text, InlineKeyboardMarkup) para a lista de gastos do mês."""
    nome = _mes_nome(mes, ano)
    linhas = [f"📋 *Gastos de {nome}*", "━━━━━━━━━━━━━━━━━━", ""]
    kbd_rows = []
    total = 0.0

    for row_id, cat, valor, desc, data_str in rows:
        emoji = CATEGORIAS.get(cat, "📦 Outros").split()[0]
        cat_nome = CATEGORIAS.get(cat, cat).split(" ", 1)[1]
        dia = data_str[8:10] + "/" + data_str[5:7]
        desc_txt = f" · _{_esc(desc)}_" if desc else ""
        linhas.append(f"{emoji} *{_fmt(valor)}* · {cat_nome}{desc_txt} · {dia}")
        kbd_rows.append([InlineKeyboardButton(
            f"🗑️ #{row_id} {cat_nome} {_fmt(valor)}",
            callback_data=f"wallet_del_{row_id}",
        )])
        total += valor

    linhas += ["", f"💰 *Total: {_fmt(total)}*"]
    kbd_rows.append([InlineKeyboardButton("◀️ Voltar", callback_data="carteira")])
    return "\n".join(linhas), InlineKeyboardMarkup(kbd_rows)


def _render_resumo(rows: list, mes: int, ano: int) -> str:
    """Retorna texto do resumo mensal com gráfico de barras."""
    nome = _mes_nome(mes, ano)
    total = sum(v for _, v in rows)
    linhas = [f"📊 *Resumo de {nome}*", "━━━━━━━━━━━━━━━━━━", ""]

    for cat, soma in rows:
        label = CATEGORIAS.get(cat, cat)
        pct = (soma / total * 100) if total else 0
        barra = _barra(pct)
        linhas.append(f"{label}")
        linhas.append(f"`{barra}` {pct:.0f}% — {_fmt(soma)}")
        linhas.append("")

    linhas.append(f"💰 *Total: {_fmt(total)}*")
    return "\n".join(linhas)


def _render_lista(items: list, titulo: str = "🛒 *Lista de Compras*") -> str:
    total = _lista_total(items)
    linhas = [titulo, "━━━━━━━━━━━━━━━━━━", ""]
    for _, nome, valor_unit, qtd, subtotal in items:
        if qtd > 1:
            linhas.append(
                f"• *{_esc(nome)}* x{qtd} ({_fmt(valor_unit)} un.) = *{_fmt(subtotal)}*"
            )
        else:
            linhas.append(f"• *{_esc(nome)}* — *{_fmt(subtotal)}*")
    linhas += ["", f"💰 *Total: {_fmt(total)}*"]
    return "\n".join(linhas)


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def show_wallet_menu(query) -> None:
    user_id = query.from_user.id
    now = datetime.now()
    saldo = _get_saldo(user_id)
    rows = _resumo(user_id, now.month, now.year)
    gasto_mes = sum(v for _, v in rows)
    disponivel = saldo - gasto_mes

    text = (
        "💰 *Carteira de Gastos*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 Saldo: *{_fmt(saldo)}*\n"
        f"📉 Gasto em {MESES_PT[now.month]}: *{_fmt(gasto_mes)}*\n"
        f"✅ Disponível: *{_fmt(disponivel)}*"
    )
    await query.edit_message_text(text, reply_markup=_kbd_wallet(), parse_mode="Markdown")


async def handle_wallet_callback(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = query.data
    user_id = query.from_user.id

    if data == "carteira":
        await show_wallet_menu(query)

    elif data == "wallet_lancar":
        await query.edit_message_text(
            "📂 *Selecione a categoria:*",
            reply_markup=_kbd_categorias(),
            parse_mode="Markdown",
        )

    elif data.startswith("wallet_cat_"):
        cat_key = data[len("wallet_cat_"):]
        if cat_key not in CATEGORIAS:
            await query.answer("Categoria inválida.")
            return
        context.user_data["wallet_categoria"] = cat_key
        context.user_data["awaiting_command"] = "wallet_valor"
        await query.edit_message_text(
            f"Categoria: {CATEGORIAS[cat_key]}\n\n💵 *Digite o valor:*\n_(ex: 29.90 ou 29,90)_",
            parse_mode="Markdown",
        )

    elif data == "wallet_ver":
        now = datetime.now()
        rows = _listar(user_id, now.month, now.year)
        if not rows:
            await query.edit_message_text(
                f"📋 Nenhum gasto em {_mes_nome(now.month, now.year)}.",
                reply_markup=_back_kbd(),
            )
            return
        text, kbd = _render_gastos(rows, now.month, now.year)
        await query.edit_message_text(text, reply_markup=kbd, parse_mode="Markdown")

    elif data == "wallet_resumo":
        now = datetime.now()
        rows = _resumo(user_id, now.month, now.year)
        if not rows:
            await query.edit_message_text(
                f"📊 Nenhum gasto em {_mes_nome(now.month, now.year)}.",
                reply_markup=_back_kbd(),
            )
            return
        text = _render_resumo(rows, now.month, now.year)
        await query.edit_message_text(text, reply_markup=_back_kbd(), parse_mode="Markdown")

    elif data.startswith("wallet_del_"):
        try:
            gasto_id = int(data[len("wallet_del_"):])
        except ValueError:
            await query.answer("ID inválido.")
            return
        ok = _deletar(user_id, gasto_id)
        await query.answer("✅ Deletado!" if ok else "Gasto não encontrado.")
        now = datetime.now()
        rows = _listar(user_id, now.month, now.year)
        if not rows:
            await query.edit_message_text(
                f"📋 Nenhum gasto em {_mes_nome(now.month, now.year)}.",
                reply_markup=_back_kbd(),
            )
            return
        text, kbd = _render_gastos(rows, now.month, now.year)
        await query.edit_message_text(text, reply_markup=kbd, parse_mode="Markdown")

    # ── Saldo ──────────────────────────────────────────────────────────────────

    elif data == "wallet_saldo":
        saldo = _get_saldo(user_id)
        now = datetime.now()
        rows = _resumo(user_id, now.month, now.year)
        gasto_mes = sum(v for _, v in rows)
        disponivel = saldo - gasto_mes
        text = (
            "💳 *Saldo*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"✅ Disponível: *{_fmt(disponivel)}*\n"
            f"📉 Gasto em {MESES_PT[now.month]}: *{_fmt(gasto_mes)}*\n"
            f"🏦 Saldo total: *{_fmt(saldo)}*"
        )
        await query.edit_message_text(text, reply_markup=_kbd_saldo(), parse_mode="Markdown")

    elif data == "wallet_saldo_add":
        context.user_data["awaiting_command"] = "wallet_saldo_valor"
        await query.edit_message_text(
            "💵 *Digite o valor a adicionar ao saldo:*\n_(ex: 500 ou 1500,00)_",
            parse_mode="Markdown",
        )

    # ── Lista de compras ───────────────────────────────────────────────────────

    elif data == "wallet_lista":
        items = _lista_get(user_id)
        if not items:
            await query.edit_message_text(
                "🛒 *Lista de Compras*\n\nLista vazia. Adicione o primeiro item:",
                reply_markup=_kbd_lista_vazia(),
                parse_mode="Markdown",
            )
        else:
            text = _render_lista(items)
            await query.edit_message_text(text, reply_markup=_kbd_lista_com_itens(), parse_mode="Markdown")

    elif data == "wallet_lista_add_texto":
        context.user_data["awaiting_command"] = "wallet_lista_item"
        await query.edit_message_text(
            "✏️ *Digite o item e o valor:*\n_(ex: feijão 13 ou arroz 8,50)_",
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_add_foto":
        context.user_data["awaiting_command"] = "wallet_lista_foto"
        await query.edit_message_text(
            "📷 *Envie a foto do item ou etiqueta de preço:*\n"
            "_(na primeira vez pode demorar alguns segundos para carregar o OCR)_",
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_confirma":
        nome = context.user_data.get("wallet_ocr_nome")
        valor = context.user_data.get("wallet_ocr_valor")
        if not nome or not valor:
            await query.answer("Dados do OCR não encontrados. Tente novamente.")
            return
        context.user_data["wallet_lista_nome_tmp"] = nome
        context.user_data["wallet_lista_valor_tmp"] = valor
        context.user_data["awaiting_command"] = "wallet_lista_qtd"
        await query.edit_message_text(
            f"✅ *{_esc(nome)}* — {_fmt(valor)}\n\n🔢 *Quantos?* _(ex: 1)_",
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_corrige":
        context.user_data["awaiting_command"] = "wallet_lista_item"
        await query.edit_message_text(
            "✏️ *Digite o item e o valor corretos:*\n_(ex: feijão 13 ou arroz 8,50)_",
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_remover":
        items = _lista_get(user_id)
        if not items:
            await query.answer("Lista vazia.")
            return
        total = _lista_total(items)
        kbd_rows = [
            [InlineKeyboardButton(
                f"🗑️ {row[1]} x{row[3]} = {_fmt(row[4])}",
                callback_data=f"wallet_lista_rem_{row[0]}",
            )]
            for row in items
        ]
        kbd_rows.append([InlineKeyboardButton("◀️ Voltar", callback_data="wallet_lista")])
        await query.edit_message_text(
            f"🗑️ *Remover item*\nTotal atual: *{_fmt(total)}*\n\nToque no item para remover:",
            reply_markup=InlineKeyboardMarkup(kbd_rows),
            parse_mode="Markdown",
        )

    elif data.startswith("wallet_lista_rem_"):
        try:
            item_id = int(data[len("wallet_lista_rem_"):])
        except ValueError:
            await query.answer("ID inválido.")
            return
        ok = _lista_remove(user_id, item_id)
        await query.answer("✅ Removido!" if ok else "Item não encontrado.")
        items = _lista_get(user_id)
        if not items:
            await query.edit_message_text(
                "🛒 *Lista de Compras*\n\nLista vazia. Adicione o primeiro item:",
                reply_markup=_kbd_lista_vazia(),
                parse_mode="Markdown",
            )
            return
        total = _lista_total(items)
        kbd_rows = [
            [InlineKeyboardButton(
                f"🗑️ {row[1]} x{row[3]} = {_fmt(row[4])}",
                callback_data=f"wallet_lista_rem_{row[0]}",
            )]
            for row in items
        ]
        kbd_rows.append([InlineKeyboardButton("◀️ Voltar", callback_data="wallet_lista")])
        await query.edit_message_text(
            f"🗑️ *Remover item*\nTotal atual: *{_fmt(total)}*\n\nToque no item para remover:",
            reply_markup=InlineKeyboardMarkup(kbd_rows),
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_finalizar":
        items = _lista_get(user_id)
        if not items:
            await query.answer("Lista vazia.")
            return
        total = _lista_total(items)
        saldo = _get_saldo(user_id)
        text = _render_lista(items, "🛒 *Lista Finalizada — 🍔 Alimentação*")
        text += f"\n\n💳 Saldo atual: *{_fmt(saldo)}*\n\n💰 *Deseja abater do saldo?*"
        context.user_data["wallet_lista_total"] = total
        await query.edit_message_text(text, reply_markup=_kbd_abater(), parse_mode="Markdown")

    elif data == "wallet_lista_abater_sim":
        total = context.user_data.get("wallet_lista_total", 0.0)
        novo_saldo = _deduct_saldo(user_id, total)
        await query.edit_message_text(
            f"✅ *{_fmt(total)} abatido do saldo.*\n"
            f"💳 Novo saldo: *{_fmt(novo_saldo)}*\n\n"
            "O que deseja fazer com a lista?",
            reply_markup=_kbd_pos_abater(),
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_abater_nao":
        await query.edit_message_text(
            "Ok! O que deseja fazer com a lista?",
            reply_markup=_kbd_pos_abater(),
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_salvar":
        items = _lista_get(user_id)
        total = context.user_data.get("wallet_lista_total", _lista_total(items))
        if items:
            nomes = ", ".join(row[1] for row in items)
            _lancar(user_id, "alimentacao", total, f"Lista: {nomes}"[:200])
        _lista_clear(user_id)
        await query.edit_message_text(
            f"✅ *Lista salva no histórico!*\n💰 *{_fmt(total)}* em 🍔 Alimentação",
            reply_markup=_back_kbd(),
            parse_mode="Markdown",
        )

    elif data == "wallet_lista_apagar":
        _lista_clear(user_id)
        await query.edit_message_text(
            "🗑️ Lista apagada.",
            reply_markup=_back_kbd(),
            parse_mode="Markdown",
        )


async def handle_wallet_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Retorna True se o input foi consumido pela wallet (interrompe o handler geral)."""
    awaiting = context.user_data.get("awaiting_command")

    if awaiting == "wallet_valor":
        text = update.message.text.strip().replace(",", ".")
        try:
            valor = float(text)
            if valor <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Valor inválido. Digite um número positivo (ex: 29.90):")
            return True
        context.user_data["wallet_valor"] = valor
        context.user_data["awaiting_command"] = "wallet_descricao"
        cat = CATEGORIAS[context.user_data["wallet_categoria"]]
        await update.message.reply_text(
            f"Categoria: {cat} | {_fmt(valor)}\n\n📝 *Descrição:*\n_(ou envie `-` para pular)_",
            parse_mode="Markdown",
        )
        return True

    elif awaiting == "wallet_descricao":
        desc = update.message.text.strip()
        if desc == "-":
            desc = ""
        user_id = update.effective_user.id
        cat = context.user_data.get("wallet_categoria", "outros")
        valor = context.user_data.get("wallet_valor", 0.0)
        _lancar(user_id, cat, valor, desc)
        novo_saldo = _deduct_saldo(user_id, valor)
        context.user_data["awaiting_command"] = None
        label = CATEGORIAS.get(cat, cat)
        await update.message.reply_text(
            f"✅ *Gasto registrado!*\n\n{label} — {_fmt(valor)}"
            + (f"\n📝 _{_esc(desc)}_" if desc else "")
            + f"\n\n💳 Saldo restante: *{_fmt(novo_saldo)}*",
            reply_markup=_kbd_wallet(),
            parse_mode="Markdown",
        )
        return True

    elif awaiting == "wallet_saldo_valor":
        text = update.message.text.strip().replace(",", ".")
        try:
            valor = float(text)
            if valor <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Valor inválido. Digite um número positivo (ex: 500):")
            return True
        user_id = update.effective_user.id
        novo_saldo = _add_saldo(user_id, valor)
        context.user_data["awaiting_command"] = None
        await update.message.reply_text(
            f"✅ *{_fmt(valor)} adicionado ao saldo!*\n💳 Saldo atual: *{_fmt(novo_saldo)}*",
            reply_markup=_kbd_wallet(),
            parse_mode="Markdown",
        )
        return True

    elif awaiting == "wallet_lista_item":
        text = update.message.text.strip()
        nome, valor = _parse_item_text(text)
        if nome is None or valor is None:
            await update.message.reply_text(
                "❌ Formato inválido. Use: *nome valor*\n_(ex: feijão 13 ou arroz 8,50)_",
                parse_mode="Markdown",
            )
            return True
        context.user_data["wallet_lista_nome_tmp"] = nome
        context.user_data["wallet_lista_valor_tmp"] = valor
        context.user_data["awaiting_command"] = "wallet_lista_qtd"
        await update.message.reply_text(
            f"📦 *{_esc(nome)}* — {_fmt(valor)}\n\n🔢 *Quantos?* _(ex: 1)_",
            parse_mode="Markdown",
        )
        return True

    elif awaiting == "wallet_lista_qtd":
        text = update.message.text.strip()
        try:
            qtd = int(text)
            if qtd <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Quantidade inválida. Digite um número inteiro positivo (ex: 2):")
            return True
        user_id = update.effective_user.id
        nome = context.user_data.pop("wallet_lista_nome_tmp", "Item")
        valor = context.user_data.pop("wallet_lista_valor_tmp", 0.0)
        context.user_data.pop("wallet_ocr_nome", None)
        context.user_data.pop("wallet_ocr_valor", None)
        _lista_add(user_id, nome, valor, qtd)
        subtotal = round(valor * qtd, 2)
        context.user_data["awaiting_command"] = None
        items = _lista_get(user_id)
        total = _lista_total(items)
        await update.message.reply_text(
            f"✅ *Adicionado!*\n"
            f"📦 *{_esc(nome)}* x{qtd} = *{_fmt(subtotal)}*\n"
            f"🛒 Total da lista: *{_fmt(total)}*",
            reply_markup=_kbd_lista_mais(),
            parse_mode="Markdown",
        )
        return True

    return False


async def handle_wallet_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Processa foto quando awaiting_command == 'wallet_lista_foto'. Retorna True se consumiu."""
    if context.user_data.get("awaiting_command") != "wallet_lista_foto":
        return False

    msg = await update.message.reply_text("🔍 Processando imagem com OCR...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        raw_text = await _ocr_from_photo(photo_file)
        nome, valor = _parse_item_text(raw_text)

        if nome is None or valor is None:
            await msg.edit_text(
                f"⚠️ Não consegui identificar item e valor na imagem.\n"
                f"Texto detectado: _{_esc(raw_text or 'nenhum')}_\n\n"
                "Digite manualmente: *nome valor*",
                parse_mode="Markdown",
            )
            context.user_data["awaiting_command"] = "wallet_lista_item"
            return True

        context.user_data["wallet_ocr_nome"] = nome
        context.user_data["wallet_ocr_valor"] = valor
        context.user_data["awaiting_command"] = None

        await msg.edit_text(
            f"📷 *OCR detectou:*\n\n"
            f"📦 Nome: *{_esc(nome)}*\n"
            f"💵 Valor: *{_fmt(valor)}*\n\n"
            "Está correto?",
            reply_markup=_kbd_confirmar_ocr(),
            parse_mode="Markdown",
        )

    except Exception as e:
        await msg.edit_text(
            f"❌ Erro ao processar imagem: {_esc(str(e))}\n\nDigite manualmente: *nome valor*",
            parse_mode="Markdown",
        )
        context.user_data["awaiting_command"] = "wallet_lista_item"

    return True
