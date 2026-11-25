import os
import re
import math
import time
import json
import queue
import zipfile
import hashlib
import asyncio
import threading
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

# Modelos testados em ordem no header 'model' do Fish Audio (None = padrão do servidor)
FISH_MODELS_FALLBACK: tuple[str | None, ...] = ("s2.1-pro-free", "s1", "speech-1.6", None)

# Limites do cache LRU de áudios reutilizáveis (nunca apaga modelo Vosk nem arquivo temporário)
MAX_ARQUIVOS_CACHE_AUDIO = 100
MAX_MB_CACHE_AUDIO = 35.0
SLOTS_STREAM_AUDIO = 4

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
_LOCK_LIMPEZA_CACHE = threading.Lock()
_FISH_MODEL_ATIVO: str | None = "s2.1-pro-free"


def _garantir_mixer_audio(forcar_reinicio: bool = False) -> bool:
    """Garante que o pygame.mixer esteja inicializado antes de carregar ou tocar qualquer áudio."""
    try:
        if forcar_reinicio and pygame.mixer.get_init():
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            pygame.mixer.quit()

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        return True
    except Exception as e:
        log.warning("Falha ao inicializar pygame.mixer: %s", e)
        return False


def _limpar_cache_audio_excedente(
    max_arquivos: int = MAX_ARQUIVOS_CACHE_AUDIO,
    max_mb: float = MAX_MB_CACHE_AUDIO,
) -> None:
    """Remove os .mp3 mais antigos em data/cache/voz_*/ mantendo o cache abaixo do teto LRU."""
    if not _LOCK_LIMPEZA_CACHE.acquire(blocking=False):
        return
    try:
        if not os.path.isdir(PASTA_CACHE):
            return

        arquivos: list[tuple[float, int, str]] = []
        tamanho_total = 0

        for nome_sub in os.listdir(PASTA_CACHE):
            if not nome_sub.startswith("voz_"):
                continue
            pasta_voz = os.path.join(PASTA_CACHE, nome_sub)
            if not os.path.isdir(pasta_voz):
                continue
            for nome_arq in os.listdir(pasta_voz):
                if not nome_arq.lower().endswith(".mp3"):
                    continue
                caminho = os.path.join(pasta_voz, nome_arq)
                try:
                    st = os.stat(caminho)
                    arquivos.append((st.st_mtime, st.st_size, caminho))
                    tamanho_total += st.st_size
                except OSError:
                    continue

        limite_bytes = int(max_mb * 1024 * 1024)
        if len(arquivos) <= max_arquivos and tamanho_total <= limite_bytes:
            return

        arquivos.sort(key=lambda item: item[0])
        removidos = 0
        total_atual = len(arquivos)

        for _, tam, caminho in arquivos:
            if total_atual <= max_arquivos and tamanho_total <= limite_bytes:
                break
            try:
                os.remove(caminho)
                tamanho_total -= tam
                total_atual -= 1
                removidos += 1
            except OSError:
                continue

        if removidos > 0:
            log.info(
                "Cache LRU de áudio limpo: %d arquivo(s) antigo(s) removido(s) (restantes: %d, %.1f MB).",
                removidos,
                total_atual,
                tamanho_total / (1024 * 1024),
            )
    except Exception as e:
        log.warning("Aviso na limpeza do cache de áudio: %s", e)
    finally:
        _LOCK_LIMPEZA_CACHE.release()


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
    url_modelo = f"[https://alphacephei.com/vosk/models/](https://alphacephei.com/vosk/models/){nome_pasta}.zip"

    candidatos = [
        os.path.join(PASTA_PROJETO, "bin", nome_pasta),
        os.path.join(PASTA_CACHE, nome_pasta),
        os.path.join(PASTA_PROJETO, "cache", nome_pasta),
    ]
    pasta_modelo = next((p for p in candidatos if os.path.isdir(p)), None)

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


def _extrair_fish_id(valor_bruto: str) -> str:
    """Extrai o reference_id limpo mesmo se o usuário colou URL completa com query string."""
    texto = str(valor_bruto or "").strip()
    if not texto:
        return ""
    texto = texto.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if "/" in texto:
        texto = texto.split("/")[-1]
    return texto.strip()


def _extrair_fish_key(valor_bruto: str) -> str:
    chave = str(valor_bruto or "").strip()
    if chave.lower().startswith("bearer "):
        chave = chave[7:].strip()
    return chave


async def _gerar_audio_nativo(texto: str, arquivo_saida: str) -> None:
    comunicador = edge_tts.Communicate(texto, VOZ_FALLBACK, rate="+4%")
    await comunicador.save(arquivo_saida)


def gerar_voz_fish_audio(hud: CapriHUD, texto: str, arquivo_saida: str) -> bool:
    """Gera áudio via Fish Audio API testando modelos válidos (s1 -> speech-1.6 -> padrão) com log claro."""
    global _FISH_MODEL_ATIVO

    chave_limpa = _extrair_fish_key(str(hud.config.get("fish_api_key", "")))
    id_limpo = _extrair_fish_id(str(hud.config.get("fish_voice_id", "")))
    if not chave_limpa or not id_limpo:
        return False

    url = "https://api.fish.audio/v1/tts"
    payload = {
        "text": texto.strip(),
        "reference_id": id_limpo,
        "format": "mp3",
        "mp3_bitrate": 128,
        "normalize": True,
        "latency": "balanced",
    }

    modelos_ordem: list[str | None] = [_FISH_MODEL_ATIVO] + [
        m for m in FISH_MODELS_FALLBACK if m != _FISH_MODEL_ATIVO
    ]

    for modelo in modelos_ordem:
        headers = {
            "Authorization": f"Bearer {chave_limpa}",
            "Content-Type": "application/json",
        }
        if modelo:
            headers["model"] = modelo

        try:
            resp = SESSAO_HTTP.post(url, json=payload, headers=headers, timeout=15)
            content_type = resp.headers.get("Content-Type", "").lower()

            if resp.status_code == 200 and len(resp.content) > 500 and "json" not in content_type:
                with open(arquivo_saida, "wb") as f:
                    f.write(resp.content)
                _FISH_MODEL_ATIVO = modelo
                return True

            detalhe = resp.text[:220].replace("\n", " ").strip()
            log.warning(
                "Fish Audio falhou (model=%s, HTTP %d): %s",
                modelo or "padrao",
                resp.status_code,
                detalhe or f"content-type={content_type}, bytes={len(resp.content)}",
            )

            # Erros definitivos de credencial, saldo ou ID inexistente não precisam tentar outro modelo
            if resp.status_code in (401, 403, 404):
                return False
        except Exception as e:
            log.warning("Erro de conexão Fish Audio (model=%s): %s", modelo or "padrao", e)
            return False

    return False


def _sintetizar_para_arquivo(
    hud: CapriHUD,
    texto: str,
    arquivo_destino: str,
    evitar_cache_no_fallback: bool = False,
) -> str:
    """Sintetiza o texto (Fish Audio -> Edge TTS fallback) sem gravar fallback no cache do Fish."""
    def _executar(destino: str) -> str:
        if gerar_voz_fish_audio(hud, texto, destino):
            return destino
        destino_fallback = (
            os.path.join(PASTA_CACHE, "_fala_temp.mp3")
            if evitar_cache_no_fallback and "_fala_temp" not in os.path.basename(destino)
            else destino
        )
        try:
            asyncio.run(_gerar_audio_nativo(texto, destino_fallback))
        except Exception as e:
            log.warning("Fallback Edge TTS também falhou: %s", e)
            raise
        return destino_fallback

    try:
        alvo = _executar(arquivo_destino)
    except PermissionError:
        alt = os.path.join(PASTA_CACHE, f"_fala_temp_{int(time.time() * 1000)}.mp3")
        alvo = _executar(alt)

    if not os.path.exists(alvo) or os.path.getsize(alvo) <= 200:
        raise RuntimeError(f"Arquivo de áudio vazio ou ausente após síntese: {alvo}")
    return alvo


def _dividir_em_frases(texto: str, max_chars: int = 210) -> list[str]:
    """Quebra respostas longas em blocos naturais por frase para reduzir a latência inicial da fala."""
    limpo = re.sub(r"\s+", " ", (texto or "").strip())
    if not limpo:
        return []

    partes_brutas = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", limpo) if p.strip()]
    if not partes_brutas:
        return [limpo]

    expandidas: list[str] = []
    for p in partes_brutas:
        if len(p) <= max_chars:
            expandidas.append(p)
            continue
        sub_partes = [s.strip() for s in re.split(r"(?<=[,;:])\s+", p) if s.strip()]
        atual = ""
        for sub in sub_partes:
            if not atual:
                atual = sub
            elif len(atual) + 1 + len(sub) <= max_chars:
                atual = f"{atual} {sub}"
            else:
                expandidas.append(atual)
                atual = sub
        if atual:
            expandidas.append(atual)

    blocos: list[str] = []
    for frag in expandidas:
        if blocos and len(frag) < 28 and len(blocos[-1]) + 1 + len(frag) <= max_chars + 40:
            blocos[-1] = f"{blocos[-1]} {frag}"
        elif blocos and len(blocos[-1]) < 28 and len(blocos[-1]) + 1 + len(frag) <= max_chars + 40:
            blocos[-1] = f"{blocos[-1]} {frag}"
        else:
            blocos.append(frag)

    return blocos


def _obter_caminho_audio(hud: CapriHUD, texto_limpo: str, usar_cache: bool) -> str:
    """Retorna caminho fixo em data/cache/ para falas cacheadas ou arquivo temporário reutilizável."""
    if not usar_cache:
        os.makedirs(PASTA_CACHE, exist_ok=True)
        return os.path.join(PASTA_CACHE, "_fala_temp.mp3")

    id_voz = _extrair_fish_id(str(hud.config.get("fish_voice_id", "")))
    pasta_voz = f"voz_{id_voz[:12]}" if id_voz else "voz_padrao"
    pasta_destino = os.path.join(PASTA_CACHE, pasta_voz)
    os.makedirs(pasta_destino, exist_ok=True)

    prefixo = _REGEX_NOME_CACHE.sub("_", texto_limpo.lower())[:35].strip("_") or "fala"
    hash_texto = hashlib.md5(texto_limpo.lower().encode("utf-8")).hexdigest()[:10]
    return os.path.join(pasta_destino, f"{prefixo}_{hash_texto}.mp3")


def _reproduzir_arquivo_com_lipsync(hud: CapriHUD, arquivo_audio: str) -> bool:
    """Reproduz um arquivo .mp3 com lip-sync no HUD. Retorna False se foi interrompido."""
    if not _garantir_mixer_audio():
        return False

    try:
        pygame.mixer.music.load(arquivo_audio)
        pygame.mixer.music.play()
    except pygame.error as e:
        log.warning("Erro ao tocar no pygame.mixer (%s) — tentando reinicializar dispositivo...", e)
        if not _garantir_mixer_audio(forcar_reinicio=True):
            return False
        pygame.mixer.music.load(arquivo_audio)
        pygame.mixer.music.play()

    relogio = pygame.time.Clock()
    t_inicio = time.time()
    tem_cmd_fn = getattr(hud, "tem_comando_texto", lambda: False)
    interrompido = False

    while pygame.mixer.music.get_busy():
        if (
            not hud.rodando
            or getattr(hud, "voz_mutada", False)
            or not bool(hud.config.get("voz_ativa", True))
            or tem_cmd_fn()
        ):
            pygame.mixer.music.stop()
            interrompido = True
            break
        t = time.time() - t_inicio
        cadencia_silaba = abs(math.sin(t * 11.5)) * abs(math.cos(t * 4.2))
        if cadencia_silaba < 0.16:
            hud.nivel_voz = 0.08
        else:
            hud.nivel_voz = min(
                1.0, cadencia_silaba * 1.15 + float(np.random.uniform(0.0, 0.15))
            )
        relogio.tick(22)

    hud.nivel_voz = 0.0
    try:
        pygame.mixer.music.unload()
    except Exception:
        pass
    return not interrompido


def _falar_em_fila_por_frase(hud: CapriHUD, blocos: list[str]) -> None:
    """
    Reproduz a primeira frase assim que pronta enquanto sintetiza a próxima em paralelo.
    Usa 4 slots rotativos (_fala_stream_0..3.mp3) com fila de tamanho 1 para evitar conflito de arquivo.
    """
    os.makedirs(PASTA_CACHE, exist_ok=True)
    fila_audios: queue.Queue[str | None] = queue.Queue(maxsize=1)
    cancelar = threading.Event()
    tem_cmd_fn = getattr(hud, "tem_comando_texto", lambda: False)

    def _produtor() -> None:
        try:
            for idx, frase in enumerate(blocos):
                if (
                    cancelar.is_set()
                    or not hud.rodando
                    or getattr(hud, "voz_mutada", False)
                    or tem_cmd_fn()
                ):
                    break
                slot = os.path.join(PASTA_CACHE, f"_fala_stream_{idx % SLOTS_STREAM_AUDIO}.mp3")
                try:
                    caminho_pronto = _sintetizar_para_arquivo(hud, frase, slot)
                except Exception as e:
                    log.warning("Falha ao sintetizar frase #%d: %s", idx + 1, e)
                    continue

                if cancelar.is_set():
                    break

                while not cancelar.is_set():
                    try:
                        fila_audios.put(caminho_pronto, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        finally:
            while True:
                try:
                    fila_audios.put(None, timeout=0.1)
                    break
                except queue.Full:
                    if cancelar.is_set():
                        try:
                            fila_audios.get_nowait()
                        except queue.Empty:
                            pass

    t_prod = threading.Thread(target=_produtor, daemon=True)
    t_prod.start()

    try:
        while True:
            if not hud.rodando or getattr(hud, "voz_mutada", False) or tem_cmd_fn():
                cancelar.set()
                break
            try:
                proximo_arquivo = fila_audios.get(timeout=0.15)
            except queue.Empty:
                if not t_prod.is_alive():
                    break
                continue

            if proximo_arquivo is None:
                break

            continuar = _reproduzir_arquivo_com_lipsync(hud, proximo_arquivo)
            if not continuar:
                cancelar.set()
                break
    finally:
        cancelar.set()
        while True:
            try:
                fila_audios.get_nowait()
            except queue.Empty:
                break
        t_prod.join(timeout=1.0)
        hud.nivel_voz = 0.0


def falar(hud: CapriHUD, texto: str, usar_cache: bool = True) -> None:
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

    if getattr(hud, "voz_mutada", False) or not bool(hud.config.get("voz_ativa", True)):
        time.sleep(0.8)
        return

    try:
        if _garantir_mixer_audio():
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass

        # Respostas dinâmicas com 2+ frases usam TTS em fila para falar quase imediatamente
        tts_streaming_ativo = bool(hud.config.get("tts_por_frase", True))
        if not usar_cache and tts_streaming_ativo:
            blocos = _dividir_em_frases(texto_fala)
            if len(blocos) >= 2:
                _falar_em_fila_por_frase(hud, blocos)
                return

        arquivo_audio = _obter_caminho_audio(hud, texto_fala, usar_cache=usar_cache)
        tem_cache_disco = (
            usar_cache
            and os.path.exists(arquivo_audio)
            and os.path.getsize(arquivo_audio) > 500
        )

        if tem_cache_disco:
            try:
                os.utime(arquivo_audio, None)
            except OSError:
                pass
        else:
            fish_configurado = bool(
                _extrair_fish_key(str(hud.config.get("fish_api_key", "")))
                and _extrair_fish_id(str(hud.config.get("fish_voice_id", "")))
            )
            arquivo_audio = _sintetizar_para_arquivo(
                hud,
                texto_fala,
                arquivo_audio,
                evitar_cache_no_fallback=usar_cache and fish_configurado,
            )
            if usar_cache:
                threading.Thread(target=_limpar_cache_audio_excedente, daemon=True).start()

        _reproduzir_arquivo_com_lipsync(hud, arquivo_audio)
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
    try:
        limiar_voz = max(120, min(1500, int(hud.config.get("limiar_voz", 340) or 340)))
    except Exception:
        limiar_voz = 340
    blocos_espera_max = 65 if aguardando_comando else 38
    blocos_silencio_fim = 9 if aguardando_comando else 7
    blocos_duracao_max = 85

    buffer_pre_fala: deque[np.ndarray] = deque(maxlen=5)
    quadros_fala: list[np.ndarray] = []
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

        pico_max = float(np.max(np.abs(gravacao_1d)))
        if pico_max > 0:
            ganho = min(3.5, 24000.0 / pico_max)
            gravacao_1d = np.clip(gravacao_1d * ganho, -32768.0, 32767.0)

        bytes_pcm = gravacao_1d.astype(np.int16).tobytes()
        del gravacao_1d

        hud.atualizar_estado("TRANSCREVENDO...", "#F59E0B")
        usar_offline = bool(hud.config.get("stt_offline", PREFERIR_STT_OFFLINE))
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