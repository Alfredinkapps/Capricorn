import os
import subprocess
from abrir_apps import carregar_apps_ativos
from dicionario_comandos import VERBOS_FECHAR, normalizar_frase, remover_acentos


def fechar_aplicativo(nome_app: str) -> str:
    alvo = normalizar_frase(nome_app)
    alvo_compacto = remover_acentos(alvo).replace(" ", "")
    apps_ativos = carregar_apps_ativos()

    chave_encontrada = None
    for chave, info in apps_ativos.items():
        nome_curto = info.get("nome", "").split("(")[0].strip()
        termos = [normalizar_frase(t) for t in ([chave, nome_curto] + info.get("apelidos", [])) if t]
        if alvo in termos or alvo_compacto in [remover_acentos(t).replace(" ", "") for t in termos]:
            chave_encontrada = chave
            break

    if not chave_encontrada:
        return f"Não encontrei {nome_app} ativo para fechar."

    info = apps_ativos[chave_encontrada]
    exe = info.get("executavel", "")
    nome_exibicao = info.get("nome", chave_encontrada).split("(")[0].strip()

    if not exe and info.get("caminho_abrir", "").lower().endswith(".exe"):
        exe = os.path.basename(info["caminho_abrir"])

    if not exe:
        return f"Não sei qual é o processo executável de {nome_exibicao}."

    subprocess.run(f'taskkill /F /IM "{exe}" /T', shell=True, creationflags=0x08000000)
    return f"Encerrando {nome_exibicao}."


def verificar_fechamento_rapido(frase: str) -> str:
    frase_norm = normalizar_frase(frase)
    if not any(v in frase_norm for v in VERBOS_FECHAR):
        return ""

    if "vscode" in frase_norm:
        subprocess.run('taskkill /F /IM "Code.exe" /T', shell=True, creationflags=0x08000000)
        return "Encerrando Visual Studio Code."

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
            return fechar_aplicativo(chave_real)

    return ""