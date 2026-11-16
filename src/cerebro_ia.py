import os
import re
import threading
import speech_recognition as sr
from datetime import datetime
from tkinter import filedialog
from google.genai import types

from hud import CapriHUD, salvar_configuracoes
from voz import falar, ouvir_microfone_com_hud
from spotify_control import detectar_pedido_musica, encontrar_janela_spotify, tocar_musica_spotify
from sistema_pc import tentar_execucao_instantanea
from dicionario_comandos import COMANDOS_INTERFACE, normalizar_frase

_REGEX_ASTERISCOS = re.compile(r"\*+")
_REGEX_HASHTAGS = re.compile(r"#+\s*")
_REGEX_COLCHETES = re.compile(r"\[.*?\]")
_REGEX_LINKS = re.compile(r"https?://\S+")
_REGEX_ESPACOS_DUPLOS = re.compile(r"\s{2,}")


def obter_lista_modelos_rapidos(client) -> list:
    preferidos = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-latest"
    ]
    try:
        for m in client.models.list():
            nome = m.name.replace("models/", "")
            if "gemini" in nome and "flash" in nome:
                if not any(x in nome for x in ("thinking", "vision", "tts", "image", "audio", "embedding", "8b")):
                    if nome not in preferidos:
                        preferidos.append(nome)
    except Exception:
        pass
    return preferidos


def limpar_resposta_ia(texto: str) -> str:
    limpo = _REGEX_ASTERISCOS.sub("", texto)
    limpo = _REGEX_HASHTAGS.sub("", limpo)
    limpo = _REGEX_COLCHETES.sub("", limpo)
    limpo = _REGEX_LINKS.sub("", limpo)
    limpo = _REGEX_ESPACOS_DUPLOS.sub(" ", limpo)
    return limpo.strip()


def _salvar_exe_no_config(hud: CapriHUD, caminho_arquivo: str, nome_chamada: str):
    if hasattr(hud, "salvar_executavel_personalizado"):
        hud.salvar_executavel_personalizado(caminho_arquivo, nome_chamada)
        return

    apelido_limpo = nome_chamada.strip()
    chave = normalizar_frase(apelido_limpo)

    variacoes = {chave, chave.replace(" ", "")}
    variacoes.add(re.sub(r"([a-zA-Z])(\d)", r"\1 \2", chave))
    if len(chave) <= 5:
        variacoes.add(" ".join(list(chave.replace(" ", ""))))

    nome_exe = os.path.basename(caminho_arquivo)
    if not nome_exe.lower().endswith(".exe"):
        nome_exe = ""

    if "apps" not in hud.config:
        hud.config["apps"] = {}

    hud.config["apps"][chave] = {
        "nome": f"{apelido_limpo.upper()} ({os.path.basename(caminho_arquivo)})",
        "caminho_abrir": caminho_arquivo,
        "executavel": nome_exe,
        "ativo": True,
        "personalizado": True,
        "apelidos": list(variacoes)
    }
    salvar_configuracoes(hud.config)


def perguntar_gemini_com_pesquisa(pergunta: str, client, modelos: list, historico: list) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    instrucao_pesquisa = (
        f"Você é Capri (projeto Capricorn), assistente virtual pessoal do usuário inspirada em Cyberpunk. "
        f"A data atual é {hoje}. "
        f"Use a ferramenta de busca do Google sempre que precisar confirmar fatos atuais, cargos políticos, "
        f"notícias, clima ou informações em tempo real. "
        f"Responda SEMPRE em português do Brasil, em no máximo 1 ou 2 frases curtas, fluidas, diretas e sem usar asteriscos ou emojis."
    )

    conteudos = list(historico[-6:]) + [pergunta]

    for modelo in modelos:
        for usar_busca in (True, False):
            try:
                cfg = types.GenerateContentConfig(
                    system_instruction=instrucao_pesquisa,
                    tools=[types.Tool(google_search=types.GoogleSearch())] if usar_busca else None,
                    temperature=0.3,
                )
                resposta = client.models.generate_content(model=modelo, contents=conteudos, config=cfg)
                if resposta and resposta.text:
                    texto_final = limpar_resposta_ia(resposta.text)
                    historico.append(pergunta)
                    historico.append(texto_final)
                    return texto_final
            except Exception:
                continue

    return ""


def processar_comando_usuario(comando: str, hud: CapriHUD, reconhecedor: sr.Recognizer, client, modelos: list, historico: list):
    cmd = normalizar_frase(comando)

    if any(g in cmd for g in COMANDOS_INTERFACE["desligar_capri"]):
        falar(hud, "Desligando os sistemas locais. Até logo.")
        hud.desligar_tudo()
        return

    if any(g in cmd for g in COMANDOS_INTERFACE["cancelar_conversa"]):
        falar(hud, "Beleza, qualquer coisa é só chamar.")
        return

    # 1. Cadastrar Executável Manualmente por Voz
    if any(g in cmd for g in COMANDOS_INTERFACE["cadastrar_exe"]):
        falar(hud, "Selecione o arquivo executável na janela que eu abri.")
        caminho_escolhido = [""]
        evento_selecao = threading.Event()

        def _escolher_no_windows():
            caminho_escolhido[0] = filedialog.askopenfilename(
                parent=hud.root,
                title="Selecione o Executável para a Capri",
                filetypes=[("Executáveis e Atalhos", "*.exe *.lnk *.url *.bat *.cmd"), ("Todos os arquivos", "*.*")]
            )
            evento_selecao.set()

        hud.root.after(0, _escolher_no_windows)
        evento_selecao.wait()

        if not caminho_escolhido[0]:
            falar(hud, "Nenhum executável foi selecionado.")
            return

        falar(hud, "Como você quer chamar esse executável?")
        hud.atualizar_estado("NOME DO APP?...", "#00FF66")
        nome_voz = ouvir_microfone_com_hud(hud, reconhecedor, aguardando_comando=True)

        if nome_voz:
            _salvar_exe_no_config(hud, caminho_escolhido[0], nome_voz)
            falar(hud, f"Perfeito. Salvei como {nome_voz}. Quando quiser, é só pedir para abrir {nome_voz}.")
        else:
            falar(hud, "Não consegui ouvir o nome. Tente novamente ou use o botão nas configurações.")
        return

    # 2. Música no Spotify Desktop
    pediu_musica, nome_musica_direto = detectar_pedido_musica(cmd)
    if pediu_musica:
        if nome_musica_direto:
            hud.atualizar_estado("ABRINDO SPOTIFY...", "#00FF66")
            falar(hud, tocar_musica_spotify(nome_musica_direto))
            return

        if encontrar_janela_spotify():
            falar(hud, "Para qual música você quer trocar?", usar_cache=True)
        else:
            falar(hud, "Qual música você quer ouvir?", usar_cache=True)

        hud.atualizar_estado("QUAL MÚSICA?...", "#00FF66")
        nome_musica = ouvir_microfone_com_hud(hud, reconhecedor, aguardando_comando=True)
        if nome_musica:
            hud.atualizar_estado("CARREGANDO SPOTIFY...", "#00FF66")
            falar(hud, tocar_musica_spotify(nome_musica))
        else:
            falar(hud, "Não consegui ouvir o nome da música.")
        return

    # 3. Comandos Locais Instantâneos do PC
    resposta_local = tentar_execucao_instantanea(cmd, hud)
    if resposta_local:
        falar(hud, resposta_local)
        return

    # 4. Pesquisa na Gemini API + Google Search
    hud.atualizar_estado("PESQUISANDO IA...", "#A855F7")
    print(f"🔎 [Pesquisando na Gemini API]: '{cmd}'...")

    resposta_ia = perguntar_gemini_com_pesquisa(cmd, client, modelos, historico)
    if resposta_ia:
        falar(hud, resposta_ia)
    else:
        falar(hud, "Não consegui conectar aos servidores de pesquisa agora.")