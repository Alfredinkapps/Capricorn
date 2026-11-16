import os
import re
import asyncio
import requests
import numpy as np
import sounddevice as sd
import pygame
import edge_tts
import speech_recognition as sr
from collections import deque
from hud import PASTA_PROJETO, CapriHUD
from dicionario_comandos import extrair_comando_apos_nome, normalizar_frase

VOZ_FALLBACK = "pt-BR-FranciscaNeural"

# Atualizado: "Fala, bobão." substituído por "Fala."
RESPOSTAS_CHAMADA = [
    "Oie.",
    "Fala.",
    "Diga lá.",
    "Tô ouvindo, fala aí."
]

# Sessão HTTP persistente (evita reconectar do zero a cada fala na Fish Audio)
SESSAO_HTTP = requests.Session()
_REGEX_NOME_CACHE = re.compile(r"[^a-zA-Z0-9]")


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
        "model": "s2.1-pro-free"
    }
    # normalize=True e texto sem reticências artificiais removem as respiradas estranhas
    payload = {
        "text": texto.strip(),
        "reference_id": id_limpo,
        "format": "mp3",
        "mp3_bitrate": 128,
        "normalize": True,
        "latency": "balanced"
    }

    try:
        resp = SESSAO_HTTP.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(arquivo_saida, "wb") as f:
                f.write(resp.content)
            return True
        return False
    except Exception as e:
        print(f"❌ [Erro de conexão Fish Audio]: {e}")
        return False


def falar(hud: CapriHUD, texto: str, usar_cache: bool = False):
    texto_limpo = re.sub(r"\s+", " ", texto).strip()
    print(f"\nCAPRI: {texto_limpo}\n")
    hud.atualizar_estado("FALANDO...", "#FF0055", f"CAPRI: {texto_limpo}")

    pasta_cache = os.path.join(PASTA_PROJETO, "cache")
    os.makedirs(pasta_cache, exist_ok=True)

    if usar_cache:
        nome_limpo = _REGEX_NOME_CACHE.sub("_", texto_limpo.lower())
        arquivo_audio = os.path.join(pasta_cache, f"cache_{nome_limpo}.mp3")
    else:
        arquivo_audio = os.path.join(pasta_cache, "capri_voz.mp3")

    try:
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        tem_cache_valido = usar_cache and os.path.exists(arquivo_audio) and os.path.getsize(arquivo_audio) > 500
        if not tem_cache_valido:
            if not gerar_voz_fish_audio(hud, texto_limpo, arquivo_audio):
                asyncio.run(_gerar_audio_nativo(texto_limpo, arquivo_audio))

        pygame.mixer.music.load(arquivo_audio)
        pygame.mixer.music.play()

        relogio = pygame.time.Clock()
        while pygame.mixer.music.get_busy() and hud.rodando:
            hud.nivel_voz = np.random.uniform(0.25, 0.75)
            relogio.tick(15)

        hud.nivel_voz = 0.0
        pygame.mixer.music.unload()
    except Exception as e:
        hud.nivel_voz = 0.0
        print(f"[Erro na reprodução de voz]: {e}")


def ouvir_microfone_com_hud(hud: CapriHUD, reconhecedor: sr.Recognizer, aguardando_comando: bool = False) -> str:
    taxa_amostragem = 16000
    bloco = 1600  # 0.1s exato
    limiar_voz = 360

    blocos_espera_max = 65 if aguardando_comando else 38
    blocos_silencio_fim = 9 if aguardando_comando else 7
    blocos_duracao_max = 80

    buffer_pre_fala = deque(maxlen=4)
    quadros_fala = []
    falando = False
    blocos_silencio = 0

    hud.nivel_voz = 0.0
    hud.atualizar_estado("OUVINDO VOCÊ..." if aguardando_comando else "EM ESPERA", "#00FF66" if aguardando_comando else "#00F0FF")

    try:
        with sd.InputStream(samplerate=taxa_amostragem, channels=1, dtype="int16") as stream:
            for i in range(blocos_espera_max + blocos_duracao_max):
                if not hud.rodando or hud.pausada or hud.reiniciar_ia:
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

        gravacao = np.concatenate(quadros_fala, axis=0)
        gravacao_float = gravacao.astype(np.float32)
        pico_max = np.max(np.abs(gravacao_float))
        if pico_max > 0:
            ganho = min(3.5, 24000.0 / pico_max)
            gravacao = np.clip(gravacao_float * ganho, -32768, 32767).astype(np.int16)

        hud.atualizar_estado("TRANSCREVENDO...", "#F59E0B")
        audio_data = sr.AudioData(gravacao.tobytes(), taxa_amostragem, 2)
        texto_bruto = reconhecedor.recognize_google(audio_data, language="pt-BR")
        return normalizar_frase(texto_bruto)

    except sr.UnknownValueError:
        hud.nivel_voz = 0.0
        return ""
    except Exception as e:
        hud.nivel_voz = 0.0
        print(f"[Aviso de áudio]: {e}")
        return ""