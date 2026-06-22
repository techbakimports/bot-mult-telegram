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


def _kbd_repetir_ou_parar() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Sortear de novo", callback_data="sort_repetir")],
        [InlineKeyboardButton("✅ Finalizar sorteio", callback_data="sorteio")],
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
            context.user_data["sort_tipo"] = "palavras"
            context.user_data["sort_opcoes"] = opcoes
            escolhido = random.choice(opcoes)
            await update.message.reply_text(
                f"🎲 *Sorteio entre {len(opcoes)} opções:*\n"
                f"{', '.join(opcoes)}\n\n"
                f"🏆 *{escolhido}*",
                parse_mode="Markdown",
                reply_markup=_kbd_repetir_ou_parar(),
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
        context.user_data.pop("sort_tipo", None)
        context.user_data.pop("sort_opcoes", None)
        context.user_data.pop("sort_min", None)
        context.user_data.pop("sort_max", None)
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
            "_(ex: 1 200  ou  1-200)_",
            parse_mode="Markdown",
        )

    elif data == "sort_repetir":
        tipo = context.user_data.get("sort_tipo")

        if tipo == "palavras":
            opcoes = context.user_data.get("sort_opcoes", [])
            if not opcoes:
                await query.edit_message_text(
                    "❌ Dados perdidos. Comece novamente.",
                    reply_markup=_kbd_sorteio(),
                )
                return
            escolhido = random.choice(opcoes)
            await query.edit_message_text(
                f"🎲 *Sorteio entre {len(opcoes)} opções:*\n"
                f"{', '.join(opcoes)}\n\n"
                f"🏆 *{escolhido}*",
                parse_mode="Markdown",
                reply_markup=_kbd_repetir_ou_parar(),
            )

        elif tipo == "numero":
            minimo = context.user_data.get("sort_min", 0)
            maximo = context.user_data.get("sort_max", 0)
            if minimo >= maximo:
                await query.edit_message_text(
                    "❌ Dados perdidos. Comece novamente.",
                    reply_markup=_kbd_sorteio(),
                )
                return
            resultado = random.randint(minimo, maximo)
            await query.edit_message_text(
                f"🔢 *Sorteio de {minimo} a {maximo}:*\n\n"
                f"🏆 *{resultado}*",
                parse_mode="Markdown",
                reply_markup=_kbd_repetir_ou_parar(),
            )

        elif tipo == "moeda":
            resultado = random.choice(["🪙 Cara!", "🪙 Coroa!"])
            await query.edit_message_text(
                f"🪙 *Cara ou coroa*\n\n🏆 *{resultado}*",
                parse_mode="Markdown",
                reply_markup=_kbd_repetir_ou_parar(),
            )

        elif tipo == "dado":
            valor = random.randint(1, 6)
            faces = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
            await query.edit_message_text(
                f"🎯 *Rolar dados*\n\n{faces[valor]} *{valor}*",
                parse_mode="Markdown",
                reply_markup=_kbd_repetir_ou_parar(),
            )

        else:
            await query.edit_message_text(
                "❌ Nenhum sorteio ativo. Comece novamente.",
                reply_markup=_kbd_sorteio(),
            )

    elif data == "sort_moeda":
        context.user_data["sort_tipo"] = "moeda"
        resultado = random.choice(["🪙 Cara!", "🪙 Coroa!"])
        await query.edit_message_text(
            f"🪙 *Cara ou coroa*\n\n🏆 *{resultado}*",
            parse_mode="Markdown",
            reply_markup=_kbd_repetir_ou_parar(),
        )

    elif data == "sort_dado":
        context.user_data["sort_tipo"] = "dado"
        valor = random.randint(1, 6)
        faces = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        await query.edit_message_text(
            f"🎯 *Rolar dados*\n\n{faces[valor]} *{valor}*",
            parse_mode="Markdown",
            reply_markup=_kbd_repetir_ou_parar(),
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

        context.user_data["sort_tipo"] = "palavras"
        context.user_data["sort_opcoes"] = opcoes
        escolhido = random.choice(opcoes)
        context.user_data["awaiting_command"] = None
        await update.message.reply_text(
            f"🎲 *Sorteio entre {len(opcoes)} opções:*\n"
            f"{', '.join(opcoes)}\n\n"
            f"🏆 *{escolhido}*",
            parse_mode="Markdown",
            reply_markup=_kbd_repetir_ou_parar(),
        )
        return True

    elif awaiting == "sort_numero":
        texto = update.message.text.strip()
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

        context.user_data["sort_tipo"] = "numero"
        context.user_data["sort_min"] = minimo
        context.user_data["sort_max"] = maximo
        resultado = random.randint(minimo, maximo)
        context.user_data["awaiting_command"] = None
        await update.message.reply_text(
            f"🔢 *Sorteio de {minimo} a {maximo}:*\n\n"
            f"🏆 *{resultado}*",
            parse_mode="Markdown",
            reply_markup=_kbd_repetir_ou_parar(),
        )
        return True

    return False
