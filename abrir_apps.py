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


def abrir_aplicativo(nome_app: str) -> str:
    """Abre um aplicativo instalado no computador caso ele esteja autorizado nas configurações.
    
    Args:
        nome_app: Nome do aplicativo que o usuário deseja abrir (ex: 'firefox', 'vscode', 'calculadora', 'discord', 'steam').
    """
    alvo = nome_app.lower().strip()
    apps_ativos = carregar_apps_ativos()

    # Apelidos rápidos comuns
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
        # Busca parcial pelo nome do app
        for k in apps_ativos.keys():
            if alvo in k or k in alvo:
                chave_encontrada = k
                break

    if not chave_encontrada:
        return f"O aplicativo {nome_app} está desativado nas configurações ou não foi encontrado."

    info = apps_ativos[chave_encontrada]
    caminho = info.get("caminho_abrir", "")
    nome_exibicao = info.get("nome", chave_encontrada)

    try:
        os.startfile(caminho)
        return f"Protocolo executado. Iniciando {nome_exibicao}."
    except Exception:
        try:
            subprocess.Popen(f'start "" "{caminho}"', shell=True)
            return f"Protocolo executado. Iniciando {nome_exibicao}."
        except Exception as e:
            return f"Erro ao tentar abrir {nome_exibicao}: {str(e)}"


def verificar_abertura_rapida(frase: str, modo_direto: bool = False) -> str:
    """Verifica no Fast-Track se o usuário pediu para abrir algum app ativo."""
    verbos_abrir = ["abra", "abrir", "abre", "abri", "inicie", "iniciar", "inicia", "ligar", "executar", "executa", "roda", "rodar"]
    if not modo_direto and not any(v in frase for v in verbos_abrir):
        return ""

    apps_ativos = carregar_apps_ativos()
    
    # Checa apelidos primeiro
    if "navegador" in frase:
        for nav in ["firefox", "google chrome", "chrome", "brave", "edge"]:
            if nav in apps_ativos:
                return abrir_aplicativo(nav)
    if "vscode" in frase or "visual studio" in frase:
        for ide in ["visual studio code", "vscode"]:
            if ide in apps_ativos:
                return abrir_aplicativo(ide)

    # Checa os nomes dos apps ativos (do nome maior para o menor para evitar falsos positivos)
    for chave in sorted(apps_ativos.keys(), key=len, reverse=True):
        if chave in frase:
            return abrir_aplicativo(chave)

    return ""