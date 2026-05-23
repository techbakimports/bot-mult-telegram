"""
Handlers para comandos de rede e sistema
"""
import asyncio
import time
import platform
from datetime import datetime, timezone

import psutil
import requests
import subprocess
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from utils import is_authorized, is_valid_host
from config import AUTHORIZED_ID


# 📊 /status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra status da VPS (restrito ao dono)"""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != AUTHORIZED_ID:
        if update.callback_query:
            await update.callback_query.answer("⛔ Acesso restrito.", show_alert=True)
        else:
            await update.message.reply_text("⛔ Acesso restrito.")
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
        url = f"https://api.whois.vu/?q={domain}"
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(url, timeout=15))

        if response.status_code == 200:
            data = response.json()
            if data.get("available") == "yes":
                output = f"Domínio {domain} está disponível para registro."
            else:
                registrar = data.get("registrar", "N/A")
                
                def format_ts(ts):
                    if not ts: return "N/A"
                    try:
                        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                    except (ValueError, TypeError, OSError):
                        return "N/A"
                
                created = format_ts(data.get("created"))
                updated = format_ts(data.get("updated"))
                expires = format_ts(data.get("expires"))
                
                # Coleta os 3 primeiros status se existirem
                statuses = data.get("statuses", [])
                status_str = ", ".join(statuses[:3]) if statuses else "N/A"
                if len(statuses) > 3:
                    status_str += "..."
                
                output = (
                    f"Registrar: {registrar}\n"
                    f"Status: {status_str}\n"
                    f"Criado: {created}\n"
                    f"Atualizado: {updated}\n"
                    f"Expira: {expires}\n"
                )
        else:
             output = f"Erro na consulta: HTTP {response.status_code}"

        voltar = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]])
        await update.message.reply_text(f"🔎 Whois ({domain}):\n\n{output}", reply_markup=voltar)

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

    if not is_valid_host(site):
        await update.message.reply_text("❌ Endereço inválido. Use um domínio ou IP válido.\nEx: /ping_site google.com")
        return

    try:
        param = '-n' if platform.system() == 'Windows' else '-c'
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
