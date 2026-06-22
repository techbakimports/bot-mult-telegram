"""
Módulo de sorteio — palavras, números, cara/coroa, dados
"""
import random

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from utils import is_authorized


# ── Teclados ─────────────────────────────────────────────────────────────────

def _kbd_sorteio() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Sortear palavras", callback_data="sort_palavras")],
        [InlineKeyboardButton("🔢 Sortear número", callback_data="sort_numero")],
        [
            InlineKeyboardButton("🪙 Cara ou coroa", callback_data="sort_moeda"),
            InlineKeyboardButton("🎯 Rolar dados", callback_data="sort_dado"),
        ],
        [InlineKeyboardButton("◀️ Voltar", callback_data="voltar")],
    ])


def _kbd_novamente(tipo: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 De novo", callback_data=tipo)],
        [InlineKeyboardButton("◀️ Menu sorteio", callback_data="sorteio")],
    ])


def _kbd_voltar_sorteio() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Menu sorteio", callback_data="sorteio")],
    ])


# ── Comando /sortear ─────────────────────────────────────────────────────────

async def sortear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra menu de sorteio ou sorteia direto se args forem passados."""
    if not is_authorized(update):
        return

    if context.args:
        texto = " ".join(context.args)
        if "," in texto:
            opcoes = [op.strip() for op in texto.split(",") if op.strip()]
            if len(opcoes) < 2:
                await update.message.reply_text("❌ Envie pelo menos 2 opções separadas por vírgula.")
                return
            escolhido = random.choice(opcoes)
            await update.message.reply_text(
                f"🎲 *Sorteio entre {len(opcoes)} opções:*\n\n"
                f"🏆 *{escolhido}*",
                parse_mode="Markdown",
                reply_markup=_kbd_novamente("sort_palavras"),
            )
            return

    await update.message.reply_text(
        "🎲 *Sorteio*\n\nEscolha o tipo:",
        parse_mode="Markdown",
        reply_markup=_kbd_sorteio(),
    )


# ── Callbacks ────────────────────────────────────────────────────────────────

async def handle_sorteio_callback(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = query.data

    if data == "sorteio":
        await query.edit_message_text(
            "🎲 *Sorteio*\n\nEscolha o tipo:",
            parse_mode="Markdown",
            reply_markup=_kbd_sorteio(),
        )

    elif data == "sort_palavras":
        context.user_data["awaiting_command"] = "sort_palavras"
        await query.edit_message_text(
            "🎲 *Sortear palavras*\n\n"
            "Digite as opções separadas por vírgula:\n"
            "_(ex: pizza, hamburguer, sushi, japonês)_",
            parse_mode="Markdown",
        )

    elif data == "sort_numero":
        context.user_data["awaiting_command"] = "sort_numero"
        await query.edit_message_text(
            "🔢 *Sortear número*\n\n"
            "Digite o intervalo (mínimo e máximo):\n"
            "_(ex: 1 200  ou  50 500)_",
            parse_mode="Markdown",
        )

    elif data == "sort_moeda":
        resultado = random.choice(["🪙 Cara!", "🪙 Coroa!"])
        await query.edit_message_text(
            f"🪙 *Cara ou coroa*\n\n🏆 *{resultado}*",
            parse_mode="Markdown",
            reply_markup=_kbd_novamente("sort_moeda"),
        )

    elif data == "sort_dado":
        valor = random.randint(1, 6)
        faces = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        await query.edit_message_text(
            f"🎯 *Rolar dados*\n\n{faces[valor]} *{valor}*",
            parse_mode="Markdown",
            reply_markup=_kbd_novamente("sort_dado"),
        )


# ── Input de texto ───────────────────────────────────────────────────────────

async def handle_sorteio_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Retorna True se o input foi consumido pelo sorteio."""
    awaiting = context.user_data.get("awaiting_command")

    if awaiting == "sort_palavras":
        texto = update.message.text.strip()
        opcoes = [op.strip() for op in texto.split(",") if op.strip()]

        if len(opcoes) < 2:
            await update.message.reply_text(
                "❌ Envie pelo menos 2 opções separadas por vírgula.\n"
                "_(ex: pizza, hamburguer, sushi)_",
                parse_mode="Markdown",
            )
            return True

        escolhido = random.choice(opcoes)
        context.user_data["awaiting_command"] = None
        await update.message.reply_text(
            f"🎲 *Sorteio entre {len(opcoes)} opções:*\n"
            f"{', '.join(opcoes)}\n\n"
            f"🏆 *{escolhido}*",
            parse_mode="Markdown",
            reply_markup=_kbd_novamente("sort_palavras"),
        )
        return True

    elif awaiting == "sort_numero":
        texto = update.message.text.strip()
        # Aceita "1 200", "1-200", "1,200"
        partes = texto.replace("-", " ").replace(",", " ").split()

        if len(partes) != 2:
            await update.message.reply_text(
                "❌ Formato inválido. Digite dois números.\n"
                "_(ex: 1 200  ou  1-200)_",
                parse_mode="Markdown",
            )
            return True

        try:
            minimo = int(partes[0])
            maximo = int(partes[1])
        except ValueError:
            await update.message.reply_text(
                "❌ Use apenas números inteiros.\n"
                "_(ex: 1 200)_",
                parse_mode="Markdown",
            )
            return True

        if minimo >= maximo:
            await update.message.reply_text(
                "❌ O primeiro número deve ser menor que o segundo.\n"
                "_(ex: 1 200)_",
                parse_mode="Markdown",
            )
            return True

        if maximo - minimo > 1_000_000:
            await update.message.reply_text("❌ Intervalo muito grande (máx 1.000.000).")
            return True

        resultado = random.randint(minimo, maximo)
        context.user_data["awaiting_command"] = None
        await update.message.reply_text(
            f"🔢 *Sorteio de {minimo} a {maximo}:*\n\n"
            f"🏆 *{resultado}*",
            parse_mode="Markdown",
            reply_markup=_kbd_novamente("sort_numero"),
        )
        return True

    return False
