import os
import subprocess

# Dicionário com todos os aplicativos para abrir
MAPA_ABRIR = {
    "calculadora": "calc.exe",
    "bloco de notas": "notepad.exe",
    "vscode": "code",
    "visual studio code": "code",
    "chrome": "chrome",
    "firefox": "firefox",
    "navegador": "firefox",
    "discord": "discord:",
    "steam": "steam:",
    "cmd": "cmd.exe"
}

def abrir_aplicativo(nome_app: str) -> str:
    """Abre um aplicativo ou programa no computador do usuário.
    
    Args:
        nome_app: O nome do aplicativo em letras minúsculas (ex: 'vscode', 'calculadora', 'bloco de notas', 'chrome', 'firefox', 'navegador', 'discord', 'steam', 'cmd').
    """
    app_limpo = nome_app.lower().strip()
    comando = MAPA_ABRIR.get(app_limpo)
    
    if comando:
        print(f"⚙️ [Módulo Abrir: Iniciando '{app_limpo}'...]")
        try:
            os.startfile(comando)
            return f"Protocolo executado. Iniciando {app_limpo}."
        except Exception:
            try:
                subprocess.Popen(f"start {comando}", shell=True)
                return f"Protocolo executado. Iniciando {app_limpo}."
            except Exception as e:
                return f"Erro ao tentar abrir {app_limpo}: {str(e)}"
                
    return f"O aplicativo {nome_app} ainda não está cadastrado no módulo de abertura."


def verificar_abertura_rapida(frase: str) -> str:
    """Verifica se a frase pede para abrir algum app da lista e executa na hora."""
    verbos_abrir = ["abra", "abrir", "abre", "inicie", "iniciar", "ligar", "executar"]
    
    if any(verbo in frase for verbo in verbos_abrir):
        for nome_app in MAPA_ABRIR.keys():
            if nome_app in frase:
                return abrir_aplicativo(nome_app)
    return ""