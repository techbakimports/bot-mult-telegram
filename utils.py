"""
Funções utilitárias do bot
"""
from telegram import Update
from config import AUTHORIZED_ID


def is_authorized(update: Update) -> bool:
    """Verifica se o usuário está autorizado"""
    return update.effective_user.id == AUTHORIZED_ID
