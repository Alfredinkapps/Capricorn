import os
import sys
import json
import shutil
import winreg
from typing import Any

# Raiz do projeto (sobe 2 níveis a partir de src/core/config.py)
if getattr(sys, "frozen", False):
    PASTA_PROJETO = os.path.dirname(sys.executable)
else:
    PASTA_CORE = os.path.dirname(os.path.abspath(__file__))
    PASTA_SRC = os.path.dirname(PASTA_CORE)
    PASTA_PROJETO = os.path.dirname(PASTA_SRC) if os.path.basename(PASTA_SRC).lower() == "src" else PASTA_SRC

PASTA_DATA = os.path.join(PASTA_PROJETO, "data")
PASTA_CACHE = os.path.join(PASTA_DATA, "cache")
ARQUIVO_CONFIG = os.path.join(PASTA_DATA, "capri_config.json")

os.makedirs(PASTA_DATA, exist_ok=True)
os.makedirs(PASTA_CACHE, exist_ok=True)


def configurar_inicializacao_windows(ativar: bool) -> bool:
    """Registra ou remove a Capri na inicialização do Windows em modo silencioso e sem terminal."""
    caminho_chave = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_valor = "Capri"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, caminho_chave, 0, winreg.KEY_SET_VALUE
        ) as chave:
            if ativar:
                if getattr(sys, "frozen", False):
                    comando = f'"{sys.executable}" --startup'
                else:
                    pasta_py = os.path.dirname(sys.executable)
                    pythonw = os.path.join(pasta_py, "pythonw.exe")
                    executavel = pythonw if os.path.exists(pythonw) else sys.executable
                    script_main = os.path.join(PASTA_PROJETO, "src", "main.py")
                    comando = f'"{executavel}" "{script_main}" --startup'
                winreg.SetValueEx(chave, nome_valor, 0, winreg.REG_SZ, comando)
            else:
                try:
                    winreg.DeleteValue(chave, nome_valor)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def _migrar_config_antigo_se_necessario() -> None:
    """Se existir capri_config.json na raiz e ainda não houver em data/, move automaticamente."""
    config_raiz = os.path.join(PASTA_PROJETO, "capri_config.json")
    if not os.path.exists(ARQUIVO_CONFIG) and os.path.exists(config_raiz):
        try:
            shutil.move(config_raiz, ARQUIVO_CONFIG)
            print("  [Config]: capri_config.json migrado automaticamente para data/.")
        except Exception as e:
            print(f"[Aviso Migração Config]: {e}")


def carregar_configuracoes() -> dict[str, Any]:
    _migrar_config_antigo_se_necessario()
    padrao: dict[str, Any] = {
        "provedor_ia": "Gemini",
        "gemini_api_key": "",
        "claude_api_key": "",
        "deepseek_api_key": "",
        "fish_api_key": "",
        "fish_voice_id": "",
        "spotify_client_id": "",
        "spotify_redirect_uri": "http://127.0.0.1:8888/callback",
        "iniciar_com_windows": True,
        "pose_padrao": "Padrao",
        "modo_recorte_transparente": False,
        "stt_offline": True,
        "voz_ativa": True,
        "tts_por_frase": True,
        "busca_web_ativa": True,
        "limiar_voz": 340,
        "apelidos_ativacao": ["capri", "cap", "capricornio"],
        "monitor_visao": 1,
        "modo_captura_visao": "auto",
        "apps": {},
    }
    if not os.path.exists(ARQUIVO_CONFIG):
        return padrao
    try:
        with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            return padrao
        for k, v in padrao.items():
            if k not in dados:
                dados[k] = v
        return dados
    except Exception:
        return padrao


def salvar_configuracoes(config: dict[str, Any]) -> None:
    try:
        os.makedirs(PASTA_DATA, exist_ok=True)
        with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Erro ao salvar capri_config.json]: {e}")