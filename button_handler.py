"""
Handler dos botões inline do menu
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from utils import is_authorized
from handlers import status
from tools import fazer_download
from wallet import handle_wallet_callback, show_wallet_menu


# 🔘 Handler dos botões inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa cliques nos botões inline"""
    if not is_authorized(update):
        return
    
    query = update.callback_query
    await query.answer()
    
    if query.data == "status":
        await status(update, context)
    elif query.data == "whois":
        await query.edit_message_text(text="Envie o domínio: /whois <dominio>")
    elif query.data == "ping_site":
        await query.edit_message_text(text="Envie o site: /ping_site <site>")
    elif query.data == "encurta":
        await query.edit_message_text(text="Use: /encurta <url>\nEx: /encurta https://www.exemplo.com.br")
    elif query.data == "qrcode":
        await query.edit_message_text(text="Use: /qrcode <texto|url>\nEx: /qrcode https://t.me/seu_bot")
    elif query.data == "baixar":
        context.user_data['awaiting_command'] = 'baixar'
        await query.edit_message_text(text="📨 Envie a URL do vídeo/áudio:")
    elif query.data.startswith("qual_"):
        # Callbacks de qualidade de download
        if query.data == "qual_cancel":
            await query.edit_message_text(text="❌ Download cancelado")
        elif query.data == "qual_360p":
            await fazer_download(update, context, "360p")
        elif query.data == "qual_480p":
            await fazer_download(update, context, "480p")
        elif query.data == "qual_720p":
            await fazer_download(update, context, "720p")
        elif query.data == "qual_audio":
            await fazer_download(update, context, "audio")
    elif query.data == "audio":
        await query.edit_message_text(text="Use: envie/resp: arquivo e /audio <convert|cut|volume|fadein|fadeout>\nEx: responda ao arquivo com /audio convert mp3")

    elif query.data == "clima":
        context.user_data['awaiting_command'] = 'clima'
        await query.edit_message_text(text="📨 Envie o nome da cidade:")
    elif query.data == "imagem":
        context.user_data['awaiting_command'] = 'imagem'
        await query.edit_message_text(
            text="🎨 Envie o prompt para gerar a imagem.\n"
            "Ex: paisagem cyberpunk à noite"
        )
    elif query.data == "conv_img":
        await query.edit_message_text(
            text="🖼️ Converter imagem\n\n"
            "Envie uma imagem (foto ou documento) e responda a ela com:\n"
            "/conv_img <formato>\n\n"
            "Formatos: jpg, png, webp, bmp, gif, tiff, pdf"
        )
    elif query.data == "carteira" or query.data.startswith("wallet_"):
        await handle_wallet_callback(query, context)
    elif query.data == "voltar":
        # Voltar ao menu principal
        await show_menu(query)


async def show_menu(query):
    """Mostra o menu principal.

    Se a mensagem atual for uma foto (ex: QR code, imagem gerada),
    edit_message_text falha. Nesse caso, removemos os botões inline e enviamos uma nova.
    """
    keyboard = [
        [InlineKeyboardButton("Status", callback_data="status"), InlineKeyboardButton("Whois", callback_data="whois")],
        [InlineKeyboardButton("Ping Site", callback_data="ping_site"), InlineKeyboardButton("Encurtar URL", callback_data="encurta")],
        [InlineKeyboardButton("QR Code", callback_data="qrcode"), InlineKeyboardButton("Baixar", callback_data="baixar")],
        [InlineKeyboardButton("Áudio", callback_data="audio"), InlineKeyboardButton("Clima", callback_data="clima")],
        [InlineKeyboardButton("Imagem", callback_data="imagem"), InlineKeyboardButton("Converter Img", callback_data="conv_img")],
        [InlineKeyboardButton("💰 Carteira", callback_data="carteira")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(text="Bot online e funcionando!\n\nEscolha uma opcao:", reply_markup=reply_markup)
    except Exception:
        # Mensagem é uma foto/mídia — não dá para editar para texto.
        # Remove teclado e envia o menu como nova mensagem.
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.chat.send_message(
            text="Bot online e funcionando!\n\nEscolha uma opcao:",
            reply_markup=reply_markup,
        )
