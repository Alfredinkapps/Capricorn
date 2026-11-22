import os
import sys
import json
import shutil
import winreg

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


def configurar_inicializacao_windows(ativar: bool = True):
    """Registra ou remove a Capri da inicialização automática do Windows."""
    chave_reg = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_app = "CapriAssistant"
    try:
        if getattr(sys, "frozen", False):
            caminho_exec = f'"{sys.executable}"'
        else:
            script_principal = os.path.join(PASTA_PROJETO, "src", "main.py")
            caminho_exec = f'"{sys.executable}" "{script_principal}"'

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave_reg, 0, winreg.KEY_ALL_ACCESS) as key:
            if ativar:
                winreg.SetValueEx(key, nome_app, 0, winreg.REG_SZ, caminho_exec)
            else:
                try:
                    winreg.DeleteValue(key, nome_app)
                except FileNotFoundError:
                    pass
    except Exception as e:
        print(f"[Aviso Registro Windows]: {e}")


def _migrar_config_antigo_se_necessario():
    """Se existir capri_config.json na raiz e ainda não houver em data/, move automaticamente."""
    config_raiz = os.path.join(PASTA_PROJETO, "capri_config.json")
    if not os.path.exists(ARQUIVO_CONFIG) and os.path.exists(config_raiz):
        try:
            shutil.move(config_raiz, ARQUIVO_CONFIG)
            print("  [Config]: capri_config.json migrado automaticamente para data/.")
        except Exception as e:
            print(f"[Aviso Migração Config]: {e}")


def carregar_configuracoes() -> dict:
    _migrar_config_antigo_se_necessario()
    padrao = {
        "provedor_ia": "Gemini",
        "gemini_api_key": "",
        "claude_api_key": "",
        "deepseek_api_key": "",
        "fish_api_key": "",
        "fish_voice_id": "",
        "iniciar_com_windows": True,
        "pose_padrao": "Padrao",
        "modo_recorte_transparente": False,
        "stt_offline": True,
        "voz_ativa": True,
        "apps": {},
    }
    if not os.path.exists(ARQUIVO_CONFIG):
        return padrao
    try:
        with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
            dados = json.load(f)
        for k, v in padrao.items():
            if k not in dados:
                dados[k] = v
        return dados
    except Exception:
        return padrao


def salvar_configuracoes(config: dict):
    try:
        os.makedirs(PASTA_DATA, exist_ok=True)
        with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Erro ao salvar capri_config.json]: {e}")