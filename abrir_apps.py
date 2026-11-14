import os
import json
import subprocess
import sys

if getattr(sys, "frozen", False):
    PASTA_BASE = os.path.dirname(sys.executable)
else:
    PASTA_BASE = os.path.dirname(os.path.abspath(__file__))

ARQUIVO_CONFIG = os.path.join(PASTA_BASE, "capri_config.json")

# Variações que o microfone costuma entender quando você fala "VS Code"
VARIACOES_VSCODE = [
    "vscode", "vs code", "v s code", "visual studio code",
    "visual studio", "visual code", "vesicode", "vê esse code", "vsc"
]


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


def _abrir_vscode_direto() -> str:
    """Localiza e abre o executável oficial do VS Code no Windows caso o atalho padrão falhe."""
    caminhos_possiveis = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Microsoft VS Code\Code.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), r"Microsoft VS Code\Code.exe"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Visual Studio Code\Visual Studio Code.lnk")
    ]
    for caminho in caminhos_possiveis:
        if os.path.exists(caminho):
            try:
                os.startfile(caminho)
                return "Protocolo executado. Iniciando Visual Studio Code."
            except Exception:
                pass

    # Última tentativa via comando global 'code' no PATH do Windows
    try:
        subprocess.Popen("code", shell=True)
        return "Protocolo executado. Iniciando Visual Studio Code."
    except Exception as e:
        return f"Não foi possível localizar o executável do VS Code: {str(e)}"


def abrir_aplicativo(nome_app: str) -> str:
    """Abre um aplicativo instalado no computador caso ele esteja autorizado nas configurações."""
    alvo = nome_app.lower().strip()
    apps_ativos = carregar_apps_ativos()

    apelidos = {
        "navegador": ["firefox", "google chrome", "chrome", "microsoft edge", "opera", "brave"],
        "vscode": ["visual studio code", "vscode", "vs code", "code"],
        "bloco de notas": ["bloco de notas", "notepad"],
        "calculadora": ["calculadora", "calc"]
    }

    # Se for qualquer variação de VS Code, normaliza para o apelido 'vscode'
    if any(v in alvo for v in VARIACOES_VSCODE):
        alvo = "vscode"

    chave_encontrada = None
    if alvo in apps_ativos:
        chave_encontrada = alvo
    elif alvo in apelidos:
        for op in apelidos[alvo]:
            if op in apps_ativos:
                chave_encontrada = op
                break
            # Busca parcial nas chaves ativas
            for k in apps_ativos.keys():
                if op in k:
                    chave_encontrada = k
                    break
            if chave_encontrada:
                break
    else:
        for k in apps_ativos.keys():
            if alvo in k or k in alvo:
                chave_encontrada = k
                break

    # Fallback exclusivo para o VS Code caso o caminho salvo tenha mudado
    if not chave_encontrada and alvo == "vscode":
        return _abrir_vscode_direto()

    if not chave_encontrada:
        return f"O aplicativo {nome_app} está desativado nas configurações ou não foi encontrado."

    info = apps_ativos[chave_encontrada]
    caminho = info.get("caminho_abrir", "")
    nome_exibicao = info.get("nome", chave_encontrada)

    try:
        os.startfile(caminho)
        return f"Protocolo executado. Iniciando {nome_exibicao}."
    except Exception:
        if alvo == "vscode":
            return _abrir_vscode_direto()
        try:
            subprocess.Popen(f'start "" "{caminho}"', shell=True)
            return f"Protocolo executado. Iniciando {nome_exibicao}."
        except Exception as e:
            return f"Erro ao tentar abrir {nome_exibicao}: {str(e)}"


def verificar_abertura_rapida(frase: str, modo_direto: bool = False) -> str:
    """Verifica no Fast-Track se o usuário pediu para abrir algum app ativo."""
    verbos_abrir = [
        "abra", "abrir", "abre", "abri", "inicie", "iniciar",
        "inicia", "ligar", "executar", "executa", "roda", "rodar"
    ]
    if not modo_direto and not any(v in frase for v in verbos_abrir):
        return ""

    apps_ativos = carregar_apps_ativos()

    # 1. Checa todas as variações de fala do VS Code (com ou sem espaço)
    if any(v in frase for v in VARIACOES_VSCODE):
        return abrir_aplicativo("vscode")

    # 2. Checa apelidos de navegador
    if "navegador" in frase:
        for nav in ["firefox", "google chrome", "chrome", "brave", "edge"]:
            if nav in apps_ativos:
                return abrir_aplicativo(nav)

    # 3. Checa os demais apps ativos na lista
    for chave in sorted(apps_ativos.keys(), key=len, reverse=True):
        if chave in frase:
            return abrir_aplicativo(chave)

    return ""