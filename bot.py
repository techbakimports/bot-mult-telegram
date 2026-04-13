
import time
import platform
import psutil
import subprocess
import os
import sys
import logging
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Console Windows (cp1252) não imprime emojis nos logs sem UTF-8
for _stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 📋 Configurar Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)
logger = logging.getLogger(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not TOKEN:
    logger.error(
        "BOT_TOKEN não definido. Crie o arquivo .env na pasta do bot com uma linha:\n"
        "BOT_TOKEN=seu_token_do_BotFather"
    )
    sys.exit(1)

import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from tools import clima, gerar_qrcode, process_audio, fazer_download, gerar_imagem

AUTHORIZED_ID = 109787324


# 🔒 Verificação de autorização
def is_authorized(update: Update):
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    is_auth = user_id == AUTHORIZED_ID
    logger.info(f"[AUTH] Verificação: {username} (ID: {user_id}) - Autorizado: {is_auth}")
    return is_auth

# 📨 Handler para mensagens quando um comando está aguardando input
async def handle_input_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens quando um comando está aguardando input"""
    username = update.effective_user.username or "N/A"
    
    if not is_authorized(update):
        return
    
    # Verificar se há um comando aguardando
    awaiting_cmd = context.user_data.get('awaiting_command')
    if not awaiting_cmd:
        return
    
    msg_text = update.message.text.strip()
    logger.info(f"[INPUT] {username} enviou: {msg_text} para comando: {awaiting_cmd}")
    
    try:
        if awaiting_cmd == 'whois':
            # Executar whois
            context.args = msg_text.split()
            await whois_lookup(update, context)
            context.user_data['awaiting_command'] = None
            
        elif awaiting_cmd == 'ping_site':
            # Executar ping
            context.args = msg_text.split()
            await ping_site(update, context)
            context.user_data['awaiting_command'] = None
            
        elif awaiting_cmd == 'traduz':
            # Executar tradução
            parts = msg_text.split(maxsplit=1)
            context.args = parts
            await traduzir(update, context)
            context.user_data['awaiting_command'] = None
            
        elif awaiting_cmd == 'encurta':
            # Encurtar URL
            context.args = [msg_text]
            await encurtar_url(update, context)
            context.user_data['awaiting_command'] = None
            
        elif awaiting_cmd == 'qrcode':
            # Gerar QR Code
            context.args = msg_text.split()
            await gerar_qrcode(update, context)
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

        elif awaiting_cmd == 'baixar':
            # Baixar vídeo
            context.args = [msg_text]
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
            
    except Exception as e:
        logger.error(f"[INPUT] Erro ao processar {awaiting_cmd}: {str(e)}")
        await update.message.reply_text(f"❌ Erro: {str(e)}")
        context.user_data['awaiting_command'] = None

# 🚀 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[START] Comando /start por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[START] Acesso negado para {username}")
        return
    
    logger.info(f"[START] Exibindo menu para {username}")
    
    # Criar os botões inline com todas as opções
    keyboard = [
        [InlineKeyboardButton("Status", callback_data="status"), InlineKeyboardButton("Whois", callback_data="whois")],
        [InlineKeyboardButton("Ping Site", callback_data="ping_site"), InlineKeyboardButton("Conversor", callback_data="conversor")],
        [InlineKeyboardButton("Unidades", callback_data="unidades"), InlineKeyboardButton("Traduz", callback_data="traduz")],
        [InlineKeyboardButton("Encurtar URL", callback_data="encurta"), InlineKeyboardButton("QR Code", callback_data="qrcode")],
        [InlineKeyboardButton("Baixar", callback_data="baixar"), InlineKeyboardButton("Áudio", callback_data="audio")],
        [InlineKeyboardButton("Clima", callback_data="clima"), InlineKeyboardButton("Imagem", callback_data="imagem")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Bot online e funcionando!\n\nEscolha uma opção:",
        reply_markup=reply_markup
    )

# 📊 /status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[STATUS] Solicidade por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[STATUS] Acesso negado para {username}")
        return

    logger.info(f"[STATUS] Coletando informações de sistema...")
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_hours = round(uptime_seconds / 3600, 2)
    logger.info(f"[STATUS] CPU: {cpu}% | RAM: {ram}% | Uptime: {uptime_hours}h")

    msg = (
        f"📊 Status da VPS\n\n"
        f"CPU: {cpu}%\n"
        f"RAM: {ram}%\n"
        f"Uptime: {uptime_hours} horas\n"
        f"Sistema: {platform.system()}"
    )

    # Verifica se vem de um callback (inline button)
    if update.callback_query:
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text=msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg)

# 🔎 /whois
async def whois_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[WHOIS] Solicitude por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[WHOIS] Acesso negado para {username}")
        return

    if not context.args:
        logger.warning(f"[WHOIS] Parâmetros inválidos por {username}")
        await update.message.reply_text("Use: /whois <dominio>")
        return

    domain = context.args[0]
    logger.info(f"[WHOIS] Executando whois para: {domain}")
    start_time = time.time()

    try:
        result = subprocess.run(
            ["whois", domain],
            capture_output=True,
            text=True,
            timeout=15
        )
        elapsed = time.time() - start_time
        logger.info(f"[WHOIS] ✅ Completado em {elapsed:.2f}s para {domain}")

        output = result.stdout

        if len(output) > 4000:
            output = output[:4000] + "\n\n... (cortado)"
            logger.info(f"[WHOIS] Output cortado (original > 4000 chars)")

        await update.message.reply_text(f"🔎 Whois:\n\n{output}")
        logger.info(f"[WHOIS] ✅ Resultado enviado para {username}")

    except subprocess.TimeoutExpired:
        logger.error(f"[WHOIS] ❌ TIMEOUT para {domain}")
        await update.message.reply_text(f"❌ Timeout: Whois demorou muito")
    except Exception as e:
        logger.error(f"[WHOIS] ❌ Erro para {domain}: {str(e)}")
        await update.message.reply_text(f"Erro: {str(e)}")

# 🌍 /ping_site
async def ping_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[PING] Solicitude por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[PING] Acesso negado para {username}")
        return

    if not context.args:
        logger.warning(f"[PING] Parâmetros inválidos por {username}")
        await update.message.reply_text("Use: /ping_site <site>")
        return

    site = context.args[0]
    logger.info(f"[PING] Executando ping para: {site}")
    start_time = time.time()

    try:
        result = subprocess.run(
            ["ping", "-c", "4", site],
            capture_output=True,
            text=True,
            timeout=10
        )
        elapsed = time.time() - start_time
        logger.info(f"[PING] ✅ Completado em {elapsed:.2f}s para {site}")

        output = result.stdout

        if len(output) > 4000:
            output = output[:4000] + "\n\n... (cortado)"
            logger.info(f"[PING] Output cortado (original > 4000 chars)")

        await update.message.reply_text(f"🌍 Ping Result:\n\n{output}")
        logger.info(f"[PING] ✅ Resultado enviado para {username}")

    except subprocess.TimeoutExpired:
        logger.error(f"[PING] ❌ TIMEOUT para {site}")
        await update.message.reply_text(f"❌ Timeout: Ping demorou muito")
    except Exception as e:
        logger.error(f"[PING] ❌ Erro para {site}: {str(e)}")
        await update.message.reply_text(f"Erro: {str(e)}")

# 💱 /conversor
async def conversor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[CONVERSOR] Solicitude por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[CONVERSOR] Acesso negado para {username}")
        return
    
    try:
        if not context.args or len(context.args) < 3:
            logger.warning(f"[CONVERSOR] Parâmetros inválidos por {username}")
            await update.message.reply_text("Use: /conversor <valor> <moeda_origem> <moeda_destino>\nEx: /conversor 100 USD BRL")
            return
        
        valor = float(context.args[0])
        origem = context.args[1].upper()
        destino = context.args[2].upper()
        logger.info(f"[CONVERSOR] Convertendo {valor} {origem} → {destino}")
        
        # Fazer conversão via API
        logger.info(f"[CONVERSOR] Buscando taxa de câmbio...")
        start_time = time.time()
        url = f"https://api.exchangerate-api.com/v4/latest/{origem}"
        response = requests.get(url, timeout=5)
        elapsed = time.time() - start_time
        logger.info(f"[CONVERSOR] ✅ Taxa obtida em {elapsed:.2f}s")
        data = response.json()
        
        if destino not in data['rates']:
            logger.warning(f"[CONVERSOR] Moeda {destino} não encontrada")
            await update.message.reply_text(f"❌ Moeda '{destino}' não encontrada!")
            return
        
        taxa = data['rates'][destino]
        resultado = valor * taxa
        logger.info(f"[CONVERSOR] ✅ Resultado: {valor} {origem} = {resultado:.2f} {destino}")
        
        await update.message.reply_text(f"💱 Conversão:\n\n{valor} {origem} = {resultado:.2f} {destino}")
        logger.info(f"[CONVERSOR] ✅ Resultado enviado para {username}")
    
    except requests.Timeout:
        logger.error(f"[CONVERSOR] ❌ TIMEOUT ao buscar taxa")
        await update.message.reply_text(f"❌ Timeout: API de câmbio demorou muito")
    except Exception as e:
        logger.error(f"[CONVERSOR] ❌ Erro: {str(e)}")
        await update.message.reply_text(f"Erro: {str(e)}")

# 📋 /unidades
async def conversor_unidades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[UNIDADES] Solicitude por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[UNIDADES] Acesso negado para {username}")
        return
    
    try:
        if not context.args or len(context.args) < 3:
            logger.warning(f"[UNIDADES] Parâmetros inválidos por {username}")
            await update.message.reply_text("Use: /unidades <valor> <origem> <destino>\nEx: /unidades 100 km mi\n\nOpções: km→mi, m→ft, kg→lb, l→gal")
            return
        
        valor = float(context.args[0])
        origem = context.args[1].lower()
        destino = context.args[2].lower()
        logger.info(f"[UNIDADES] Convertendo {valor} {origem} → {destino}")
        
        # Tabela de conversões (apenas os fatores)
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
        if chave not in conversoes:
            logger.warning(f"[UNIDADES] Conversão não suportada: {origem}→{destino}")
            await update.message.reply_text("❌ Conversão não suportada!")
            return
        
        resultado = valor * conversoes[chave]
        logger.info(f"[UNIDADES] ✅ Resultado: {valor} {origem} = {resultado:.2f} {destino}")
        await update.message.reply_text(f"📋 Conversão:\n\n{valor} {origem} = {resultado:.2f} {destino}")
        logger.info(f"[UNIDADES] ✅ Resultado enviado para {username}")
    
    except ValueError as e:
        logger.error(f"[UNIDADES] ❌ Erro ao converter: {str(e)}")
        await update.message.reply_text(f"❌ Valor inválido")
    except Exception as e:
        logger.error(f"[UNIDADES] ❌ Erro: {str(e)}")
        await update.message.reply_text(f"Erro: {str(e)}")

# 🌐 /traduz
async def traduzir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[TRADUZ] Solicitude por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[TRADUZ] Acesso negado para {username}")
        return
    
    try:
        if not context.args or len(context.args) < 2:
            logger.warning(f"[TRADUZ] Parâmetros inválidos por {username}")
            await update.message.reply_text("Use: /traduz <idioma_destino> <texto>\nEx: /traduz es Olá mundo")
            return
        
        idioma_destino = context.args[0].lower()
        texto = " ".join(context.args[1:])
        logger.info(f"[TRADUZ] Traduzindo para {idioma_destino}: '{texto}'")
        
        # Usar Google Translate via TK library
        logger.info(f"[TRADUZ] Buscando tradução...")
        start_time = time.time()
        url = f"https://api.mymemory.translated.net/get?q={texto}&langpair=pt|{idioma_destino}"
        response = requests.get(url, timeout=5)
        elapsed = time.time() - start_time
        logger.info(f"[TRADUZ] ✅ Obtida em {elapsed:.2f}s")
        data = response.json()
        
        if data['responseStatus'] == 200:
            traducao = data['responseData']['translatedText']
            logger.info(f"[TRADUZ] ✅ Resultado: '{traducao}'")
            await update.message.reply_text(f"🌐 Tradução para {idioma_destino.upper()}:\n\n{traducao}")
            logger.info(f"[TRADUZ] ✅ Resultado enviado para {username}")
        else:
            logger.error(f"[TRADUZ] ❌ API retornou: {data['responseStatus']}")
            await update.message.reply_text("❌ Erro ao traduzir!")
    
    except requests.Timeout:
        logger.error(f"[TRADUZ] ❌ TIMEOUT ao buscar tradução")
        await update.message.reply_text(f"❌ Timeout: API demorou muito")
    except Exception as e:
        logger.error(f"[TRADUZ] ❌ Erro: {str(e)}")
        await update.message.reply_text(f"Erro: {str(e)}")

# 🔗 /encurta
async def encurtar_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    logger.info(f"[ENCURTA] Solicitude por {username}")
    
    if not is_authorized(update):
        logger.warning(f"[ENCURTA] Acesso negado para {username}")
        return
    
    try:
        if not context.args:
            logger.warning(f"[ENCURTA] Parâmetros inválidos por {username}")
            await update.message.reply_text("Use: /encurta <url>\nEx: /encurta https://www.exemplo.com.br")
            return
        
        url = context.args[0]
        logger.info(f"[ENCURTA] Encurtando: {url}")
        
        # Usar TinyURL
        logger.info(f"[ENCURTA] Buscando URL encurtada...")
        start_time = time.time()
        api_url = f"https://tinyurl.com/api-create.php?url={url}"
        response = requests.get(api_url, timeout=5)
        elapsed = time.time() - start_time
        logger.info(f"[ENCURTA] ✅ Obtida em {elapsed:.2f}s")
        url_curta = response.text
        
        if url_curta.startswith('https'):
            logger.info(f"[ENCURTA] ✅ Resultado: {url_curta}")
            await update.message.reply_text(f"🔗 URL Encurtada:\n\n{url_curta}")
            logger.info(f"[ENCURTA] ✅ Resultado enviado para {username}")
        else:
            logger.error(f"[ENCURTA] ❌ Erro ao encurtar: {url_curta}")
            await update.message.reply_text("❌ Erro ao encurtar URL!")
    
    except requests.Timeout:
        logger.error(f"[ENCURTA] ❌ TIMEOUT ao encurtar")
        await update.message.reply_text(f"❌ Timeout: Serviço demorou muito")
    except Exception as e:
        logger.error(f"[ENCURTA] ❌ Erro: {str(e)}")
        await update.message.reply_text(f"Erro: {str(e)}")

# 🔘 Handler dos botões inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "N/A"
    button_data = update.callback_query.data
    logger.info(f"[BUTTON] Botão pressionado por {username}: {button_data}")
    
    if not is_authorized(update):
        logger.warning(f"[BUTTON] Acesso negado para {username}")
        return
    
    query = update.callback_query
    await query.answer()
    logger.info(f"[BUTTON] ⏳ Processando: {button_data}")
    
    if query.data == "status":
        await status(update, context)
    elif query.data == "whois":
        context.user_data['awaiting_command'] = 'whois'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Envie o domínio para consultar:", reply_markup=reply_markup)
    elif query.data == "ping_site":
        context.user_data['awaiting_command'] = 'ping_site'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Envie o site para fazer ping:", reply_markup=reply_markup)
    elif query.data == "conversor":
        # Submenu de conversor
        keyboard = [
            [InlineKeyboardButton("USD→BRL", callback_data="conv_usd_brl"), InlineKeyboardButton("EUR→BRL", callback_data="conv_eur_brl")],
            [InlineKeyboardButton("USD→EUR", callback_data="conv_usd_eur"), InlineKeyboardButton("GBP→BRL", callback_data="conv_gbp_brl")],
            [InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="💱 Selecione a conversão (padrão 100):", reply_markup=reply_markup)
    elif query.data == "unidades":
        # Submenu de unidades
        keyboard = [
            [InlineKeyboardButton("100 km→mi", callback_data="unit_km_mi"), InlineKeyboardButton("100 kg→lb", callback_data="unit_kg_lb")],
            [InlineKeyboardButton("100 m→ft", callback_data="unit_m_ft"), InlineKeyboardButton("100 l→gal", callback_data="unit_l_gal")],
            [InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📋 Selecione a conversão:", reply_markup=reply_markup)
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
            
            msg = f"💱 Conversão:\n\n{valor} {origem.upper()} = {resultado:.2f} {destino.upper()}"
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
            msg = f"📋 Conversão:\n\n{valor} {origem} = {resultado:.2f} {destino}"
            keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=msg, reply_markup=reply_markup)
        else:
            await query.edit_message_text(text="❌ Conversão não encontrada")
    elif query.data == "traduz":
        context.user_data['awaiting_command'] = 'traduz'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Use o formato: <idioma> <texto>\nEx: es Olá mundo", reply_markup=reply_markup)
    elif query.data == "encurta":
        context.user_data['awaiting_command'] = 'encurta'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Envie a URL para encurtar:", reply_markup=reply_markup)
    elif query.data == "qrcode":
        context.user_data['awaiting_command'] = 'qrcode'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Envie o texto ou URL para gerar QR Code:", reply_markup=reply_markup)
    elif query.data == "baixar":
        context.user_data['awaiting_command'] = 'baixar'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Envie a URL do vídeo/áudio:", reply_markup=reply_markup)
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
        context.user_data['awaiting_command'] = 'audio'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Envie um arquivo de áudio com o comando: convert|cut|volume|fadein|fadeout", reply_markup=reply_markup)

    elif query.data == "clima":
        context.user_data['awaiting_command'] = 'clima'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📨 Envie o nome da cidade:", reply_markup=reply_markup)
    elif query.data == "imagem":
        context.user_data['awaiting_command'] = 'imagem'
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="🎨 Envie o prompt para gerar a imagem (texto livre).\n"
            "Ex: paisagem cyberpunk à noite com néon\n\n"
            "Com chave OpenAI no .env, usa DALL-E 3; senão usa Pollinations.",
            reply_markup=reply_markup,
        )
    elif query.data == "voltar":
        # Voltar ao menu principal
        keyboard = [
            [InlineKeyboardButton("Status", callback_data="status"), InlineKeyboardButton("Whois", callback_data="whois")],
            [InlineKeyboardButton("Ping Site", callback_data="ping_site"), InlineKeyboardButton("Conversor", callback_data="conversor")],
            [InlineKeyboardButton("Unidades", callback_data="unidades"), InlineKeyboardButton("Traduz", callback_data="traduz")],
            [InlineKeyboardButton("Encurtar URL", callback_data="encurta"), InlineKeyboardButton("QR Code", callback_data="qrcode")],
            [InlineKeyboardButton("Baixar", callback_data="baixar"), InlineKeyboardButton("Áudio", callback_data="audio")],
            [InlineKeyboardButton("Clima", callback_data="clima"), InlineKeyboardButton("Imagem", callback_data="imagem")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text="Bot online e funcionando!\n\nEscolha uma opção:", reply_markup=reply_markup)
        except Exception:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.chat.send_message(
                text="Bot online e funcionando!\n\nEscolha uma opção:",
                reply_markup=reply_markup,
            )

# 🤖 Main
def main():
    logger.info("="*70)
    logger.info("🚀 INICIANDO BOT TELEGRAM")
    logger.info(f"⏰ Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info("="*70)
    
    app = ApplicationBuilder().token(TOKEN).build()
    logger.info("✅ Bot App Builder inicializado")
    
    # Handlers dos comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("whois", whois_lookup))
    app.add_handler(CommandHandler("ping_site", ping_site))
    app.add_handler(CommandHandler("conversor", conversor))
    app.add_handler(CommandHandler("unidades", conversor_unidades))
    app.add_handler(CommandHandler("traduz", traduzir))
    app.add_handler(CommandHandler("encurta", encurtar_url))
    app.add_handler(CommandHandler("clima", clima))
    app.add_handler(CommandHandler("imagem", gerar_imagem))

    
    # Handler para capturar mensagens quando um comando está aguardando input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input_message))
    
    # Handler dos botões inline (deve ser o último!)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("✅ Todos os handlers registrados")
    logger.info("🤖 Bot aguardando mensagens...")
    logger.info("="*70)
    
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("⏹️  Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
