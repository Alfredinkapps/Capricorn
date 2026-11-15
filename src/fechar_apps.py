import os
import re
import sys
import json
import subprocess

if getattr(sys, "frozen", False):
    PASTA_BASE = os.path.dirname(sys.executable)
else:
    PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
    PASTA_BASE = os.path.dirname(PASTA_ATUAL) if os.path.basename(PASTA_ATUAL).lower() == "src" else PASTA_ATUAL

ARQUIVO_CONFIG = os.path.join(PASTA_BASE, "capri_config.json")


def _normalizar_nome(texto: str) -> str:
    limpo = texto.lower().strip()
    limpo = re.sub(r"([a-zA-Z])\s+(\d)", r"\1\2", limpo)
    return re.sub(r"\s+", " ", limpo)


def carregar_apps_ativos() -> dict:
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
    alvo = _normalizar_nome(nome_app)
    alvo_compacto = alvo.replace(" ", "")
    apps_ativos = carregar_apps_ativos()

    chave_encontrada = None
    for chave, info in apps_ativos.items():
        termos = [_normalizar_nome(chave), _normalizar_nome(info.get("nome", ""))] + [
            _normalizar_nome(ap) for ap in info.get("apelidos", [])
        ]
        if alvo in termos or alvo_compacto in [t.replace(" ", "") for t in termos if t]:
            chave_encontrada = chave
            break

    if not chave_encontrada:
        return f"Não encontrei o aplicativo {nome_app} ativo para fechar."

    info = apps_ativos[chave_encontrada]
    exe = info.get("executavel", "")
    nome_exibicao = info.get("nome", chave_encontrada)

    if not exe and info.get("caminho_abrir", "").lower().endswith(".exe"):
        exe = os.path.basename(info["caminho_abrir"])

    if not exe:
        return f"Não sei qual é o processo executável de {nome_exibicao}."

    subprocess.run(f'taskkill /F /IM "{exe}" /T', shell=True, creationflags=0x08000000)
    return f"Encerrando {nome_exibicao}."


def verificar_fechamento_rapido(frase: str) -> str:
    verbos_fechar = ["feche", "fechar", "fecha", "encerre", "encerrar", "encerra", "finalizar", "matar"]
    if not any(v in frase for v in verbos_fechar):
        return ""

    frase_norm = _normalizar_nome(frase)
    frase_compacta = frase_norm.replace(" ", "")
    apps_ativos = carregar_apps_ativos()

    if any(v in frase_norm for v in ["vscode", "vs code", "v s code", "visual studio", "visual code"]):
        subprocess.run('taskkill /F /IM "Code.exe" /T', shell=True, creationflags=0x08000000)
        return "Encerrando Visual Studio Code."

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
            return fechar_aplicativo(chave_real)

    return ""