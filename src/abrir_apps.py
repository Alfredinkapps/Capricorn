import os
import re
import sys
import json
import subprocess

if getattr(sys, "frozen", False):
    PASTA_BASE = os.path.dirname(sys.executable)
else:
    PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
    # Funciona tanto se o arquivo estiver na raiz quanto dentro da pasta src/
    PASTA_BASE = os.path.dirname(PASTA_ATUAL) if os.path.basename(PASTA_ATUAL).lower() == "src" else PASTA_ATUAL

ARQUIVO_CONFIG = os.path.join(PASTA_BASE, "capri_config.json")

VARIACOES_VSCODE = [
    "vscode", "vs code", "v s code", "visual studio code",
    "visual studio", "visual code", "vesicode", "vê esse code", "vsc"
]


def _normalizar_nome(texto: str) -> str:
    """Remove espaços entre letras e números (ex: transforma 'cs 2' ou 'c s 2' em 'cs2')."""
    limpo = texto.lower().strip()
    limpo = re.sub(r"([a-zA-Z])\s+(\d)", r"\1\2", limpo)
    limpo = re.sub(r"\s+", " ", limpo)
    return limpo


def carregar_apps_ativos() -> dict:
    """Retorna todos os aplicativos que estão com o botão VERDE (ativo=True) no capri_config.json."""
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
    try:
        subprocess.Popen("code", shell=True)
        return "Protocolo executado. Iniciando Visual Studio Code."
    except Exception as e:
        return f"Não foi possível localizar o executável do VS Code: {str(e)}"


def _executar_caminho(caminho: str, nome_exibicao: str) -> str:
    """Abre o executável ou atalho garantindo que o diretório de trabalho (cwd) seja a pasta do próprio app."""
    if not caminho or not os.path.exists(caminho):
        return f"O caminho salvo para {nome_exibicao} não foi encontrado no computador."

    pasta_app = os.path.dirname(caminho)
    try:
        if caminho.lower().endswith(".exe"):
            subprocess.Popen([caminho], cwd=pasta_app if os.path.isdir(pasta_app) else None)
        else:
            os.startfile(caminho)
        return f"Protocolo executado. Iniciando {nome_exibicao}."
    except Exception:
        try:
            os.startfile(caminho)
            return f"Protocolo executado. Iniciando {nome_exibicao}."
        except Exception as e:
            return f"Erro ao tentar abrir {nome_exibicao}: {str(e)}"


def abrir_aplicativo(nome_app: str) -> str:
    """Procura o aplicativo pelo nome ou apelido personalizado e executa."""
    alvo = _normalizar_nome(nome_app)
    alvo_sem_espaco = alvo.replace(" ", "")
    apps_ativos = carregar_apps_ativos()

    if any(v in alvo for v in VARIACOES_VSCODE):
        alvo = "vscode"

    # 1. Procura nos apps cadastrados (pela chave, pelo nome ou pela lista de apelidos personalizados)
    chave_encontrada = None
    for chave, info in apps_ativos.items():
        chave_norm = _normalizar_nome(chave)
        nome_norm = _normalizar_nome(info.get("nome", ""))
        apelidos_app = [_normalizar_nome(ap) for ap in info.get("apelidos", [])]

        todos_nomes = [chave_norm, nome_norm] + apelidos_app
        todos_sem_espaco = [n.replace(" ", "") for n in todos_nomes if n]

        if alvo in todos_nomes or alvo_sem_espaco in todos_sem_espaco:
            chave_encontrada = chave
            break

    # 2. Busca parcial caso não tenha achado exato
    if not chave_encontrada:
        for chave, info in apps_ativos.items():
            apelidos_app = [_normalizar_nome(ap) for ap in info.get("apelidos", [])]
            for termo in [ _normalizar_nome(chave), _normalizar_nome(info.get("nome", "")) ] + apelidos_app:
                if termo and (termo in alvo or termo.replace(" ", "") in alvo_sem_espaco):
                    chave_encontrada = chave
                    break
            if chave_encontrada:
                break

    if not chave_encontrada and alvo == "vscode":
        return _abrir_vscode_direto()

    if not chave_encontrada:
        return f"O aplicativo {nome_app} está desativado nas configurações ou não foi encontrado."

    info = apps_ativos[chave_encontrada]
    return _executar_caminho(info.get("caminho_abrir", ""), info.get("nome", chave_encontrada))


def verificar_abertura_rapida(frase: str, modo_direto: bool = False) -> str:
    """Verifica se o usuário pediu para abrir algum programa ou apelido personalizado."""
    verbos_abrir = [
        "abra", "abrir", "abre", "abri", "inicie", "iniciar",
        "inicia", "ligar", "executar", "executa", "roda", "rodar"
    ]
    if not modo_direto and not any(v in frase for v in verbos_abrir):
        return ""

    frase_norm = _normalizar_nome(frase)
    frase_compacta = frase_norm.replace(" ", "")
    apps_ativos = carregar_apps_ativos()

    if any(v in frase_norm for v in VARIACOES_VSCODE):
        return abrir_aplicativo("vscode")

    # Monta lista de todos os gatilhos (chaves + apelidos personalizados) do maior para o menor
    candidatos = []
    for chave, info in apps_ativos.items():
        candidatos.append((_normalizar_nome(chave), chave))
        for ap in info.get("apelidos", []):
            ap_norm = _normalizar_nome(ap)
            if ap_norm:
                candidatos.append((ap_norm, chave))

    candidatos.sort(key=lambda x: len(x[0]), reverse=True)

    for gatilho, chave_real in candidatos:
        gatilho_compacto = gatilho.replace(" ", "")
        if gatilho in frase_norm or (len(gatilho_compacto) >= 2 and gatilho_compacto in frase_compacta):
            return abrir_aplicativo(chave_real)

    return ""