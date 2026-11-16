import os
import sys
import json
import subprocess
from dicionario_comandos import VERBOS_ABRIR, normalizar_frase, remover_acentos

if getattr(sys, "frozen", False):
    PASTA_BASE = os.path.dirname(sys.executable)
else:
    PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
    PASTA_BASE = os.path.dirname(PASTA_ATUAL) if os.path.basename(PASTA_ATUAL).lower() == "src" else PASTA_ATUAL

ARQUIVO_CONFIG = os.path.join(PASTA_BASE, "capri_config.json")

_CACHE_APPS = {}
_ULTIMA_MODIFICACAO = 0.0


def carregar_apps_ativos() -> dict:
    """Lê o capri_config.json apenas se o arquivo tiver sido modificado no disco (Otimização O(1))."""
    global _CACHE_APPS, _ULTIMA_MODIFICACAO
    if not os.path.exists(ARQUIVO_CONFIG):
        return {}
    try:
        mtime = os.path.getmtime(ARQUIVO_CONFIG)
        if mtime != _ULTIMA_MODIFICACAO:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
            apps = dados.get("apps", {})
            _CACHE_APPS = {k.lower(): v for k, v in apps.items() if v.get("ativo", False)}
            _ULTIMA_MODIFICACAO = mtime
        return _CACHE_APPS
    except Exception:
        return _CACHE_APPS


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
                return "Iniciando Visual Studio Code."
            except Exception:
                pass
    try:
        subprocess.Popen("code", shell=True)
        return "Iniciando Visual Studio Code."
    except Exception as e:
        return f"Não foi possível localizar o VS Code: {str(e)}"


def _executar_caminho(caminho: str, nome_exibicao: str) -> str:
    if not caminho or not os.path.exists(caminho):
        return f"O caminho salvo para {nome_exibicao} não foi encontrado."

    pasta_app = os.path.dirname(caminho)
    nome_limpo = nome_exibicao.split("(")[0].strip()
    try:
        if caminho.lower().endswith(".exe"):
            subprocess.Popen([caminho], cwd=pasta_app if os.path.isdir(pasta_app) else None)
        else:
            os.startfile(caminho)
        return f"Iniciando {nome_limpo}."
    except Exception:
        try:
            os.startfile(caminho)
            return f"Iniciando {nome_limpo}."
        except Exception as e:
            return f"Erro ao abrir {nome_limpo}: {str(e)}"


def abrir_aplicativo(nome_app: str) -> str:
    alvo = normalizar_frase(nome_app)
    alvo_sem_espaco = remover_acentos(alvo).replace(" ", "")
    apps_ativos = carregar_apps_ativos()

    for chave, info in apps_ativos.items():
        termos = [chave, info.get("nome", "").split("(")[0]] + info.get("apelidos", [])
        termos_norm = [normalizar_frase(t) for t in termos if t]
        termos_compactos = [remover_acentos(t).replace(" ", "") for t in termos_norm]

        if alvo in termos_norm or alvo_sem_espaco in termos_compactos:
            return _executar_caminho(info.get("caminho_abrir", ""), info.get("nome", chave))

    if alvo == "vscode":
        return _abrir_vscode_direto()

    return f"O aplicativo {nome_app} não está ativo nas configurações."


def verificar_abertura_rapida(frase: str, modo_direto: bool = False) -> str:
    frase_norm = normalizar_frase(frase)
    if not modo_direto and not any(v in frase_norm for v in VERBOS_ABRIR):
        return ""

    if "vscode" in frase_norm:
        return abrir_aplicativo("vscode")

    frase_compacta = remover_acentos(frase_norm).replace(" ", "")
    apps_ativos = carregar_apps_ativos()

    candidatos = []
    for chave, info in apps_ativos.items():
        nome_curto = info.get("nome", "").split("(")[0].strip()
        for termo in [chave, nome_curto] + info.get("apelidos", []):
            t_norm = normalizar_frase(termo)
            if t_norm:
                candidatos.append((t_norm, chave))

    candidatos.sort(key=lambda x: len(x[0]), reverse=True)

    for gatilho, chave_real in candidatos:
        gatilho_compacto = remover_acentos(gatilho).replace(" ", "")
        if gatilho in frase_norm or (len(gatilho_compacto) >= 2 and gatilho_compacto in frase_compacta):
            return abrir_aplicativo(chave_real)

    return ""