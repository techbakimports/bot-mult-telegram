# bot (Telegram)

## Objetivo
Bot Telegram Python multifuncional: ferramentas de rede, download de mídia, geração de imagens, conversão de áudio/imagem, clima, carteira de gastos com OCR.

## Stack
- Python 3.13 + python-telegram-bot 20.3 (async/await)
- Download: yt-dlp (YouTube/outros)
- Áudio: pydub, audioop-lts
- Imagem: Pillow, qrcode
- OCR: easyocr
- Banco: SQLite (gastos por usuário)
- APIs externas: Pollinations AI / OpenAI DALL-E 3, Open-Meteo / OpenWeatherMap, is.gd

## Dependências
```bash
# Ativar venv primeiro
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Requer ffmpeg instalado no sistema (para yt-dlp e pydub)
```

## Comando de execução
```bash
python main.py
```

## Variáveis de ambiente (.env)
```
BOT_TOKEN=          # obrigatório
GEMINI_API_KEY=     # presente mas não usado ativamente
YOUTUBE_COOKIES_FILE=  # opcional (path para cookies.json)
```

Em `config.py`:
```
AUTHORIZED_ID=109787324   # ID do usuário autorizado (hardcoded)
OPENAI_API_KEY=           # opcional (DALL-E 3)
OPENWEATHER_API_KEY=      # opcional (clima premium)
```

## Estrutura de arquivos
- `main.py` — inicializa bot, registra handlers, inicia polling
- `config.py` — variáveis de ambiente e configurações
- `handlers.py` — status VPS, whois, ping
- `tools.py` — encurtar URL, QR code, download, áudio, clima, imagens
- `button_handler.py` — menu inline e callbacks
- `wallet.py` — carteira de gastos com SQLite e OCR
- `gastos/` — banco SQLite por usuário (`<user_id>.db`)
- `cookies.json` — cookies YouTube (não commitar)

## Comandos disponíveis no bot
`/start` `/status` `/whois` `/ping_site` `/encurta` `/qrcode` `/baixar` `/audio` `/clima` `/imagem` `/conv_img` + sistema de carteira

## Regras
- Limite de upload Telegram: 50MB — não remover a validação de tamanho
- ffmpeg precisa estar no PATH do sistema
- Múltiplos usuários suportados; dados isolados por `user_id` no SQLite
- Nunca commitar `cookies.json` nem `.env`
