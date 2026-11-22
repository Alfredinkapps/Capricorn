import os
from core.config import salvar_configuracoes

APPS_PADROES_PERMITIDOS = {
    "firefox": ("Firefox", "firefox.exe", ["firefox", "mozilla", "navegador"]),
    "google chrome": ("Google Chrome", "chrome.exe", ["chrome", "google chrome"]),
    "microsoft edge": ("Microsoft Edge", "msedge.exe", ["edge", "microsoft edge"]),
    "brave": ("Brave", "brave.exe", ["brave"]),
    "opera": ("Opera", "opera.exe", ["opera"]),
    "opera gx": ("Opera GX", "opera.exe", ["opera gx"]),
    "discord": ("Discord", "Discord.exe", ["discord", "disc"]),
    "telegram": ("Telegram", "Telegram.exe", ["telegram"]),
    "whatsapp": ("WhatsApp", "WhatsApp.exe", ["whatsapp", "zap"]),
    "steam": ("Steam", "steam.exe", ["steam"]),
    "epic games launcher": ("Epic Games", "EpicGamesLauncher.exe", ["epic", "epic games"]),
    "riot client": ("Riot Client", "RiotClientServices.exe", ["riot", "riot client"]),
    "valorant": ("VALORANT", "VALORANT-Win64-Shipping.exe", ["valorant", "vava"]),
    "battle.net": ("Battle.net", "Battle.net.exe", ["battlenet", "battle net"]),
    "ea": ("EA App", "EADesktop.exe", ["ea app", "origin"]),
    "ubisoft connect": ("Ubisoft Connect", "UbisoftConnect.exe", ["ubisoft", "uplay"]),
    "xbox": ("Xbox", "XboxPcApp.exe", ["xbox"]),
    "roblox player": ("Roblox", "RobloxPlayerBeta.exe", ["roblox"]),
    "minecraft launcher": ("Minecraft", "MinecraftLauncher.exe", ["minecraft", "mine"]),
    "spotify": ("Spotify", "Spotify.exe", ["spotify"]),
    "obs studio": ("OBS Studio", "obs64.exe", ["obs", "obs studio", "gravador"]),
    "vlc media player": ("VLC Media Player", "vlc.exe", ["vlc"]),
    "audacity": ("Audacity", "audacity.exe", ["audacity"]),
    "capcut": ("CapCut", "CapCut.exe", ["capcut"]),
    "canva": ("Canva", "Canva.exe", ["canva"]),
    "blender": ("Blender", "blender.exe", ["blender"]),
    "gimp": ("GIMP", "gimp.exe", ["gimp"]),
    "visual studio code": ("Visual Studio Code", "Code.exe", ["vscode", "vs code", "visual studio code"]),
    "git bash": ("Git Bash", "git-bash.exe", ["git bash"]),
    "postman": ("Postman", "Postman.exe", ["postman"]),
    "docker desktop": ("Docker Desktop", "Docker Desktop.exe", ["docker"]),
    "android studio": ("Android Studio", "studio64.exe", ["android studio"]),
    "pycharm": ("PyCharm", "pycharm64.exe", ["pycharm"]),
    "cursor": ("Cursor", "Cursor.exe", ["cursor"]),
    "notion": ("Notion", "Notion.exe", ["notion"]),
    "obsidian": ("Obsidian", "Obsidian.exe", ["obsidian"]),
    "word": ("Microsoft Word", "WINWORD.EXE", ["word"]),
    "excel": ("Microsoft Excel", "EXCEL.EXE", ["excel"]),
    "powerpoint": ("PowerPoint", "POWERPNT.EXE", ["powerpoint", "power point"]),
    "winrar": ("WinRAR", "WinRAR.exe", ["winrar"]),
    "7-zip file manager": ("7-Zip", "7zFM.exe", ["7zip", "7-zip"]),
    "qbittorrent": ("qBittorrent", "qbittorrent.exe", ["qbittorrent", "torrent"]),
}

UTILITARIOS_NATIVOS_WINDOWS = {
    "notepad": {"nome": "Notepad", "caminho_abrir": "notepad.exe", "executavel": "notepad.exe", "apelidos": ["notepad", "bloco de notas", "notas"]},
    "cmd": {"nome": "Prompt de Comando (CMD)", "caminho_abrir": "cmd.exe", "executavel": "cmd.exe", "apelidos": ["cmd", "prompt de comando", "terminal"]},
    "calculadora": {"nome": "Calculadora", "caminho_abrir": "calc.exe", "executavel": "CalculatorApp.exe", "apelidos": ["calculadora", "calc"]},
    "explorer": {"nome": "Explorador de Arquivos", "caminho_abrir": "explorer.exe", "executavel": "explorer.exe", "apelidos": ["explorador de arquivos", "arquivos", "pastas"]},
    "mspaint": {"nome": "Paint", "caminho_abrir": "mspaint.exe", "executavel": "mspaint.exe", "apelidos": ["paint", "mspaint"]},
    "taskmgr": {"nome": "Gerenciador de Tarefas", "caminho_abrir": "taskmgr.exe", "executavel": "Taskmgr.exe", "apelidos": ["gerenciador de tarefas", "taskmgr"]},
}

TERMOS_BLOQUEADOS_ATALHO = (
    "uninstall", "desinstalar", "setup", "installer", "ajuda", "help", "readme",
    "documentation", "website", "command prompt", "privativa", "private", "odbc",
    "narrator", "on-screen", "performance monitor", "última versão", "ultima versao",
    "32-bit", "64-bit", "updater", "update", "diagnostic", "manual", "license",
    "release notes", "safe mode", "modo de segurança", "server", "reparar", "repair",
)


def escanear_e_atualizar_apps(config: dict) -> dict:
    apps_antigos = config.get("apps", {})
    novos_apps = {}
    for chave, dados in apps_antigos.items():
        if dados.get("personalizado", False):
            novos_apps[chave] = dados

    for chave_nat, dados_nat in UTILITARIOS_NATIVOS_WINDOWS.items():
        ja_ativo = apps_antigos.get(chave_nat, {}).get("ativo", True)
        novos_apps[chave_nat] = {
            "nome": dados_nat["nome"],
            "caminho_abrir": dados_nat["caminho_abrir"],
            "executavel": dados_nat["executavel"],
            "ativo": ja_ativo,
            "personalizado": False,
            "apelidos": dados_nat["apelidos"],
        }

    pastas_menu = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    ]
    for pasta_base in pastas_menu:
        if not os.path.exists(pasta_base):
            continue
        for raiz, _, arquivos in os.walk(pasta_base):
            for arq in arquivos:
                if not arq.lower().endswith((".lnk", ".url")):
                    continue
                nome_atalho = os.path.splitext(arq)[0].strip()
                chave_atalho = nome_atalho.lower()
                if any(bloq in chave_atalho for bloq in TERMOS_BLOQUEADOS_ATALHO):
                    continue
                for padrao_chave, (nome_bonito, exe_padrao, apelidos_padrao) in APPS_PADROES_PERMITIDOS.items():
                    if chave_atalho == padrao_chave or chave_atalho.startswith(padrao_chave + " "):
                        if padrao_chave not in novos_apps:
                            ativo_ant = apps_antigos.get(padrao_chave, apps_antigos.get(chave_atalho, {})).get("ativo", True)
                            novos_apps[padrao_chave] = {
                                "nome": nome_bonito,
                                "caminho_abrir": os.path.join(raiz, arq),
                                "executavel": exe_padrao,
                                "ativo": ativo_ant,
                                "personalizado": False,
                                "apelidos": apelidos_padrao,
                            }
                        break

    config["apps"] = novos_apps
    salvar_configuracoes(config)
    return config