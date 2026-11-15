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

VOZ_FALLBACK = "pt-BR-FranciscaNeural"

RESPOSTAS_CHAMADA = [
    "Oie.",
    "Fala, bobão.",
    "Diga lá.",
    "Tô ouvindo, fala aí."
]

GATILHOS_CAPRI = [
    "capri", "cápri", "capricorn", "capricórnio",
    "cabri", "gabri", "kpri", "capricho", "capre"
]


def extrair_comando_apos_nome(frase: str) -> tuple[bool, str]:
    palavras_saudacao = ["oi", "olá", "ola", "ei", "hey", "aí", "ai", "ô", "o"]
    for gatilho in GATILHOS_CAPRI:
        if gatilho in frase:
            resto = frase.replace(gatilho, "").strip(" ,.!?")
            palavras_resto = [p for p in resto.split() if p not in palavras_saudacao]
            comando_limpo = " ".join(palavras_resto).strip()
            return True, comando_limpo
    return False, ""


def preparar_pausas_fala(texto: str) -> str:
    texto_pausado = texto.strip()
    texto_pausado = re.sub(r",\s*", ", ... ", texto_pausado)
    texto_pausado = re.sub(r"\.\s+", ".\n", texto_pausado)
    texto_pausado = re.sub(r"\?\s+", "?\n", texto_pausado)
    texto_pausado = re.sub(r"!\s+", "!\n", texto_pausado)
    return texto_pausado


async def _gerar_audio_nativo(texto: str, arquivo_saida: str):
    comunicador = edge_tts.Communicate(texto, VOZ_FALLBACK, rate="+2%")
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
    payload = {
        "text": texto,
        "reference_id": id_limpo,
        "format": "mp3",
        "mp3_bitrate": 128,
        "normalize": False,
        "latency": "normal"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(arquivo_saida, "wb") as f:
                f.write(resp.content)
            return True
        return False
    except Exception as e:
        print(f"❌ [Erro de conexão Fish Audio]: {e}")
        return False


def falar(hud: CapriHUD, texto: str, usar_cache: bool = False):
    print(f"\nCAPRI: {texto}\n")
    hud.atualizar_estado("FALANDO...", "#FF0055", f"CAPRI: {texto}")

    pasta_cache = os.path.join(PASTA_PROJETO, "cache")
    os.makedirs(pasta_cache, exist_ok=True)

    if usar_cache:
        nome_limpo = re.sub(r"[^a-zA-Z0-9]", "_", texto.lower())
        arquivo_audio = os.path.join(pasta_cache, f"cache_{nome_limpo}.mp3")
    else:
        arquivo_audio = os.path.join(pasta_cache, "capri_voz.mp3")

    try:
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        if not (usar_cache and os.path.exists(arquivo_audio) and os.path.getsize(arquivo_audio) > 500):
            texto_com_pausas = preparar_pausas_fala(texto)
            if not gerar_voz_fish_audio(hud, texto_com_pausas, arquivo_audio):
                asyncio.run(_gerar_audio_nativo(texto, arquivo_audio))

        pygame.mixer.music.load(arquivo_audio)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy() and hud.rodando:
            hud.nivel_voz = np.random.uniform(0.25, 0.75)
            pygame.time.Clock().tick(15)

        hud.nivel_voz = 0.0
        pygame.mixer.music.unload()
    except Exception as e:
        hud.nivel_voz = 0.0
        print(f"[Erro na reprodução de voz]: {e}")


def ouvir_microfone_com_hud(hud: CapriHUD, reconhecedor: sr.Recognizer, aguardando_comando: bool = False) -> str:
    taxa_amostragem = 16000
    bloco = int(taxa_amostragem * 0.1)
    limiar_voz = 380

    tempo_espera_max = 7.0 if aguardando_comando else 4.0
    blocos_espera_max = int(tempo_espera_max / 0.1)
    blocos_silencio_fim = 8 if not aguardando_comando else 10
    blocos_duracao_max = 80

    buffer_pre_fala = deque(maxlen=4)
    quadros_fala = []
    falando = False
    blocos_silencio = 0

    hud.nivel_voz = 0.0

    if aguardando_comando:
        hud.atualizar_estado("OUVINDO VOCÊ...", "#00FF66")
    else:
        hud.atualizar_estado("EM ESPERA", "#00F0FF")

    try:
        with sd.InputStream(samplerate=taxa_amostragem, channels=1, dtype='int16') as stream:
            for i in range(blocos_espera_max + blocos_duracao_max):
                if not hud.rodando or hud.pausada or hud.reiniciar_ia:
                    hud.nivel_voz = 0.0
                    return ""

                dados, _ = stream.read(bloco)
                copia = dados.copy()
                pico = int(np.max(np.abs(copia)))

                if aguardando_comando:
                    hud.nivel_voz = min(1.0, pico / 2500.0)
                else:
                    hud.nivel_voz = 0.0

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
        return reconhecedor.recognize_google(audio_data, language="pt-BR").lower().strip()

    except sr.UnknownValueError:
        hud.nivel_voz = 0.0
        return ""
    except Exception as e:
        hud.nivel_voz = 0.0
        print(f"[Aviso de áudio]: {e}")
        return ""