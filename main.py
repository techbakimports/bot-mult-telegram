"""
Bot Telegram - Arquivo Principal
Executa o bot e registra todos os handlers
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from config import TOKEN
from utils import is_authorized
from handlers import status, whois_lookup, ping_site
from tools import (
    traduzir,
    encurtar_url,
    gerar_qrcode,
    baixar_media,
    process_audio,
    clima,
    fazer_download,
    gerar_imagem,
)
from button_handler import button_handler, show_menu


# 🚀 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando inicial do bot"""
    if not is_authorized(update):
        return
    
    # Criar os botões inline com todas as opções
    keyboard = [
        [InlineKeyboardButton("Status", callback_data="status"), InlineKeyboardButton("Whois", callback_data="whois")],
        [InlineKeyboardButton("Ping Site", callback_data="ping_site"), InlineKeyboardButton("Traduz", callback_data="traduz")],
        [InlineKeyboardButton("Encurtar URL", callback_data="encurta"), InlineKeyboardButton("QR Code", callback_data="qrcode")],
        [InlineKeyboardButton("Baixar", callback_data="baixar"), InlineKeyboardButton("Audio", callback_data="audio")],
        [InlineKeyboardButton("Clima", callback_data="clima"), InlineKeyboardButton("Imagem", callback_data="imagem")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Bot online e funcionando!\n\nEscolha uma opção:",
        reply_markup=reply_markup
    )


# 📨 Handler para mensagens de texto quando um comando está aguardando input
async def handle_input_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens quando um comando está aguardando input"""
    if not is_authorized(update):
        return
    
    # Verificar se há um comando aguardando
    awaiting_cmd = context.user_data.get('awaiting_command')
    if not awaiting_cmd:
        return
    
    msg_text = update.message.text.strip()
    
    try:
        if awaiting_cmd == 'baixar':
            # Baixar vídeo/áudio
            context.user_data['download_url'] = msg_text
            
            # Mostrar menu de qualidades
            keyboard = [
                [InlineKeyboardButton("🎬 360p (Rápido)", callback_data="qual_360p")],
                [InlineKeyboardButton("🎥 480p (Normal)", callback_data="qual_480p")],
                [InlineKeyboardButton("🎞️ 720p (HD)", callback_data="qual_720p")],
                [InlineKeyboardButton("🎵 Áudio MP3", callback_data="qual_audio")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="qual_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "📥 Escolha a qualidade desejada:\n\n"
                "🎬 360p - Melhor velocidade\n"
                "🎥 480p - Bom equilíbrio\n"
                "🎞️ 720p - Melhor qualidade\n"
                "🎵 Áudio - Apenas som em MP3",
                reply_markup=reply_markup
            )
            context.user_data['awaiting_command'] = None
        
        elif awaiting_cmd == 'clima':
            # Buscar clima
            context.args = msg_text.split()
            await clima(update, context)
            context.user_data['awaiting_command'] = None

        elif awaiting_cmd == 'imagem':
            context.args = [msg_text]
            await gerar_imagem(update, context)
            context.user_data['awaiting_command'] = None

    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")
        context.user_data['awaiting_command'] = None



# 🤖 Main
def main():
    """Função principal que inicia o bot"""
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers dos comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("whois", whois_lookup))
    app.add_handler(CommandHandler("ping_site", ping_site))
    app.add_handler(CommandHandler("traduz", traduzir))
    app.add_handler(CommandHandler("encurta", encurtar_url))
    app.add_handler(CommandHandler("qrcode", gerar_qrcode))
    app.add_handler(CommandHandler("baixar", baixar_media))
    app.add_handler(CommandHandler("audio", process_audio))
    app.add_handler(CommandHandler("clima", clima))
    app.add_handler(CommandHandler("imagem", gerar_imagem))

    # Handler para capturar mensagens quando um comando está aguardando input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input_message))
    
    # Handler dos botões inline
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Bot iniciado...")
    app.run_polling()


if __name__ == "__main__":
    main()
