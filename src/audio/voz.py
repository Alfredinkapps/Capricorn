import os
import re
import math
import time
import json
import zipfile
import hashlib
import asyncio
import urllib.request
from collections import deque

import requests
import numpy as np
import sounddevice as sd
import pygame
import edge_tts
import speech_recognition as sr

from core.config import PASTA_PROJETO, PASTA_CACHE
from core.logger import obter_logger
from ui.hud import CapriHUD
from audio.comandos import extrair_comando_apos_nome, normalizar_frase

log = obter_logger("voz")

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    VOSK_DISPONIVEL = True
except ImportError:
    Model = None
    KaldiRecognizer = None
    VOSK_DISPONIVEL = False

PREFERIR_STT_OFFLINE = True
USAR_MODELO_VOSK_GRANDE = False
VOZ_FALLBACK = "pt-BR-FranciscaNeural"

RESPOSTAS_CHAMADA = [
    "Oie.",
    "Fala.",
    "Diga lá.",
    "Tô ouvindo, fala aí.",
]

SESSAO_HTTP = requests.Session()
_REGEX_NOME_CACHE = re.compile(r"[^a-zA-Z0-9]")
_MODELO_VOSK_MEMORIA = None
_VOSK_FALHOU_CARGA = False


def obter_modelo_vosk():
    """Carrega o modelo Vosk na RAM uma única vez (priorizando bin/, depois data/cache/)."""
    global _MODELO_VOSK_MEMORIA, _VOSK_FALHOU_CARGA

    if not VOSK_DISPONIVEL or Model is None or _VOSK_FALHOU_CARGA:
        return None
    if _MODELO_VOSK_MEMORIA is not None:
        return _MODELO_VOSK_MEMORIA

    if USAR_MODELO_VOSK_GRANDE:
        nome_pasta = "vosk-model-pt-fb-v0.1.1-20220516_2113"
    else:
        nome_pasta = "vosk-model-small-pt-0.3"
    url_modelo = f"https://alphacephei.com/vosk/models/{nome_pasta}.zip"

    # 1. Procura primeiro em bin/ (pacote portátil), depois em data/cache/ e no cache legado da raiz
    candidatos = [
        os.path.join(PASTA_PROJETO, "bin", nome_pasta),
        os.path.join(PASTA_CACHE, nome_pasta),
        os.path.join(PASTA_PROJETO, "cache", nome_pasta),
    ]
    pasta_modelo = next((p for p in candidatos if os.path.isdir(p)), None)

    # 2. Se não encontrou em nenhum local, baixa e extrai em data/cache/
    if pasta_modelo is None:
        os.makedirs(PASTA_CACHE, exist_ok=True)
        pasta_modelo = os.path.join(PASTA_CACHE, nome_pasta)
        caminho_zip = os.path.join(PASTA_CACHE, "vosk_download.zip")
        try:
            log.info("Baixando modelo Vosk '%s' pela 1ª vez...", nome_pasta)
            urllib.request.urlretrieve(url_modelo, caminho_zip)
            with zipfile.ZipFile(caminho_zip, "r") as zip_ref:
                zip_ref.extractall(PASTA_CACHE)
            if os.path.exists(caminho_zip):
                os.remove(caminho_zip)
            log.info("Modelo Vosk instalado com sucesso em %s", pasta_modelo)
        except Exception as e:
            log.warning("Falha ao baixar modelo Vosk: %s", e)
            _VOSK_FALHOU_CARGA = True
            return None

    # 3. Instancia o modelo na RAM e retorna
    try:
        log.info("Carregando modelo Vosk em memória: %s", pasta_modelo)
        _MODELO_VOSK_MEMORIA = Model(pasta_modelo)
        return _MODELO_VOSK_MEMORIA
    except Exception as e:
        log.warning("Falha ao inicializar modelo Vosk: %s", e)
        _VOSK_FALHOU_CARGA = True
        return None


def transcrever_offline_vosk(bytes_audio: bytes, taxa_amostragem: int = 16000) -> str:
    """Transcreve o áudio localmente de forma estável testando até 3 hipóteses."""
    modelo_v = obter_modelo_vosk()
    if modelo_v is None or not VOSK_DISPONIVEL or KaldiRecognizer is None:
        return ""

    try:
        rec = KaldiRecognizer(modelo_v, taxa_amostragem)
        rec.SetMaxAlternatives(3)
        rec.AcceptWaveform(bytes_audio)
        res = json.loads(rec.FinalResult())

        alts = res.get("alternatives", [])
        if alts:
            opcoes = [a.get("text", "").strip() for a in alts if a.get("text", "").strip()]
            for op in opcoes:
                chamou, _ = extrair_comando_apos_nome(op)
                if chamou:
                    log.info("[Vosk Offline]: '%s'", op)
                    return op
            if opcoes:
                log.info("[Vosk Offline]: '%s'", opcoes[0])
                return opcoes[0]

        texto = res.get("text", "").strip()
        if texto:
            log.info("[Vosk Offline]: '%s'", texto)
        return texto
    except Exception as e:
        log.warning("Erro na transcrição Vosk: %s", e)
        return ""


async def _gerar_audio_nativo(texto: str, arquivo_saida: str):
    comunicador = edge_tts.Communicate(texto, VOZ_FALLBACK, rate="+4%")
    await comunicador.save(arquivo_saida)


def gerar_voz_fish_audio(hud: CapriHUD, texto: str, arquivo_saida: str) -> bool:
    chave_limpa = hud.config.get("fish_api_key", "").strip()
    id_limpo = hud.config.get("fish_voice_id", "").strip().rstrip("/").split("/")[-1]
    if not chave_limpa or not id_limpo:
        return False

    url = "https://api.fish.audio/v1/tts"
    headers = {
        "Authorization": f"Bearer {chave_limpa}",
        "Content-Type": "application/json",
        "model": "s2.1-pro-free",
    }
    payload = {
        "text": texto.strip(),
        "reference_id": id_limpo,
        "format": "mp3",
        "mp3_bitrate": 128,
        "normalize": True,
        "latency": "balanced",
    }
    try:
        resp = SESSAO_HTTP.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(arquivo_saida, "wb") as f:
                f.write(resp.content)
            return True
        return False
    except Exception as e:
        log.warning("Erro de conexão Fish Audio: %s", e)
        return False


def _obter_caminho_audio(hud: CapriHUD, texto_limpo: str, usar_cache: bool) -> str:
    """Retorna caminho fixo em data/cache/ para falas cacheadas ou arquivo temporário reutilizável."""
    if not usar_cache:
        os.makedirs(PASTA_CACHE, exist_ok=True)
        return os.path.join(PASTA_CACHE, "_fala_temp.mp3")

    id_voz = hud.config.get("fish_voice_id", "").strip().rstrip("/").split("/")[-1]
    pasta_voz = f"voz_{id_voz[:12]}" if id_voz else "voz_padrao"
    pasta_destino = os.path.join(PASTA_CACHE, pasta_voz)
    os.makedirs(pasta_destino, exist_ok=True)

    prefixo = _REGEX_NOME_CACHE.sub("_", texto_limpo.lower())[:35].strip("_") or "fala"
    hash_texto = hashlib.md5(texto_limpo.lower().encode("utf-8")).hexdigest()[:10]
    return os.path.join(pasta_destino, f"{prefixo}_{hash_texto}.mp3")


def falar(hud: CapriHUD, texto: str, usar_cache: bool = True):
    """Exibe a resposta formatada no Balão de Fala e reproduz a versão limpa por voz."""
    texto_exibicao = (texto or "").strip()
    if not texto_exibicao:
        return

    log.info("CAPRI: %s", texto_exibicao)

    if hasattr(hud, "mostrar_balao_fala"):
        hud.mostrar_balao_fala(texto_exibicao)

    tem_codigo = "```" in texto_exibicao
    texto_sem_codigo = re.sub(
        r"```.*?```", " Enviei o código no balão de fala. ", texto_exibicao, flags=re.DOTALL
    )
    texto_fala = re.sub(r"[*_`#]+", "", texto_sem_codigo)
    texto_fala = re.sub(r"\s+", " ", texto_fala).strip()
    if not texto_fala and tem_codigo:
        texto_fala = "Enviei o código pronto no balão de fala."

    hud.atualizar_estado("FALANDO...", "#FF0055", f"CAPRI: {texto_fala}")

    if getattr(hud, "voz_mutada", False):
        time.sleep(1.0)
        return

    arquivo_audio = _obter_caminho_audio(hud, texto_fala, usar_cache=usar_cache)

    try:
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        tem_cache_disco = (
            usar_cache
            and os.path.exists(arquivo_audio)
            and os.path.getsize(arquivo_audio) > 500
        )

        if not tem_cache_disco:
            try:
                if not gerar_voz_fish_audio(hud, texto_fala, arquivo_audio):
                    asyncio.run(_gerar_audio_nativo(texto_fala, arquivo_audio))
            except PermissionError:
                # Fallback caso o Windows ainda segure o handle do arquivo temporário
                arquivo_audio = os.path.join(PASTA_CACHE, f"_fala_temp_{int(time.time() * 1000)}.mp3")
                if not gerar_voz_fish_audio(hud, texto_fala, arquivo_audio):
                    asyncio.run(_gerar_audio_nativo(texto_fala, arquivo_audio))

        pygame.mixer.music.load(arquivo_audio)
        pygame.mixer.music.play()
        relogio = pygame.time.Clock()
        t_inicio = time.time()
        tem_cmd_fn = getattr(hud, "tem_comando_texto", lambda: False)

        while pygame.mixer.music.get_busy() and hud.rodando and not getattr(hud, "voz_mutada", False):
            if tem_cmd_fn():
                pygame.mixer.music.stop()
                break
            t = time.time() - t_inicio
            cadencia_silaba = abs(math.sin(t * 11.5)) * abs(math.cos(t * 4.2))
            if cadencia_silaba < 0.16:
                hud.nivel_voz = 0.08
            else:
                hud.nivel_voz = min(1.0, cadencia_silaba * 1.15 + np.random.uniform(0.0, 0.15))
            relogio.tick(22)

        hud.nivel_voz = 0.0
        pygame.mixer.music.unload()
    except Exception as e:
        hud.nivel_voz = 0.0
        log.warning("Erro na reprodução de voz: %s", e)


def ouvir_microfone_com_hud(
    hud: CapriHUD, reconhecedor: sr.Recognizer, aguardando_comando: bool = False
) -> str:
    if VOSK_DISPONIVEL and _MODELO_VOSK_MEMORIA is None and not _VOSK_FALHOU_CARGA:
        obter_modelo_vosk()

    taxa_amostragem = 16000
    bloco = 1600  # 0.1s
    limiar_voz = 340
    blocos_espera_max = 65 if aguardando_comando else 38
    blocos_silencio_fim = 9 if aguardando_comando else 7
    blocos_duracao_max = 85

    buffer_pre_fala = deque(maxlen=5)
    quadros_fala = []
    falando = False
    blocos_silencio = 0

    hud.nivel_voz = 0.0
    cor_ouvindo = getattr(hud, "ACCENT_LIME", "#00FF66")
    if aguardando_comando:
        hud.atualizar_estado("OUVINDO VOCÊ...", cor_ouvindo)

    tem_cmd_fn = getattr(hud, "tem_comando_texto", lambda: False)

    try:
        with sd.InputStream(samplerate=taxa_amostragem, channels=1, dtype="int16") as stream:
            for i in range(blocos_espera_max + blocos_duracao_max):
                if (
                    not hud.rodando
                    or hud.pausada
                    or hud.reiniciar_ia
                    or tem_cmd_fn()
                    or (not aguardando_comando and getattr(hud, "forcar_escuta_voz", False))
                ):
                    hud.nivel_voz = 0.0
                    return ""

                dados, _ = stream.read(bloco)
                copia = dados.copy()
                pico = int(np.max(np.abs(copia)))
                hud.nivel_voz = min(1.0, pico / 2500.0) if aguardando_comando else 0.0

                if not falando:
                    buffer_pre_fala.append(copia)
                    if pico > limiar_voz:
                        falando = True
                        quadros_fala.extend(buffer_pre_fala)
                        blocos_silencio = 0
                    elif i >= blocos_espera_max:
                        hud.nivel_voz = 0.0
                        return ""
                else:
                    quadros_fala.append(copia)
                    if pico < limiar_voz:
                        blocos_silencio += 1
                        if blocos_silencio >= blocos_silencio_fim:
                            break
                    else:
                        blocos_silencio = 0
                    if len(quadros_fala) >= blocos_duracao_max:
                        break

        hud.nivel_voz = 0.0
        if not quadros_fala:
            return ""

        gravacao_1d = np.concatenate(quadros_fala, axis=0).flatten().astype(np.float32)
        del quadros_fala

        pico_max = np.max(np.abs(gravacao_1d))
        if pico_max > 0:
            ganho = min(3.5, 24000.0 / pico_max)
            gravacao_1d = np.clip(gravacao_1d * ganho, -32768.0, 32767.0)

        bytes_pcm = gravacao_1d.astype(np.int16).tobytes()
        del gravacao_1d

        hud.atualizar_estado("TRANSCREVENDO...", "#F59E0B")
        usar_offline = hud.config.get("stt_offline", PREFERIR_STT_OFFLINE)
        ja_tentou_vosk = False

        if usar_offline and VOSK_DISPONIVEL:
            ja_tentou_vosk = True
            texto_offline = transcrever_offline_vosk(bytes_pcm, taxa_amostragem)
            if texto_offline:
                return normalizar_frase(texto_offline)

        try:
            audio_data = sr.AudioData(bytes_pcm, taxa_amostragem, 2)
            texto_bruto = reconhecedor.recognize_google(audio_data, language="pt-BR")  # type: ignore
            return normalizar_frase(texto_bruto)
        except sr.UnknownValueError:
            return ""
        except Exception as e:
            log.debug("Fallback de transcrição Google -> Vosk: %s", e)
            if not ja_tentou_vosk and VOSK_DISPONIVEL:
                texto_fallback = transcrever_offline_vosk(bytes_pcm, taxa_amostragem)
                return normalizar_frase(texto_fallback)
            return ""

    except Exception as e:
        hud.nivel_voz = 0.0
        log.warning("Aviso de áudio no microfone: %s", e)
        return ""