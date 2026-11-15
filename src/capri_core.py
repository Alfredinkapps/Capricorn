import os
import sys
import time
import random
import threading
import speech_recognition as sr
from google import genai

# Garante que o Python encontre todos os módulos dentro de src/
PASTA_SRC = os.path.dirname(os.path.abspath(__file__))
if PASTA_SRC not in sys.path:
    sys.path.insert(0, PASTA_SRC)

from hud import PASTA_PROJETO, CapriHUD, configurar_inicializacao_windows
from voz import falar, ouvir_microfone_com_hud, extrair_comando_apos_nome, RESPOSTAS_CHAMADA
from cerebro_ia import obter_lista_modelos_rapidos, processar_comando_usuario


def loop_cerebro_capri(hud: CapriHUD):
    os.chdir(PASTA_PROJETO)
    configurar_inicializacao_windows(True)
    reconhecedor = sr.Recognizer()

    while hud.rodando and not hud.config.get("gemini_api_key"):
        time.sleep(0.5)

    if not hud.rodando:
        return

    while hud.rodando:
        try:
            hud.reiniciar_ia = False
            os.environ["GEMINI_API_KEY"] = hud.config.get("gemini_api_key", "")
            client = genai.Client(http_options={'timeout': 20000})

            modelos = obter_lista_modelos_rapidos(client)
            historico_conversa = []

            falar(hud, "Sistemas da Capri online. Módulos de controle e pesquisa carregados.")
            hud.atualizar_estado("EM ESPERA", "#00F0FF", "Diga 'Capri' para me chamar...")

            while hud.rodando and not hud.reiniciar_ia:
                if hud.pausada:
                    time.sleep(0.2)
                    continue

                frase_ouvida = ouvir_microfone_com_hud(hud, reconhecedor, aguardando_comando=False)

                if not frase_ouvida or not hud.rodando or hud.pausada or hud.reiniciar_ia:
                    continue

                print(f"🗣️ Ouvido: '{frase_ouvida}'")
                chamou_capri, comando_embutido = extrair_comando_apos_nome(frase_ouvida)

                if chamou_capri:
                    if len(comando_embutido) < 3:
                        saudacao = random.choice(RESPOSTAS_CHAMADA)
                        falar(hud, saudacao, usar_cache=True)

                        hud.atualizar_estado("OUVINDO VOCÊ...", "#00FF66", "Pode falar sua pergunta ou comando...")
                        comando_direto = ouvir_microfone_com_hud(hud, reconhecedor, aguardando_comando=True)

                        if comando_direto:
                            print(f"🎯 Pergunta/Comando recebido: '{comando_direto}'")
                            hud.atualizar_estado("COMANDO DETECTADO", "#00FF66", f"Você: \"{comando_direto}\"")
                            processar_comando_usuario(comando_direto, hud, reconhecedor, client, modelos, historico_conversa)
                        else:
                            hud.atualizar_estado("EM ESPERA", "#00F0FF", "Nenhum comando detectado. Diga 'Capri'...")
                    else:
                        hud.atualizar_estado("VOZ DETECTADA", "#00FF66", f"Você: \"{comando_embutido}\"")
                        processar_comando_usuario(comando_embutido, hud, reconhecedor, client, modelos, historico_conversa)

                    hud.atualizar_estado("EM ESPERA", "#00F0FF", "Diga 'Capri' para me chamar...")

        except Exception as e:
            print(f"[Erro no Loop Principal]: {e}")
            time.sleep(2)


if __name__ == "__main__":
    app_hud = CapriHUD()
    thread_ia = threading.Thread(target=loop_cerebro_capri, args=(app_hud,), daemon=True)
    thread_ia.start()
    app_hud.root.mainloop()