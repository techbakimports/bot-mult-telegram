"""
Funções utilitárias do bot
"""
import re

from telegram import Update
from config import AUTHORIZED_ID


def is_authorized(update: Update) -> bool:
    """Verifica se o usuário está autorizado"""
    user = update.effective_user
    if user is None or user.id != AUTHORIZED_ID:
        return False
    return True


def is_valid_host(host: str) -> bool:
    """Valida se o host é um domínio ou IP válido (sem flags ou caracteres perigosos)."""
    # Aceita domínios (ex: google.com) e IPs (ex: 8.8.8.8)
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]{0,253}[a-zA-Z0-9])?$'
    return bool(re.match(pattern, host))
