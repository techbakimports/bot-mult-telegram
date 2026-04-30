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

# Opcional: arquivo de cookies exportado do navegador para bypass do YouTube
# Exporte com extensão "Get cookies.txt LOCALLY" e coloque o caminho aqui.
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "")

# Navegador para extrair cookies automaticamente quando YOUTUBE_COOKIES_FILE não está definido.
# Opções: chrome, edge, firefox, brave  (padrão: edge)
YOUTUBE_COOKIES_BROWSER = os.getenv("YOUTUBE_COOKIES_BROWSER", "edge")
