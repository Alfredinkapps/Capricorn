import os
import json
import subprocess

ARQUIVO_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capri_config.json")


def carregar_apps_ativos() -> dict:
    """Retorna apenas os aplicativos que estão com o botão VERDE (ativo=True) nas configurações."""
    if not os.path.exists(ARQUIVO_CONFIG):
        return {}
    try:
        with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
            dados = json.load(f)
        apps = dados.get("apps", {})
        return {k.lower(): v for k, v in apps.items() if v.get("ativo", False)}
    except Exception:
        return {}


def fechar_aplicativo(nome_app: str) -> str:
    """Fecha um aplicativo aberto no computador caso ele esteja autorizado nas configurações.
    
    Args:
        nome_app: Nome do aplicativo que o usuário deseja fechar (ex: 'firefox', 'vscode', 'calculadora', 'discord').
    """
    alvo = nome_app.lower().strip()
    apps_ativos = carregar_apps_ativos()

    apelidos = {
        "navegador": ["firefox", "google chrome", "chrome", "microsoft edge", "opera", "brave"],
        "vscode": ["visual studio code", "vscode", "code"],
        "bloco de notas": ["bloco de notas", "notepad"],
        "calculadora": ["calculadora", "calc"]
    }

    chave_encontrada = None
    if alvo in apps_ativos:
        chave_encontrada = alvo
    elif alvo in apelidos:
        for op in apelidos[alvo]:
            if op in apps_ativos:
                chave_encontrada = op
                break
    else:
        for k in apps_ativos.keys():
            if alvo in k or k in alvo:
                chave_encontrada = k
                break

    if not chave_encontrada:
        return f"O aplicativo {nome_app} está desativado nas configurações ou não foi encontrado."

    info = apps_ativos[chave_encontrada]
    processo = info.get("processo_fechar", "")
    nome_exibicao = info.get("nome", chave_encontrada)

    if not processo:
        return f"Não foi possível identificar o executável de {nome_exibicao}."

    try:
        resultado = subprocess.run(
            f'taskkill /F /IM "{processo}" /T',
            shell=True,
            capture_output=True,
            text=True
        )
        if resultado.returncode == 0:
            return f"Protocolo executado. O aplicativo {nome_exibicao} foi encerrado."
        else:
            return f"O aplicativo {nome_exibicao} não parece estar aberto no momento."
    except Exception as e:
        return f"Erro ao tentar fechar {nome_exibicao}: {str(e)}"


def verificar_fechamento_rapido(frase: str) -> str:
    """Verifica no Fast-Track se o usuário pediu para fechar algum app ativo."""
    verbos_fechar = ["feche", "fechar", "fecha", "encerre", "encerrar", "finalizar", "mate"]
    if not any(v in frase for v in verbos_fechar):
        return ""

    apps_ativos = carregar_apps_ativos()

    if "navegador" in frase:
        for nav in ["firefox", "google chrome", "chrome", "brave", "edge"]:
            if nav in apps_ativos:
                return fechar_aplicativo(nav)
    if "vscode" in frase or "visual studio" in frase:
        for ide in ["visual studio code", "vscode"]:
            if ide in apps_ativos:
                return fechar_aplicativo(ide)

    for chave in sorted(apps_ativos.keys(), key=len, reverse=True):
        if chave in frase:
            return fechar_aplicativo(chave)

    return ""