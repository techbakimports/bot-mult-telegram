"""
Handlers para comandos de rede e sistema
"""
import time
import platform
import psutil
import subprocess
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from utils import is_authorized


# 📊 /status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra status da VPS"""
    if not is_authorized(update):
        return

    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_hours = round(uptime_seconds / 3600, 2)

    msg = (
        f"📊 Status da VPS\n\n"
        f"CPU: {cpu}%\n"
        f"RAM: {ram}%\n"
        f"Uptime: {uptime_hours} horas\n"
        f"Sistema: {platform.system()}"
    )

    # Verifica se vem de um callback (inline button)
    if update.callback_query:
        keyboard = [[InlineKeyboardButton("Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text=msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg)


# 🔎 /whois
async def whois_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executa whois de um domínio"""
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text("Use: /whois <dominio>")
        return

    domain = context.args[0]

    try:
        import requests
        url = f"https://api.hackertarget.com/whois/?q={domain}"
        response = requests.get(url, timeout=15)
        output = response.text

        if len(output) > 4000:
            output = output[:4000] + "\n\n... (cortado)"

        await update.message.reply_text(f"🔎 Whois:\n\n{output}")

    except Exception as e:
        await update.message.reply_text(f"Erro: {str(e)}")


# 🌍 /ping_site
async def ping_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Faz ping em um site"""
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text("Use: /ping_site <site>")
        return

    site = context.args[0]

    try:
        import os
        param = '-n' if os.name == 'nt' else '-c'
        result = subprocess.run(
            ["ping", param, "4", site],
            capture_output=True,
            text=True,
            timeout=10
        )

        output = result.stdout

        if len(output) > 4000:
            output = output[:4000] + "\n\n... (cortado)"

        await update.message.reply_text(f"🌍 Ping Result:\n\n{output}")

    except Exception as e:
        await update.message.reply_text(f"Erro: {str(e)}")
