"""
Handler dos botões inline do menu
"""
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from utils import is_authorized
from handlers import status
from tools import fazer_download


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
    elif query.data == "conversor":
        # Submenu de conversor
        keyboard = [
            [InlineKeyboardButton("USD-BRL", callback_data="conv_usd_brl"), InlineKeyboardButton("EUR-BRL", callback_data="conv_eur_brl")],
            [InlineKeyboardButton("USD-EUR", callback_data="conv_usd_eur"), InlineKeyboardButton("GBP-BRL", callback_data="conv_gbp_brl")],
            [InlineKeyboardButton("Voltar", callback_data="voltar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Selecione a conversao (padrao 100):", reply_markup=reply_markup)
    elif query.data == "unidades":
        # Submenu de unidades
        keyboard = [
            [InlineKeyboardButton("100 km-mi", callback_data="unit_km_mi"), InlineKeyboardButton("100 kg-lb", callback_data="unit_kg_lb")],
            [InlineKeyboardButton("100 m-ft", callback_data="unit_m_ft"), InlineKeyboardButton("100 l-gal", callback_data="unit_l_gal")],
            [InlineKeyboardButton("Voltar", callback_data="voltar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Selecione a conversao:", reply_markup=reply_markup)
    # Conversões de moedas
    elif query.data.startswith("conv_"):
        _, origem, destino = query.data.split("_")
        valor = 100
        try:
            url = f"https://api.exchangerate-api.com/v4/latest/{origem.upper()}"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            taxa = data['rates'][destino.upper()]
            resultado = valor * taxa
            
            msg = f"Conversao:\n\n{valor} {origem.upper()} = {resultado:.2f} {destino.upper()}"
            keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=msg, reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(text=f"❌ Erro: {str(e)}")
    # Conversões de unidades
    elif query.data.startswith("unit_"):
        _, origem, destino = query.data.split("_")
        valor = 100
        
        conversoes = {
            ('km', 'mi'): 0.621371,
            ('mi', 'km'): 1.60934,
            ('m', 'ft'): 3.28084,
            ('ft', 'm'): 0.3048,
            ('kg', 'lb'): 2.20462,
            ('lb', 'kg'): 0.453592,
            ('l', 'gal'): 0.264172,
            ('gal', 'l'): 3.78541,
        }
        
        chave = (origem, destino)
        if chave in conversoes:
            resultado = valor * conversoes[chave]
            msg = f"Conversao:\n\n{valor} {origem} = {resultado:.2f} {destino}"
            keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=msg, reply_markup=reply_markup)
        else:
            await query.edit_message_text(text="❌ Conversão não encontrada")
    elif query.data == "traduz":
        await query.edit_message_text(text="Use: /traduz <idioma_destino> <texto>\nEx: /traduz es Olá mundo")
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
            "Ex: paisagem cyberpunk à noite\n\n"
            "Com OPENAI_API_KEY no .env usa DALL-E 3; senão Pollinations."
        )
    elif query.data == "voltar":
        # Voltar ao menu principal
        await show_menu(query)


async def show_menu(query):
    """Mostra o menu principal.

    Se a mensagem atual for uma foto (ex: QR code, imagem gerada),
    edit_message_text falha. Nesse caso, deleta a mensagem e envia uma nova.
    """
    keyboard = [
        [InlineKeyboardButton("Status", callback_data="status"), InlineKeyboardButton("Whois", callback_data="whois")],
        [InlineKeyboardButton("Ping Site", callback_data="ping_site"), InlineKeyboardButton("Traduz", callback_data="traduz")],
        [InlineKeyboardButton("Encurtar URL", callback_data="encurta"), InlineKeyboardButton("QR Code", callback_data="qrcode")],
        [InlineKeyboardButton("Baixar", callback_data="baixar"), InlineKeyboardButton("Audio", callback_data="audio")],
        [InlineKeyboardButton("Clima", callback_data="clima"), InlineKeyboardButton("Imagem", callback_data="imagem")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(text="Bot online e funcionando!\n\nEscolha uma opcao:", reply_markup=reply_markup)
    except Exception:
        # Mensagem é uma foto/mídia — não dá para editar para texto.
        # Deleta a mensagem antiga e envia o menu como nova mensagem.
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.chat.send_message(
            text="Bot online e funcionando!\n\nEscolha uma opcao:",
            reply_markup=reply_markup,
        )
