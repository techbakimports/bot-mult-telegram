"""
Carteira de gastos — um banco SQLite por usuário em gastos/<user_id>.db
"""
import sqlite3
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
        cur = conn.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
        return cur.rowcount > 0


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
    """Escapa caracteres especiais do Markdown v1 em texto do usuário."""
    for ch in ("*", "_", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


# ─── Teclados ─────────────────────────────────────────────────────────────────

def _kbd_wallet() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Lançar Gasto",  callback_data="wallet_lancar"),
            InlineKeyboardButton("📋 Ver Gastos",    callback_data="wallet_ver"),
        ],
        [
            InlineKeyboardButton("📊 Resumo do Mês", callback_data="wallet_resumo"),
            InlineKeyboardButton("◀️ Voltar",        callback_data="voltar"),
        ],
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


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def show_wallet_menu(query) -> None:
    await query.edit_message_text(
        "💰 *Carteira de Gastos*\n\nEscolha uma opção:",
        reply_markup=_kbd_wallet(),
        parse_mode="Markdown",
    )


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
        gasto_id = _lancar(user_id, cat, valor, desc)
        context.user_data["awaiting_command"] = None
        label = CATEGORIAS.get(cat, cat)
        await update.message.reply_text(
            f"✅ *Gasto registrado!*\n\n{label} — {_fmt(valor)}"
            + (f"\n📝 _{_esc(desc)}_" if desc else ""),
            reply_markup=_kbd_wallet(),
            parse_mode="Markdown",
        )
        return True

    return False