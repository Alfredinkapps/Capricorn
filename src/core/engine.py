import os
import time
import random
import threading
import pygame
import speech_recognition as sr
from google import genai

from core.config import PASTA_PROJETO, PASTA_DATA, configurar_inicializacao_windows
from ui.hud import CapriHUD
from audio.voz import falar, ouvir_microfone_com_hud, RESPOSTAS_CHAMADA
from audio.comandos import extrair_comando_apos_nome, normalizar_frase
from ai.cerebro import obter_lista_modelos_rapidos, processar_comando_usuario
from ai.visao import ObservadorTela
from ai.memoria import MemoriaCapri
from agents.reigns import AgenteReigns
from core.logger import obter_logger

log = obter_logger("engine")


def executar_comando_seguro(texto_bruto: str, hud: CapriHUD, estado: dict, lock: threading.Lock, origem: str = "VOZ"):
    """Normaliza e executa comandos de voz ou texto sem travar o HUD em caso de erro."""
    texto_norm = normalizar_frase(texto_bruto) if texto_bruto else ""
    if not texto_norm:
        texto_norm = texto_bruto.strip().lower()
    if not texto_norm:
        return

    if origem == "TEXTO":
        chamou, resto = extrair_comando_apos_nome(texto_norm)
        comando_final = resto if (chamou and len(resto) >= 2) else texto_norm
    else:
        comando_final = texto_norm

    if origem == "TEXTO":
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass

    with lock:
        try:
            processar_comando_usuario(
                comando_final,
                hud,
                estado["reconhecedor"],
                estado["client"],
                estado["modelos"],
                estado["historico"],
                observador=estado.get("observador"),
                agente_reigns=estado.get("agente_reigns"),
                memoria=estado.get("memoria"),
            )
        except Exception as e:
            log.exception("Erro ao processar comando (%s)", origem)
            hud.atualizar_estado("ERRO", "#FF0055", f"Erro ao ler mensagem: {e}")
            time.sleep(2.5)
        finally:
            estado_pos = "MIC SILENCIADO" if hud.pausada else "EM ESPERA"
            cor_pos = getattr(hud, "BORDER_PINK", "#D45B72")
            hud.atualizar_estado(estado_pos, cor_pos)


def loop_mensagens_texto(hud: CapriHUD, estado: dict, lock: threading.Lock):
    """Lê a caixa de mensagem instantaneamente, sem depender do loop do microfone."""
    while hud.rodando:
        try:
            cmd_digitado = hud.fila_comandos_texto.get(timeout=0.2)
        except Exception:
            continue

        if not cmd_digitado or not cmd_digitado.strip():
            continue

        espera = 0
        while not estado["pronto"] and hud.rodando and espera < 50:
            time.sleep(0.1)
            espera += 1

        log.info("Caixa de mensagem: '%s'", cmd_digitado)
        executar_comando_seguro(cmd_digitado, hud, estado, lock, origem="TEXTO")


def loop_cerebro_capri(hud: CapriHUD, estado: dict, lock: threading.Lock):
    os.chdir(PASTA_PROJETO)
    configurar_inicializacao_windows(hud.config.get("iniciar_com_windows", True))

    while hud.rodando:
        try:
            hud.reiniciar_ia = False
            estado["pronto"] = False
            chave_gemini = hud.config.get("gemini_api_key", "").strip()
            client = None
            modelos = []

            if chave_gemini:
                os.environ["GEMINI_API_KEY"] = chave_gemini
                try:
                    client = genai.Client(http_options={"timeout": 20000})
                    modelos = obter_lista_modelos_rapidos(client)
                except Exception as e:
                    log.warning("Falha ao inicializar cliente Gemini: %s", e)
                    client = None

            estado["client"] = client
            estado["modelos"] = modelos
            estado["historico"] = []
            estado["pronto"] = True

            with lock:
                falar(hud, "Sistemas da Capri online. Módulos de controle e pesquisa carregados.")

            # Acompanhamento proativo de eventos citados nos últimos 20 dias
            memoria = estado.get("memoria")
            if memoria:
                evento_pendente = memoria.obter_evento_para_perguntar()
                if evento_pendente:
                    time.sleep(1.5)
                    desc = evento_pendente["descricao"]
                    dias = evento_pendente["dias_atras"]
                    pergunta = f"Ei, faz uns {dias} dias que você comentou sobre {desc}. Como foi lá?"
                    with lock:
                        falar(hud, pergunta, usar_cache=False)
                    memoria.marcar_evento_como_perguntado(evento_pendente["id"])
                    memoria.registrar_conversa("[Sistema: acompanhamento proativo]", pergunta)

            estado_inicial = "MIC SILENCIADO" if hud.pausada else "EM ESPERA"
            hud.atualizar_estado(estado_inicial, hud.BORDER_PINK, "Diga 'Capri' ou digite um comando na barra abaixo.")

            while hud.rodando and not hud.reiniciar_ia:
                if getattr(hud, "limpar_contexto", False):
                    hud.limpar_contexto = False
                    estado["historico"].clear()

                if getattr(hud, "forcar_escuta_voz", False):
                    hud.forcar_escuta_voz = False
                    hud.atualizar_estado("OUVINDO VOCÊ...", hud.ACCENT_LIME, "Pode falar sua pergunta ou comando...")
                    cmd_voz_direto = ouvir_microfone_com_hud(hud, estado["reconhecedor"], aguardando_comando=True)
                    if cmd_voz_direto:
                        executar_comando_seguro(cmd_voz_direto, hud, estado, lock, origem="VOZ")
                    else:
                        hud.atualizar_estado("EM ESPERA", hud.BORDER_PINK, "Diga 'Capri' ou digite na barra abaixo.")
                    continue

                if hud.pausada:
                    time.sleep(0.1)
                    continue

                frase_ouvida = ouvir_microfone_com_hud(hud, estado["reconhecedor"], aguardando_comando=False)
                if not frase_ouvida or not hud.rodando or hud.pausada or hud.reiniciar_ia:
                    continue

                log.info("Voz ouvida: '%s'", frase_ouvida)
                chamou_capri, comando_embutido = extrair_comando_apos_nome(frase_ouvida)

                if chamou_capri:
                    if len(comando_embutido) < 3:
                        with lock:
                            saudacao = random.choice(RESPOSTAS_CHAMADA)
                            falar(hud, saudacao, usar_cache=True)
                        hud.atualizar_estado("OUVINDO VOCÊ...", hud.ACCENT_LIME, "Pode falar sua pergunta ou comando...")
                        comando_direto = ouvir_microfone_com_hud(hud, estado["reconhecedor"], aguardando_comando=True)
                        if comando_direto:
                            log.info("Comando de voz recebido: '%s'", comando_direto)
                            hud.atualizar_estado("COMANDO DETECTADO", hud.ACCENT_LIME, f'Você: "{comando_direto}"')
                            executar_comando_seguro(comando_direto, hud, estado, lock, origem="VOZ")
                        else:
                            hud.atualizar_estado("EM ESPERA", hud.BORDER_PINK, "Nenhum comando detectado. Diga 'Capri'...")
                    else:
                        hud.atualizar_estado("VOZ DETECTADA", hud.ACCENT_LIME, f'Você: "{comando_embutido}"')
                        executar_comando_seguro(comando_embutido, hud, estado, lock, origem="VOZ")

        except Exception as e:
            log.exception("Erro inesperado no loop principal")
            time.sleep(2)

def iniciar_capri():
    """Inicializa os subsistemas, sobe as threads de controle e abre o HUD."""
    app_hud = CapriHUD()
    estado_compartilhado = {
        "client": None,
        "modelos": [],
        "historico": [],
        "reconhecedor": sr.Recognizer(),
        "pronto": False,
    }
    lock_execucao = threading.Lock()

    memoria = MemoriaCapri(PASTA_DATA)
    estado_compartilhado["memoria"] = memoria

    observador = ObservadorTela(app_hud, estado_compartilhado, lock_execucao, falar)
    estado_compartilhado["observador"] = observador

    agente_reigns = AgenteReigns(app_hud, estado_compartilhado, lock_execucao, falar, memoria=memoria)
    estado_compartilhado["agente_reigns"] = agente_reigns

    thread_ia = threading.Thread(
        target=loop_cerebro_capri,
        args=(app_hud, estado_compartilhado, lock_execucao),
        daemon=True,
    )
    thread_texto = threading.Thread(
        target=loop_mensagens_texto,
        args=(app_hud, estado_compartilhado, lock_execucao),
        daemon=True,
    )
    thread_ia.start()
    thread_texto.start()
    app_hud.root.mainloop()