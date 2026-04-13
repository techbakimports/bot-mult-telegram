"""
Configurações do Bot Telegram
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Token do bot
TOKEN = os.getenv("BOT_TOKEN")

# ID do usuário autorizado
AUTHORIZED_ID = 109787324

# Opcional: geração de imagens com DALL-E 3 (https://platform.openai.com/api-keys)
# Sem chave, o bot usa Pollinations (gratuito, qualidade variável).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Opcional: clima com OpenWeatherMap
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
