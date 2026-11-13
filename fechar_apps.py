import subprocess

# Dicionário com o nome real dos processos (.exe) no Gerenciador de Tarefas do Windows
MAPA_FECHAR = {
    "calculadora": "CalculatorApp.exe",
    "bloco de notas": "notepad.exe",
    "vscode": "Code.exe",
    "visual studio code": "Code.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "navegador": "firefox.exe",
    "discord": "Discord.exe",
    "steam": "steam.exe",
    "cmd": "cmd.exe"
}

def fechar_aplicativo(nome_app: str) -> str:
    """Fecha ou encerra um aplicativo que está aberto no computador do usuário.
    
    Args:
        nome_app: O nome do aplicativo em letras minúsculas (ex: 'vscode', 'calculadora', 'bloco de notas', 'chrome', 'firefox', 'navegador', 'discord', 'steam', 'cmd').
    """
    app_limpo = nome_app.lower().strip()
    processo = MAPA_FECHAR.get(app_limpo)
    
    if processo:
        print(f"⚙️ [Módulo Fechar: Encerrando '{app_limpo}' ({processo})...]")
        try:
            # /F força o fechamento, /IM busca pelo nome da imagem e /T fecha processos filhos
            resultado = subprocess.run(
                f"taskkill /F /IM {processo} /T",
                shell=True,
                capture_output=True,
                text=True
            )
            if resultado.returncode == 0:
                return f"Protocolo executado. O aplicativo {app_limpo} foi encerrado."
            else:
                return f"O aplicativo {app_limpo} não está aberto no momento."
        except Exception as e:
            return f"Erro ao tentar fechar {app_limpo}: {str(e)}"
            
    return f"O aplicativo {nome_app} ainda não está cadastrado no módulo de encerramento."


def verificar_fechamento_rapido(frase: str) -> str:
    """Verifica se a frase pede para fechar algum app da lista e executa na hora."""
    verbos_fechar = ["feche", "fechar", "fecha", "encerre", "encerrar", "finalizar", "mate"]
    
    if any(verbo in frase for verbo in verbos_fechar):
        for nome_app in MAPA_FECHAR.keys():
            if nome_app in frase:
                return fechar_aplicativo(nome_app)
    return ""