import os
import re
import threading
import requests
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

SESSAO_IA = requests.Session()


def obter_lista_modelos_rapidos(client) -> list:
    preferidos = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.0-flash-lite",
        "gemini-3.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-latest"
    ]
    if not client:
        return preferidos
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


def _instrucao_sistema() -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    return (
        f"Você é Capri (projeto Capricorn), assistente virtual pessoal do usuário inspirada em Cyberpunk. "
        f"A data atual é {hoje}. "
        f"Responda SEMPRE em português do Brasil, em no máximo 1 ou 2 frases curtas, fluidas, diretas e sem usar asteriscos ou emojis."
    )


def _perguntar_claude(pergunta: str, api_key: str, historico: list) -> str:
    if not api_key:
        return ""
    mensagens = []
    for i, msg in enumerate(historico[-6:]):
        role = "user" if i % 2 == 0 else "assistant"
        mensagens.append({"role": role, "content": msg})
    mensagens.append({"role": "user", "content": pergunta})

    for modelo in ("claude-3-5-haiku-latest", "claude-3-7-sonnet-latest", "claude-3-haiku-20240307"):
        try:
            resp = SESSAO_IA.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": modelo,
                    "max_tokens": 180,
                    "temperature": 0.3,
                    "system": _instrucao_sistema(),
                    "messages": mensagens
                },
                timeout=15
            )
            if resp.status_code == 200:
                dados = resp.json()
                blocos = dados.get("content", [])
                if blocos and "text" in blocos[0]:
                    texto_final = limpar_resposta_ia(blocos[0]["text"])
                    historico.append(pergunta)
                    historico.append(texto_final)
                    return texto_final
        except Exception:
            continue
    return ""


def _perguntar_deepseek(pergunta: str, api_key: str, historico: list) -> str:
    if not api_key:
        return ""
    mensagens = [{"role": "system", "content": _instrucao_sistema()}]
    for i, msg in enumerate(historico[-6:]):
        role = "user" if i % 2 == 0 else "assistant"
        mensagens.append({"role": role, "content": msg})
    mensagens.append({"role": "user", "content": pergunta})

    try:
        resp = SESSAO_IA.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": mensagens,
                "max_tokens": 180,
                "temperature": 0.3
            },
            timeout=15
        )
        if resp.status_code == 200:
            dados = resp.json()
            escolhas = dados.get("choices", [])
            if escolhas:
                texto_final = limpar_resposta_ia(escolhas[0]["message"]["content"])
                historico.append(pergunta)
                historico.append(texto_final)
                return texto_final
    except Exception:
        pass
    return ""


def perguntar_gemini_com_pesquisa(pergunta: str, client, modelos: list, historico: list, hud: CapriHUD = None) -> str:
    instrucao_pesquisa = _instrucao_sistema()
    if hud is not None:
        provedor = hud.config.get("provedor_ia", "Gemini").lower()
        chave_claude = hud.config.get("claude_api_key", "").strip()
        chave_deepseek = hud.config.get("deepseek_api_key", "").strip()

        if "claude" in provedor and chave_claude:
            resp_c = _perguntar_claude(pergunta, chave_claude, historico)
            if resp_c:
                return resp_c
        elif "deepseek" in provedor and chave_deepseek:
            resp_d = _perguntar_deepseek(pergunta, chave_deepseek, historico)
            if resp_d:
                return resp_d

    if client:
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

    if hud is not None:
        if hud.config.get("deepseek_api_key", "").strip():
            return _perguntar_deepseek(pergunta, hud.config["deepseek_api_key"].strip(), historico)
        if hud.config.get("claude_api_key", "").strip():
            return _perguntar_claude(pergunta, hud.config["claude_api_key"].strip(), historico)
    return ""


def processar_comando_usuario(comando: str, hud: CapriHUD, reconhecedor: sr.Recognizer, client, modelos: list, historico: list):
    cmd = normalizar_frase(comando)

    if any(g in cmd for g in COMANDOS_INTERFACE["desligar_capri"]):
        if hasattr(hud, "acionar_sprite_temporario"):
            hud.acionar_sprite_temporario("capri-idle-wave_a.png", duracao=3.0)
        falar(hud, "Desligando os sistemas locais. Até logo.")
        hud.desligar_tudo()
        return

    if any(g in cmd for g in COMANDOS_INTERFACE["cancelar_conversa"]):
        if hasattr(hud, "acionar_sprite_temporario"):
            hud.acionar_sprite_temporario("capri-idle-shrug.png", duracao=2.0)
        falar(hud, "Beleza, qualquer coisa é só chamar.")
        return

    # 1. Cadastrar Executável Manualmente por Voz (100% Local)
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
            if hasattr(hud, "acionar_sprite_temporario"):
                hud.acionar_sprite_temporario("capri-idle-excited.png", duracao=2.5)
            falar(hud, f"Perfeito. Salvei como {nome_voz}. Quando quiser, é só pedir para abrir {nome_voz}.")
        else:
            falar(hud, "Não consegui ouvir o nome. Tente novamente ou use o botão nas configurações.")
        return

    # 2. Música no Spotify Desktop (100% Local + Sprite Musical)
    pediu_musica, nome_musica_direto = detectar_pedido_musica(cmd)
    if pediu_musica:
        if nome_musica_direto:
            hud.atualizar_estado("ABRINDO SPOTIFY...", "#00FF66")
            falar(hud, tocar_musica_spotify(nome_musica_direto))
            if hasattr(hud, "acionar_sprite_temporario"):
                hud.acionar_sprite_temporario("capri-music-window.png", duracao=6.0)
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
            if hasattr(hud, "acionar_sprite_temporario"):
                hud.acionar_sprite_temporario("capri-music-window.png", duracao=6.0)
        else:
            falar(hud, "Não consegui ouvir o nome da música.")
        return

    # 3. Comandos Locais Instantâneos do PC (100% Local)
    resposta_local = tentar_execucao_instantanea(cmd, hud)
    if resposta_local:
        if hasattr(hud, "acionar_sprite_temporario"):
            hud.acionar_sprite_temporario("capri-idle-happy.png", duracao=1.8)
        falar(hud, resposta_local)
        return

    # 4. Pesquisa na API Escolhida pelo Usuário (Gemini / Claude / DeepSeek)
    provedor_ativo = hud.config.get("provedor_ia", "Gemini")
    hud.atualizar_estado("PESQUISANDO IA...", "#A855F7")
    print(f"  [Pesquisando via {provedor_ativo}]: '{cmd}'...")
    resposta_ia = perguntar_gemini_com_pesquisa(cmd, client, modelos, historico, hud=hud)
    if resposta_ia:
        falar(hud, resposta_ia)
    else:
        if hasattr(hud, "acionar_sprite_temporario"):
            hud.acionar_sprite_temporario("capri-idle-concerned.png", duracao=2.5)
        falar(hud, f"Verifique se a chave da API do {provedor_ativo} está configurada na central.")