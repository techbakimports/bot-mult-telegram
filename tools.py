"""
Ferramentas diversas (encurtar URL, imagens, download, clima)
"""
import asyncio
import logging
import os
from typing import Tuple

import requests
import io
import qrcode
import yt_dlp
import tempfile
import shutil
import mimetypes
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from urllib.parse import quote

from utils import is_authorized

logger = logging.getLogger(__name__)


def _gerar_imagem_bytes(prompt: str) -> Tuple[bytes, str]:
    """Retorna (bytes_png, fonte).

    Ordem de tentativa:
    1. OpenAI DALL-E 3 (se OPENAI_API_KEY existir)
    2. Pollinations AI – endpoint gratuito gen.pollinations.ai
    3. AI Horde (Stable Horde) – crowdsourced, anônimo, pode demorar
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Prompt vazio.")

    # ── 1. OpenAI (pago) ─────────────────────────────────────────────
    try:
        from config import OPENAI_API_KEY
    except ImportError:
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if api_key:
        r = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "dall-e-3",
                "prompt": prompt[:4000],
                "n": 1,
                "size": "1024x1024",
            },
            timeout=180,
        )
        if not r.ok:
            err = r.text[:500]
            raise RuntimeError(f"OpenAI: {r.status_code} — {err}")
        data = r.json()
        image_url = data["data"][0]["url"]
        img = requests.get(image_url, timeout=120)
        img.raise_for_status()
        return img.content, "DALL-E 3"

    # ── 2. Pollinations AI (gratuito, sem chave) ─────────────────────
    errors = []
    try:
        encoded = quote(prompt[:2000])
        url = (
            f"https://gen.pollinations.ai/image/{encoded}"
            f"?width=1024&height=1024&nologo=true&model=flux"
        )
        img = requests.get(url, timeout=180, allow_redirects=True)
        content_type = img.headers.get("content-type", "")
        if img.ok and ("image" in content_type or len(img.content) > 10_000):
            logger.info("Imagem gerada via Pollinations (gen.pollinations.ai)")
            return img.content, "Pollinations (flux)"
        errors.append(f"Pollinations: HTTP {img.status_code}, ct={content_type}")
    except Exception as e:
        errors.append(f"Pollinations: {e}")
        logger.warning("Pollinations falhou: %s", e)

    # ── 2b. Fallback: endpoint antigo do Pollinations ────────────────
    try:
        encoded = quote(prompt[:2000])
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1024&height=1024&nologo=true&model=flux"
        )
        img = requests.get(url, timeout=180, allow_redirects=True)
        content_type = img.headers.get("content-type", "")
        if img.ok and ("image" in content_type or len(img.content) > 10_000):
            logger.info("Imagem gerada via Pollinations (endpoint antigo)")
            return img.content, "Pollinations (flux)"
        errors.append(f"Pollinations-legacy: HTTP {img.status_code}")
    except Exception as e:
        errors.append(f"Pollinations-legacy: {e}")
        logger.warning("Pollinations legacy falhou: %s", e)

    # ── 3. AI Horde / Stable Horde (gratuito, crowdsourced) ──────────
    try:
        horde_payload = {
            "prompt": prompt[:1000],
            "params": {
                "width": 1024,
                "height": 1024,
                "steps": 25,
                "sampler_name": "k_euler_a",
                "cfg_scale": 7,
            },
            "nsfw": False,
            "models": ["stable_diffusion"],
        }
        horde_headers = {
            "Content-Type": "application/json",
            "apikey": "0000000000",  # chave anônima
        }

        # Enviar pedido
        r = requests.post(
            "https://stablehorde.net/api/v2/generate/async",
            json=horde_payload,
            headers=horde_headers,
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(f"Horde async: HTTP {r.status_code} – {r.text[:300]}")

        job_id = r.json().get("id")
        if not job_id:
            raise RuntimeError("Horde: sem job id")

        # Polling (máx ~3 min)
        import time as _time
        for _ in range(90):
            _time.sleep(4)
            check = requests.get(
                f"https://stablehorde.net/api/v2/generate/check/{job_id}",
                headers=horde_headers,
                timeout=15,
            )
            if check.ok and check.json().get("done"):
                break
        else:
            raise RuntimeError("Horde: timeout após 6 minutos")

        # Buscar resultado
        result = requests.get(
            f"https://stablehorde.net/api/v2/generate/status/{job_id}",
            headers=horde_headers,
            timeout=30,
        )
        result.raise_for_status()
        generations = result.json().get("generations", [])
        if not generations:
            raise RuntimeError("Horde: nenhuma geração retornada")

        img_url = generations[0].get("img")
        if not img_url:
            raise RuntimeError("Horde: sem URL de imagem")

        img = requests.get(img_url, timeout=120)
        img.raise_for_status()
        logger.info("Imagem gerada via AI Horde (Stable Horde)")
        return img.content, "AI Horde (Stable Diffusion)"

    except Exception as e:
        errors.append(f"AI Horde: {e}")
        logger.warning("AI Horde falhou: %s", e)

    # Nenhum serviço funcionou
    raise RuntimeError(
        "Nenhum serviço de geração de imagem disponível.\n"
        + "\n".join(f"• {err}" for err in errors)
    )


# 🖼️ /imagem
async def gerar_imagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera uma imagem a partir do prompt (OpenAI ou Pollinations)."""
    if not is_authorized(update):
        return

    status_msg = None
    try:
        if not context.args:
            await update.message.reply_text(
                "Use: /imagem <descrição>\n"
                "Ex: /imagem um gato astronauta no estilo pixel art\n\n"
                "Ou use o botão Imagem no menu e envie só o texto do prompt."
            )
            return

        prompt = " ".join(context.args).strip()
        if len(prompt) > 4000:
            await update.message.reply_text("❌ Prompt muito longo (máx. 4000 caracteres).")
            return

        status_msg = await update.message.reply_text("🎨 Gerando imagem… pode levar até 1–2 minutos.")

        loop = asyncio.get_event_loop()
        image_bytes, fonte = await loop.run_in_executor(None, lambda: _gerar_imagem_bytes(prompt))

        bio = io.BytesIO(image_bytes)
        bio.seek(0)
        caption = f"🖼️ {prompt[:900]}\n\n— {fonte}"
        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await status_msg.delete()
        except Exception:
            pass

        await update.message.reply_photo(
            photo=bio,
            caption=caption[:1024],
            reply_markup=reply_markup,
        )
        logger.info("Imagem gerada (%s chars), fonte=%s", len(prompt), fonte)

    except Exception as e:
        logger.exception("gerar_imagem: %s", e)
        err_txt = f"❌ Erro ao gerar imagem: {str(e)}"
        if status_msg:
            try:
                await status_msg.edit_text(err_txt)
                return
            except Exception:
                pass
        await update.message.reply_text(err_txt)


# 🎵 /audio
async def process_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa áudio enviado (conversão, cortar, ajustar volume, efeitos simples).

    Uso:
    - Envie/encaminhe um arquivo de áudio/video e responda com:
      /audio convert <formato>
      /audio cut <start_sec> <end_sec>
      /audio volume <dB_change>   (ex: +5 ou -3)
      /audio fadein <ms>
      /audio fadeout <ms>
    """
    if not is_authorized(update):
        return

    try:
        from pydub import AudioSegment

        msg = update.message
        # Permitir que o usuário responda ao arquivo com o comando
        file_msg = msg.reply_to_message if msg.reply_to_message else msg

        file_obj_meta = None
        if getattr(file_msg, 'document', None):
            file_obj_meta = file_msg.document
        elif getattr(file_msg, 'audio', None):
            file_obj_meta = file_msg.audio
        elif getattr(file_msg, 'voice', None):
            file_obj_meta = file_msg.voice
        elif getattr(file_msg, 'video', None):
            file_obj_meta = file_msg.video
        elif getattr(file_msg, 'video_note', None):
            file_obj_meta = file_msg.video_note

        if file_obj_meta is None:
            await msg.reply_text("❌ Envie ou responda a uma mensagem com o arquivo de áudio/video e use: /audio <ação>\nEx: /audio convert mp3")
            return

        if not context.args:
            await msg.reply_text("❌ Subcomando ausente. Use: convert|cut|volume|fadein|fadeout")
            return

        action = context.args[0].lower()

        # Baixar arquivo para temporário
        file_obj = await file_obj_meta.get_file()
        tmpdir = tempfile.mkdtemp(prefix='audio_')

        # Determinar nome do arquivo de entrada
        if getattr(file_obj_meta, 'file_name', None):
            in_name = file_obj_meta.file_name
        else:
            mime = getattr(file_obj_meta, 'mime_type', None) or ''
            ext = mimetypes.guess_extension(mime.split(';')[0]) if mime else None
            in_name = 'input' + (ext or '')

        input_path = os.path.join(tmpdir, in_name)
        await file_obj.download_to_drive(custom_path=input_path)

        # Carregar com pydub
        audio = AudioSegment.from_file(input_path)

        out_path = None

        if action == 'convert':
            if len(context.args) < 2:
                await msg.reply_text("Use: /audio convert <format>\nEx: /audio convert mp3")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return
            fmt = context.args[1].lower()
            out_path = os.path.join(tmpdir, f"output.{fmt}")
            audio.export(out_path, format=fmt)

        elif action == 'cut':
            if len(context.args) < 3:
                await msg.reply_text("Use: /audio cut <start_sec> <end_sec>\nEx: /audio cut 0 60")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return
            start = float(context.args[1]) * 1000
            end = float(context.args[2]) * 1000
            clip = audio[int(start):int(end)]
            out_path = os.path.join(tmpdir, 'output.mp3')
            clip.export(out_path, format='mp3')

        elif action == 'volume':
            if len(context.args) < 2:
                await msg.reply_text("Use: /audio volume <dB_change>\nEx: /audio volume +5")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return
            change = float(context.args[1])
            processed = audio.apply_gain(change)
            out_path = os.path.join(tmpdir, 'output.mp3')
            processed.export(out_path, format='mp3')

        elif action == 'fadein':
            if len(context.args) < 2:
                await msg.reply_text("Use: /audio fadein <ms>\nEx: /audio fadein 3000")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return
            ms = int(context.args[1])
            processed = audio.fade_in(ms)
            out_path = os.path.join(tmpdir, 'output.mp3')
            processed.export(out_path, format='mp3')

        elif action == 'fadeout':
            if len(context.args) < 2:
                await msg.reply_text("Use: /audio fadeout <ms>\nEx: /audio fadeout 3000")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return
            ms = int(context.args[1])
            processed = audio.fade_out(ms)
            out_path = os.path.join(tmpdir, 'output.mp3')
            processed.export(out_path, format='mp3')

        else:
            await msg.reply_text('❌ Ação desconhecida. Uso: convert|cut|volume|fadein|fadeout')
            shutil.rmtree(tmpdir, ignore_errors=True)
            return

        # Enviar arquivo resultante
        if out_path and os.path.exists(out_path):
            size_mb = os.path.getsize(out_path) / (1024*1024)
            if size_mb > 45:
                await msg.reply_text(f"⚠️ Arquivo grande ({size_mb:.1f} MB). O Telegram pode recusar uploads grandes.")
            with open(out_path, 'rb') as f:
                await msg.reply_document(document=f, filename=os.path.basename(out_path))

        shutil.rmtree(tmpdir, ignore_errors=True)

    except Exception as e:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
        await update.message.reply_text(f"Erro: {str(e)}\n\nObservação: O `ffmpeg` precisa estar instalado no sistema para o `pydub` funcionar corretamente.")


# 🔗 /encurta
async def encurtar_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Encurta URLs"""
    if not is_authorized(update):
        return
    
    try:
        if not context.args:
            await update.message.reply_text("Use: /encurta <url>\nEx: /encurta https://www.exemplo.com.br")
            return
        
        url = context.args[0]
        
        api_url = f"https://tinyurl.com/api-create.php?url={url}"
        response = requests.get(api_url, timeout=5)
        url_curta = response.text
        
        if url_curta.startswith('https'):
            keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"🔗 URL Encurtada:\n\n{url_curta}", reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Erro ao encurtar URL!")
    
    except Exception as e:
        await update.message.reply_text(f"Erro: {str(e)}")


# 🔳 /qrcode
async def gerar_qrcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera um QR code a partir do texto/URL informado e envia como imagem"""
    if not is_authorized(update):
        return

    try:
        if not context.args:
            await update.message.reply_text("Use: /qrcode <texto|url>\nEx: /qrcode https://t.me/seu_bot")
            return

        dados = " ".join(context.args)

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(dados)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        bio = io.BytesIO()
        img.save(bio, format='PNG')
        bio.seek(0)

        keyboard = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_photo(photo=bio, reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"Erro: {str(e)}")


# ⬇️ /baixar
async def baixar_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra menu de qualidades para download.

    Uso: /baixar <url>
    Ex: /baixar https://youtube.com/watch?v=...
    """
    if not is_authorized(update):
        return

    try:
        if not context.args:
            await update.message.reply_text("Use: /baixar <url>\nEx: /baixar https://youtube.com/watch?v=...")
            return

        url = context.args[0]
        
        # Armazenar URL no context para usar depois na callback
        context.user_data['download_url'] = url
        
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

    except Exception as e:
        await update.message.reply_text(f"Erro: {str(e)}")


async def _safe_edit_message(query, text: str):
    """Edita mensagem ignorando erro 'message is not modified'."""
    try:
        await query.edit_message_text(text)
    except Exception as e:
        # Telegram retorna 400 quando o texto não mudou
        err_str = str(e).lower()
        if "message is not modified" not in err_str:
            logger.warning("Erro ao editar mensagem: %s", e)


# Função auxiliar para fazer o download
async def fazer_download(update: Update, context: ContextTypes.DEFAULT_TYPE, qualidade: str):
    """Executa o download com a qualidade especificada e mostra progresso em tempo real."""
    if not is_authorized(update):
        return

    tmpdir = None
    try:
        url = context.user_data.get('download_url')
        if not url:
            await update.callback_query.edit_message_text("❌ URL não encontrada. Use /baixar <url> novamente.")
            return

        tmpdir = tempfile.mkdtemp(prefix='yt_dl_')
        progress_data = {
            'percentage': 0,
            'speed': 'N/A',
            'eta': 'N/A',
            'status': 'iniciando',
            'downloaded': 0,
            'total': 0,
        }
        
        # Editar mensagem inicial para mostrar que o download está começando
        await _safe_edit_message(update.callback_query, "🔄 Iniciando download...\nPor favor, aguarde...")

        def format_progress_bar(percentage: float, width: int = 15) -> str:
            """Cria uma barra de progresso visual."""
            filled = int(width * percentage / 100)
            bar = '█' * filled + '░' * (width - filled)
            return f"{bar} {percentage:.1f}%"

        def progress_hook(d):
            """Callback de progresso do yt-dlp (SÍNCRONO)."""
            if d['status'] == 'downloading':
                try:
                    # Tentar obter percentage de múltiplas fontes
                    pct = 0.0

                    # Método 1: downloaded_bytes / total_bytes
                    downloaded = d.get('downloaded_bytes', 0) or 0
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0) or 0

                    if total > 0 and downloaded > 0:
                        pct = (downloaded / total) * 100
                        progress_data['downloaded'] = downloaded
                        progress_data['total'] = total
                    else:
                        # Método 2: _percent_str
                        p = d.get('_percent_str', '0%').strip()
                        percent_str = p.replace('%', '').strip()
                        try:
                            pct = float(percent_str)
                        except (ValueError, TypeError):
                            pct = 0.0

                    progress_data['percentage'] = min(pct, 100.0)
                    progress_data['speed'] = d.get('_speed_str', 'N/A') or 'N/A'
                    progress_data['eta'] = d.get('_eta_str', 'N/A') or 'N/A'
                    progress_data['status'] = 'downloading'
                except Exception:
                    pass
            elif d['status'] == 'finished':
                progress_data['percentage'] = 100
                progress_data['status'] = 'finalizando'

        # Detectar se ffmpeg está disponível (necessário para merge de streams)
        _has_ffmpeg = shutil.which('ffmpeg') is not None

        # Definir formato baseado na qualidade escolhida
        if _has_ffmpeg:
            # Com ffmpeg: usa streams separados (melhor qualidade) + merge
            if qualidade == 'audio':
                format_str = 'bestaudio[ext=m4a]/bestaudio/best'
            elif qualidade == '360p':
                format_str = 'bestvideo[height<=360]+bestaudio/best[height<=360]/best'
            elif qualidade == '480p':
                format_str = 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
            elif qualidade == '720p':
                format_str = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
            else:
                format_str = 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
        else:
            # Sem ffmpeg: só streams pré-combinados (vídeo+áudio juntos)
            if qualidade == 'audio':
                format_str = 'bestaudio/best'
            elif qualidade == '360p':
                format_str = 'best[height<=360]/best'
            elif qualidade == '480p':
                format_str = 'best[height<=480]/best'
            elif qualidade == '720p':
                format_str = 'best[height<=720]/best'
            else:
                format_str = 'best[height<=480]/best'

        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(tmpdir, '%(title).80s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 5,
            'fragment_retries': 5,
            'progress_hooks': [progress_hook],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            },
            'restrictfilenames': True,
            'noprogress': False,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'android'],
                },
            },
        }

        if _has_ffmpeg:
            ydl_opts['merge_output_format'] = 'mp4'

        if qualidade == 'audio':
            if _has_ffmpeg:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

        # Função que executa o download em thread separada
        def run_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
            return info

        # Executar download em background
        loop = asyncio.get_event_loop()
        download_task = loop.run_in_executor(None, run_download)
        
        # Atualizar progresso a cada 3 segundos
        last_update = time.time()
        last_text = ""
        while not download_task.done():
            await asyncio.sleep(1)
            
            # Atualizar mensagem a cada 3 segundos (evita rate limit do Telegram)
            if time.time() - last_update >= 3:
                percentage = progress_data['percentage']
                bar = format_progress_bar(percentage)

                # Informação de tamanho
                size_info = ""
                if progress_data['total'] > 0:
                    dl_mb = progress_data['downloaded'] / (1024 * 1024)
                    total_mb = progress_data['total'] / (1024 * 1024)
                    size_info = f"\n📦 {dl_mb:.1f} / {total_mb:.1f} MB"

                status_text = (
                    f"⬇️ Download em progresso\n\n"
                    f"{bar}{size_info}\n\n"
                    f"⚡ Velocidade: {progress_data['speed']}\n"
                    f"⏱️ ETA: {progress_data['eta']}"
                )

                # Só editar se o texto realmente mudou
                if status_text != last_text:
                    await _safe_edit_message(update.callback_query, status_text)
                    last_text = status_text
                
                last_update = time.time()

        # Aguardar conclusão do download (captura exceções)
        info = await download_task

        # Atualizar status
        await _safe_edit_message(update.callback_query, "✅ Download concluído! Processando arquivo...")

        # Encontra arquivo gerado no tmpdir
        files = os.listdir(tmpdir)
        if not files:
            await update.callback_query.message.reply_text('❌ Falha: nenhum arquivo gerado.')
            shutil.rmtree(tmpdir, ignore_errors=True)
            return

        # Preferir arquivos com maiores tamanhos
        files_paths = [os.path.join(tmpdir, f) for f in files]
        files_paths.sort(key=lambda p: os.path.getsize(p), reverse=True)
        target = files_paths[0]

        # Aviso sobre limites do Telegram (máx 50MB para bots)
        size_mb = os.path.getsize(target) / (1024*1024)
        if size_mb > 50:
            await update.callback_query.message.reply_text(
                f"⚠️ Arquivo muito grande ({size_mb:.1f} MB).\n"
                f"O limite do Telegram para bots é 50 MB.\n"
                f"Tente com qualidade mais baixa (360p)."
            )
            shutil.rmtree(tmpdir, ignore_errors=True)
            return

        # Atualizar para "enviando"
        await update.callback_query.message.reply_text("📤 Enviando arquivo para o Telegram...")

        with open(target, 'rb') as f:
            await update.callback_query.message.reply_document(
                document=f,
                filename=os.path.basename(target),
                read_timeout=120,
                write_timeout=120,
            )

        await update.callback_query.message.reply_text("✅ Download enviado com sucesso!")
        shutil.rmtree(tmpdir, ignore_errors=True)

    except Exception as e:
        if tmpdir:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
        error_msg = str(e)
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        await update.callback_query.message.reply_text(
            f"❌ Erro no download: {error_msg}\n\n"
            f"💡 Dicas:\n"
            f"• Verifique se a URL é válida\n"
            f"• Tente com qualidade mais baixa\n"
            f"• A extração de áudio requer `ffmpeg` instalado"
        )


# 🌦️ /clima
async def clima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obtém informações de clima de uma cidade.

    Uso: /clima <cidade>
    Ex: /clima São Paulo

    Nota: Com OPENWEATHER_API_KEY usa OpenWeatherMap, senão usa open-meteo (gratuito).
    """
    if not is_authorized(update):
        return

    try:
        if not context.args:
            await update.message.reply_text("Use: /clima <cidade>\nEx: /clima São Paulo")
            return

        cidade = " ".join(context.args)

        # Tenta carregar chave da config; se não tiver, usa fallback genérico
        try:
            from config import OPENWEATHER_API_KEY
            api_key = OPENWEATHER_API_KEY
        except ImportError:
            api_key = None

        if not api_key:
            # Fallback: usar API open-meteo (sem chave)
            url = f"https://geocoding-api.open-meteo.com/v1/search?name={cidade}&count=1&language=pt&format=json"
            geo_resp = requests.get(url, timeout=5)
            geo_data = geo_resp.json()

            if not geo_data.get('results'):
                await update.message.reply_text(f"❌ Cidade '{cidade}' não encontrada.")
                return

            lat = geo_data['results'][0]['latitude']
            lon = geo_data['results'][0]['longitude']
            city_name = geo_data['results'][0]['name']

            # Buscar clima
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=auto"
            weather_resp = requests.get(weather_url, timeout=5)
            weather_data = weather_resp.json()

            current = weather_data['current']
            temp = current['temperature_2m']
            humidity = current['relative_humidity_2m']
            wind = current['wind_speed_10m']
            code = current['weather_code']

            # Weather code mapper simplificado
            code_map = {
                0: "Céu limpo",
                1: "Parcialmente nublado",
                2: "Nublado",
                3: "Muito nublado",
                45: "Neblina",
                48: "Neblina com geada",
                51: "Chuva leve",
                53: "Chuva moderada",
                55: "Chuva forte",
                61: "Chuva",
                63: "Chuva moderada",
                65: "Chuva forte",
                71: "Neve leve",
                73: "Neve",
                75: "Neve pesada",
                80: "Chuva leve intermitente",
                81: "Chuva intermitente",
                82: "Chuva forte intermitente",
                85: "Neve leve intermitente",
                86: "Neve intermediária",
                95: "Trovoada",
                96: "Trovoada com granizo",
                99: "Trovoada com granizo pesado",
            }

            condition = code_map.get(code, f"Código {code}")

            msg = f"Clima em {city_name}:\n\n"
            msg += f"Temperatura: {temp}C\n"
            msg += f"Umidade: {humidity}%\n"
            msg += f"Vento: {wind} km/h\n"
            msg += f"Condicao: {condition}"

            keyboard = [[InlineKeyboardButton("Voltar", callback_data="voltar")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(msg, reply_markup=reply_markup)
            return

        # Com chave OpenWeatherMap
        url = f"https://api.openweathermap.org/data/2.5/weather?q={cidade}&appid={api_key}&units=metric&lang=pt_br"
        response = requests.get(url, timeout=5)
        data = response.json()

        if data.get('cod') != 200:
            await update.message.reply_text(f"❌ Cidade '{cidade}' não encontrada.")
            return

        temp = data['main']['temp']
        humidity = data['main']['humidity']
        condition = data['weather'][0]['description'].capitalize()
        wind = data['wind']['speed']

        msg = f"Clima em {data['name']}, {data['sys']['country']}:\n\n"
        msg += f"Temperatura: {temp}C\n"
        msg += f"Umidade: {humidity}%\n"
        msg += f"Vento: {wind} m/s\n"
        msg += f"Condicao: {condition}"

        keyboard = [[InlineKeyboardButton("Voltar", callback_data="voltar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"Erro: {str(e)}")
