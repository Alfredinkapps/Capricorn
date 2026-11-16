import os
import re
import sys
import json
import math
import time
import winreg
import threading
import tkinter as tk
from tkinter import filedialog
import pygame
import pystray
from PIL import Image, ImageDraw

# =====================================================================
# 1. CAMINHOS, INICIALIZAÇÃO E CONFIGURAÇÕES GERAIS
# =====================================================================

if getattr(sys, "frozen", False):
    PASTA_PROJETO = os.path.dirname(sys.executable)
else:
    PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
    PASTA_PROJETO = os.path.dirname(PASTA_ATUAL) if os.path.basename(PASTA_ATUAL).lower() == "src" else PASTA_ATUAL

ARQUIVO_CONFIG = os.path.join(PASTA_PROJETO, "capri_config.json")

try:
    pygame.mixer.init()
except Exception as e:
    print(f"[Aviso Mixer Pygame]: {e}")


def configurar_inicializacao_windows(ativar: bool = True):
    """Registra ou remove a Capri da inicialização automática do Windows."""
    chave_reg = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_app = "CapriAssistant"
    try:
        if getattr(sys, "frozen", False):
            caminho_exec = f'"{sys.executable}"'
        else:
            script_principal = os.path.join(PASTA_PROJETO, "src", "capri_core.py")
            if not os.path.exists(script_principal):
                script_principal = os.path.join(PASTA_PROJETO, "capri_core.py")
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


def carregar_configuracoes() -> dict:
    padrao = {
        "gemini_api_key": "",
        "fish_api_key": "",
        "fish_voice_id": "",
        "iniciar_com_windows": True,
        "apps": {}
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
        with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Erro ao salvar capri_config.json]: {e}")


# =====================================================================
# 2. SCANNER INTELIGENTE DE APLICATIVOS PADRÕES (SEM LIXO DO WINDOWS)
# =====================================================================

APPS_PADROES_PERMITIDOS = {
    # Navegadores
    "firefox": ("Firefox", "firefox.exe", ["firefox", "mozilla", "navegador"]),
    "google chrome": ("Google Chrome", "chrome.exe", ["chrome", "google chrome"]),
    "microsoft edge": ("Microsoft Edge", "msedge.exe", ["edge", "microsoft edge"]),
    "brave": ("Brave", "brave.exe", ["brave"]),
    "opera": ("Opera", "opera.exe", ["opera"]),
    "opera gx": ("Opera GX", "opera.exe", ["opera gx"]),

    # Comunicação
    "discord": ("Discord", "Discord.exe", ["discord", "disc"]),
    "telegram": ("Telegram", "Telegram.exe", ["telegram"]),
    "whatsapp": ("WhatsApp", "WhatsApp.exe", ["whatsapp", "zap"]),

    # Jogos e Launchers
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

    # Música, Mídia e Criação
    "spotify": ("Spotify", "Spotify.exe", ["spotify"]),
    "obs studio": ("OBS Studio", "obs64.exe", ["obs", "obs studio", "gravador"]),
    "vlc media player": ("VLC Media Player", "vlc.exe", ["vlc"]),
    "audacity": ("Audacity", "audacity.exe", ["audacity"]),
    "capcut": ("CapCut", "CapCut.exe", ["capcut"]),
    "canva": ("Canva", "Canva.exe", ["canva"]),
    "blender": ("Blender", "blender.exe", ["blender"]),
    "gimp": ("GIMP", "gimp.exe", ["gimp"]),

    # Desenvolvimento e Estudos
    "visual studio code": ("Visual Studio Code", "Code.exe", ["vscode", "vs code", "visual studio code"]),
    "git bash": ("Git Bash", "git-bash.exe", ["git bash"]),
    "postman": ("Postman", "Postman.exe", ["postman"]),
    "docker desktop": ("Docker Desktop", "Docker Desktop.exe", ["docker"]),
    "android studio": ("Android Studio", "studio64.exe", ["android studio"]),
    "pycharm": ("PyCharm", "pycharm64.exe", ["pycharm"]),
    "cursor": ("Cursor", "Cursor.exe", ["cursor"]),
    "notion": ("Notion", "Notion.exe", ["notion"]),
    "obsidian": ("Obsidian", "Obsidian.exe", ["obsidian"]),

    # Office e Utilitários
    "word": ("Microsoft Word", "WINWORD.EXE", ["word"]),
    "excel": ("Microsoft Excel", "EXCEL.EXE", ["excel"]),
    "powerpoint": ("PowerPoint", "POWERPNT.EXE", ["powerpoint", "power point"]),
    "winrar": ("WinRAR", "WinRAR.exe", ["winrar"]),
    "7-zip file manager": ("7-Zip", "7zFM.exe", ["7zip", "7-zip"]),
    "qbittorrent": ("qBittorrent", "qbittorrent.exe", ["qbittorrent", "torrent"]),
}

UTILITARIOS_NATIVOS_WINDOWS = {
    "notepad": {
        "nome": "Notepad",
        "caminho_abrir": "notepad.exe",
        "executavel": "notepad.exe",
        "apelidos": ["notepad", "bloco de notas", "notas"]
    },
    "cmd": {
        "nome": "Prompt de Comando (CMD)",
        "caminho_abrir": "cmd.exe",
        "executavel": "cmd.exe",
        "apelidos": ["cmd", "prompt de comando", "terminal"]
    },
    "calculadora": {
        "nome": "Calculadora",
        "caminho_abrir": "calc.exe",
        "executavel": "CalculatorApp.exe",
        "apelidos": ["calculadora", "calc"]
    },
    "explorer": {
        "nome": "Explorador de Arquivos",
        "caminho_abrir": "explorer.exe",
        "executavel": "explorer.exe",
        "apelidos": ["explorador de arquivos", "arquivos", "pastas"]
    },
    "mspaint": {
        "nome": "Paint",
        "caminho_abrir": "mspaint.exe",
        "executavel": "mspaint.exe",
        "apelidos": ["paint", "mspaint"]
    },
    "taskmgr": {
        "nome": "Gerenciador de Tarefas",
        "caminho_abrir": "taskmgr.exe",
        "executavel": "Taskmgr.exe",
        "apelidos": ["gerenciador de tarefas", "taskmgr"]
    },
}

TERMOS_BLOQUEADOS_ATALHO = (
    "uninstall", "desinstalar", "setup", "installer", "ajuda", "help", "readme",
    "documentation", "website", "command prompt", "privativa", "private", "odbc",
    "narrator", "on-screen", "performance monitor", "última versão", "ultima versao",
    "32-bit", "64-bit", "updater", "update", "diagnostic", "manual", "license",
    "release notes", "safe mode", "modo de segurança", "server", "reparar", "repair"
)


def escanear_e_atualizar_apps(config: dict) -> dict:
    """Mantém apenas apps padrões conhecidos + utilitários do Windows e preserva os .exe do usuário."""
    apps_antigos = config.get("apps", {})
    novos_apps = {}

    # 1. Preserva 100% dos executáveis adicionados manualmente pelo usuário
    for chave, dados in apps_antigos.items():
        if dados.get("personalizado", False):
            novos_apps[chave] = dados

    # 2. Adiciona utilitários nativos essenciais
    for chave_nat, dados_nat in UTILITARIOS_NATIVOS_WINDOWS.items():
        ja_ativo = apps_antigos.get(chave_nat, {}).get("ativo", True)
        novos_apps[chave_nat] = {
            "nome": dados_nat["nome"],
            "caminho_abrir": dados_nat["caminho_abrir"],
            "executavel": dados_nat["executavel"],
            "ativo": ja_ativo,
            "personalizado": False,
            "apelidos": dados_nat["apelidos"]
        }

    # 3. Escaneia o Menu Iniciar filtrando apenas a lista de apps padrões
    pastas_menu = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
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
                                "apelidos": apelidos_padrao
                            }
                        break

    config["apps"] = novos_apps
    salvar_configuracoes(config)
    return config


# =====================================================================
# 3. INTERFACE GRÁFICA PRINCIPAL (HUD) E MENU CYBERPUNK 2077
# =====================================================================

class CapriHUD:
    def __init__(self):
        self.config = escanear_e_atualizar_apps(carregar_configuracoes())
        self.rodando = True
        self.pausada = False
        self.reiniciar_ia = False
        self.nivel_voz = 0.0
        self.fase_onda = 0.0
        self.estado_atual = "INICIALIZANDO..."
        self.cor_atual = "#00F0FF"
        self.janela_config = None
        self.icone_bandeja = None

        self.root = tk.Tk()
        self.root.title("CAPRI HUD")
        self._aplicar_icone_janela(self.root)
        self.root.geometry("330x185+40+40")
        self.root.configure(bg="#090D16")
        self.root.overrideredirect(True)

        self._offset_x = 0
        self._offset_y = 0

        # Moldura externa neon
        self.borda = tk.Frame(self.root, bg="#00F0FF", padx=1, pady=1)
        self.borda.pack(fill="both", expand=True)

        self.painel = tk.Frame(self.borda, bg="#090D16")
        self.painel.pack(fill="both", expand=True)

        # Barra de título arrastável
        self.barra_topo = tk.Frame(self.painel, bg="#0F172A", height=28)
        self.barra_topo.pack(fill="x")
        self.barra_topo.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.barra_topo.bind("<B1-Motion>", self._arrastar_janela)

        self.lbl_titulo = tk.Label(
            self.barra_topo, text="◆ CAPRI // SYS.0.1.3",
            fg="#00F0FF", bg="#0F172A", font=("Consolas", 9, "bold")
        )
        self.lbl_titulo.pack(side="left", padx=8, pady=4)
        self.lbl_titulo.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.lbl_titulo.bind("<B1-Motion>", self._arrastar_janela)

        # Botões do topo (Fechar para bandeja, Configurações e Mute)
        self.btn_fechar = tk.Button(
            self.barra_topo, text="✕", fg="#94A3B8", bg="#0F172A",
            activebackground="#FF0055", activeforeground="#FFFFFF",
            font=("Consolas", 9, "bold"), relief="flat", bd=0, cursor="hand2",
            command=self.ocultar_para_bandeja, padx=6
        )
        self.btn_fechar.pack(side="right", padx=(2, 4))

        self.btn_config = tk.Button(
            self.barra_topo, text="⚙", fg="#00F0FF", bg="#0F172A",
            activebackground="#1E293B", activeforeground="#54F2F2",
            font=("Consolas", 10, "bold"), relief="flat", bd=0, cursor="hand2",
            command=self.abrir_configuracoes, padx=6
        )
        self.btn_config.pack(side="right", padx=2)

        self.btn_pausa = tk.Button(
            self.barra_topo, text="MIC ON", fg="#090D16", bg="#00FF66",
            activebackground="#00CC52", activeforeground="#090D16",
            font=("Consolas", 8, "bold"), relief="flat", bd=0, cursor="hand2",
            command=self.alternar_pausa, padx=6
        )
        self.btn_pausa.pack(side="right", padx=4, pady=3)

        # Status principal
        self.lbl_estado = tk.Label(
            self.painel, text="EM ESPERA",
            fg="#00F0FF", bg="#090D16", font=("Consolas", 12, "bold")
        )
        self.lbl_estado.pack(pady=(10, 2))

        # Visualizador de ondas de voz
        self.canvas_ondas = tk.Canvas(
            self.painel, width=290, height=58,
            bg="#090D16", highlightthickness=0
        )
        self.canvas_ondas.pack(pady=4)

        # Legenda fixa: "Diga, CAPRI"
        self.lbl_legenda = tk.Label(
            self.painel, text="Diga, CAPRI",
            fg="#94A3B8", bg="#090D16", font=("Consolas", 9, "bold")
        )
        self.lbl_legenda.pack(pady=(4, 8))

        self._iniciar_bandeja_sistema()
        self._animar_hud()

        if not self.config.get("gemini_api_key"):
            self.root.after(600, self.abrir_configuracoes)

    def _iniciar_arraste(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def _arrastar_janela(self, event):
        x = self.root.winfo_pointerx() - self._offset_x
        y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{x}+{y}")

    def _animar_hud(self):
        if not self.rodando:
            return
        try:
            self.canvas_ondas.delete("all")
            largura, altura = 290, 58
            meio_y = altura // 2
            num_barras = 29
            espacamento = largura / num_barras
            self.fase_onda += 0.25

            for i in range(num_barras):
                x = i * espacamento + (espacamento / 2)
                if self.pausada:
                    alt_barra = 2
                    cor_barra = "#475569"
                elif self.nivel_voz > 0.02:
                    fator_centro = 1.0 - abs((i - num_barras / 2) / (num_barras / 2))
                    oscilacao = abs(math.sin(self.fase_onda + i * 0.45))
                    alt_barra = max(3, int(self.nivel_voz * 48 * fator_centro * (0.4 + 0.6 * oscilacao)))
                    cor_barra = self.cor_atual
                else:
                    oscilacao_suave = abs(math.sin(self.fase_onda * 0.4 + i * 0.3))
                    alt_barra = 2 + int(oscilacao_suave * 3)
                    cor_barra = self.cor_atual

                self.canvas_ondas.create_line(
                    x, meio_y - alt_barra / 2,
                    x, meio_y + alt_barra / 2,
                    fill=cor_barra, width=3, capstyle="round"
                )
        except Exception:
            pass

        if self.rodando:
            self.root.after(45, self._animar_hud)

    def atualizar_estado(self, novo_estado: str, cor: str = "#00F0FF", legenda: str = ""):
        """Atualiza o status e a cor da borda mantendo 'Diga, CAPRI' fixo."""
        self.estado_atual = novo_estado
        self.cor_atual = cor

        def _atualizar_ui():
            if hasattr(self, "lbl_estado"):
                self.lbl_estado.configure(text=novo_estado, fg=cor)
            if hasattr(self, "borda"):
                self.borda.configure(bg=cor)
            if hasattr(self, "lbl_legenda"):
                self.lbl_legenda.configure(text="Diga, CAPRI")

        try:
            self.root.after(0, _atualizar_ui)
        except Exception:
            pass

    def alternar_pausa(self, *args):
        self.pausada = not self.pausada
        if self.pausada:
            self.btn_pausa.configure(text="MUTADA", bg="#FF0055", fg="#FFFFFF")
            self.atualizar_estado("MIC SILENCIADO", "#FF0055")
        else:
            self.btn_pausa.configure(text="MIC ON", bg="#00FF66", fg="#090D16")
            self.atualizar_estado("EM ESPERA", "#00F0FF")

    def _obter_pasta_assets(self) -> str:
        """Localiza a pasta assets tanto rodando pelo Python quanto dentro do .exe compilado."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            pasta_empacotada = os.path.join(sys._MEIPASS, "assets")
            if os.path.exists(pasta_empacotada):
                return pasta_empacotada
        pasta_local = os.path.join(PASTA_PROJETO, "assets")
        os.makedirs(pasta_local, exist_ok=True)
        return pasta_local

    def _obter_caminho_icone(self) -> str:
        """Procura icone.png ou icone.ico dentro da pasta assets/ e gera o .ico automaticamente."""
        pasta_assets = self._obter_pasta_assets()
        caminho_ico = os.path.join(pasta_assets, "icone.ico")
        caminho_png = os.path.join(pasta_assets, "icone.png")

        if os.path.exists(caminho_png):
            try:
                if not os.path.exists(caminho_ico) or os.path.getmtime(caminho_png) > os.path.getmtime(caminho_ico):
                    img = Image.open(caminho_png).convert("RGBA")
                    img.save(caminho_ico, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
                return caminho_ico
            except Exception as e:
                print(f"[Aviso conversão de ícone]: {e}")
                return caminho_png

        if os.path.exists(caminho_ico):
            return caminho_ico
        return ""

    def _aplicar_icone_janela(self, janela):
        """Aplica o ícone da pasta assets/ na janela e no Gerenciador de Tarefas."""
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("capricorn.capri.assistant")
        except Exception:
            pass

        caminho = self._obter_caminho_icone()
        if not caminho:
            return
        try:
            if caminho.lower().endswith(".ico"):
                janela.iconbitmap(caminho)
            img_tk = Image.open(caminho).convert("RGBA")
            from PIL import ImageTk
            foto = ImageTk.PhotoImage(img_tk)
            janela.iconphoto(True, foto)
            janela._icone_ref = foto
        except Exception as e:
            print(f"[Aviso ao aplicar ícone na janela]: {e}")

    def _criar_imagem_icone(self):
        """Carrega o ícone da pasta assets/ para a bandeja do Windows."""
        pasta_assets = self._obter_pasta_assets()
        for nome_arq in ("icone.png", "icone.ico"):
            caminho = os.path.join(pasta_assets, nome_arq)
            if os.path.exists(caminho):
                try:
                    return Image.open(caminho).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
                except Exception:
                    pass

        img = Image.new("RGBA", (64, 64), (9, 13, 22, 255))
        d = ImageDraw.Draw(img)
        d.polygon([(32, 6), (58, 32), (32, 58), (6, 32)], outline=(0, 240, 255, 255), width=4)
        d.ellipse((22, 22, 42, 42), fill=(232, 80, 75, 255))
        return img

    def _iniciar_bandeja_sistema(self):
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Mostrar HUD", lambda: self.root.after(0, self.mostrar_da_bandeja)),
                pystray.MenuItem("Configurações", lambda: self.root.after(0, self.abrir_configuracoes)),
                pystray.MenuItem("Mutada / Ativa", lambda: self.root.after(0, self.alternar_pausa)),
                pystray.MenuItem("Encerrar Capri", lambda: self.root.after(0, self.desligar_tudo))
            )
            self.icone_bandeja = pystray.Icon("Capri", self._criar_imagem_icone(), "Capri Assistant", menu)
            threading.Thread(target=self.icone_bandeja.run, daemon=True).start()
        except Exception as e:
            print(f"[Aviso Bandeja]: {e}")

    def ocultar_para_bandeja(self):
        self.root.withdraw()

    def mostrar_da_bandeja(self):
        self.root.deiconify()
        self.root.lift()

    def desligar_tudo(self):
        self.rodando = False
        try:
            if self.icone_bandeja:
                self.icone_bandeja.stop()
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    # =====================================================================
    # 4. CADASTRO DE EXECUTÁVEL (.EXE) E MENU CYBERPUNK 2077
    # =====================================================================

    def salvar_executavel_personalizado(self, caminho_arquivo: str, nome_chamada: str) -> bool:
        """Salva o executável escolhido manualmente com variações de voz no capri_config.json."""
        if not caminho_arquivo or not nome_chamada.strip():
            return False

        apelido_limpo = nome_chamada.strip()
        chave = apelido_limpo.lower()

        variacoes = {chave, chave.replace(" ", "")}
        variacoes.add(re.sub(r"([a-zA-Z])(\d)", r"\1 \2", chave))
        if len(chave) <= 5:
            variacoes.add(" ".join(list(chave.replace(" ", ""))))

        nome_exe = os.path.basename(caminho_arquivo)
        if not nome_exe.lower().endswith(".exe"):
            nome_exe = ""

        if "apps" not in self.config:
            self.config["apps"] = {}

        self.config["apps"][chave] = {
            "nome": f"{apelido_limpo.upper()} ({os.path.basename(caminho_arquivo)})",
            "caminho_abrir": caminho_arquivo,
            "executavel": nome_exe,
            "ativo": True,
            "personalizado": True,
            "apelidos": list(variacoes)
        }
        salvar_configuracoes(self.config)
        return True

    def adicionar_executavel_manual(self, callback_atualizar_lista=None):
        """Abre o seletor de arquivos do Windows e pergunta como o executável deve ser chamado."""
        janela_pai = getattr(self, "janela_config", None)
        if not (janela_pai and janela_pai.winfo_exists()):
            janela_pai = self.root

        caminho = filedialog.askopenfilename(
            parent=janela_pai,
            title="Selecione o Executável ou Atalho do Programa",
            filetypes=[
                ("Executáveis e Atalhos", "*.exe *.lnk *.url *.bat *.cmd"),
                ("Todos os arquivos", "*.*")
            ]
        )
        if not caminho:
            return

        BG_DARK = "#120912"
        CORAL = "#E8504B"
        CYAN = "#54F2F2"
        BORDER_RED = "#7A282A"

        dialogo = tk.Toplevel(self.root)
        dialogo.title("CAPRI // REGISTRAR EXECUTÁVEL")
        dialogo.geometry("460x235")
        dialogo.configure(bg=BG_DARK)
        dialogo.attributes("-topmost", True)
        dialogo.resizable(False, False)

        tk.Label(
            dialogo, text="EXECUTÁVEL DETECTADO",
            fg=CYAN, bg=BG_DARK, font=("Consolas", 11, "bold")
        ).pack(pady=(16, 2))

        tk.Frame(dialogo, bg=CYAN, height=1).pack(fill="x", padx=30, pady=(0, 8))

        tk.Label(
            dialogo, text=os.path.basename(caminho),
            fg=CORAL, bg=BG_DARK, font=("Consolas", 9, "bold")
        ).pack(pady=(0, 10))

        tk.Label(
            dialogo, text="Como você quer chamar este executável por voz? (Ex: CS2)",
            fg="#E2E8F0", bg=BG_DARK, font=("Consolas", 9)
        ).pack(pady=2)

        borda_input = tk.Frame(dialogo, bg=BORDER_RED, padx=1, pady=1)
        borda_input.pack(pady=8)

        entrada_nome = tk.Entry(
            borda_input, bg="#1C0D1B", fg=CYAN, insertbackground=CYAN,
            font=("Consolas", 12, "bold"), relief="flat", justify="center", width=28
        )
        entrada_nome.pack(ipady=5)
        sugestao = os.path.splitext(os.path.basename(caminho))[0]
        entrada_nome.insert(0, sugestao)
        entrada_nome.select_range(0, tk.END)
        entrada_nome.focus_set()

        def _confirmar(event=None):
            nome_escolhido = entrada_nome.get().strip()
            if nome_escolhido:
                self.salvar_executavel_personalizado(caminho, nome_escolhido)
                dialogo.destroy()
                if callback_atualizar_lista:
                    callback_atualizar_lista()

        entrada_nome.bind("<Return>", _confirmar)

        borda_btn = tk.Frame(dialogo, bg=CORAL, padx=1, pady=1)
        borda_btn.pack(pady=8)
        tk.Button(
            borda_btn, text="SALVAR GATILHO DE VOZ", bg=BG_DARK, fg=CYAN,
            activebackground="#261224", activeforeground=CYAN,
            font=("Consolas", 10, "bold"), relief="flat", cursor="hand2",
            command=_confirmar, padx=16, pady=4
        ).pack()

    def abrir_configuracoes(self, *args):
        """Menu de Configurações inspirado na interface do Cyberpunk 2077."""
        if not hasattr(self, "janela_config"):
            self.janela_config = None

        try:
            if self.janela_config is not None and self.janela_config.winfo_exists():
                self.janela_config.deiconify()
                self.janela_config.lift()
                self.janela_config.focus_force()
                return
        except Exception:
            self.janela_config = None

        try:
            self.config = escanear_e_atualizar_apps(self.config)
        except Exception:
            self.config = carregar_configuracoes()

        # Paleta Cyberpunk 2077
        BG_MAIN = "#120912"
        BG_ROW_HOVER = "#1E0E1D"
        BG_INPUT = "#190C19"
        CORAL = "#E8504B"
        CORAL_DIM = "#7A282A"
        CORAL_OFF = "#D6453D"
        CYAN = "#54F2F2"

        win = tk.Toplevel(self.root)
        self._aplicar_icone_janela(win)
        self.janela_config = win
        win.title("CAPRI // SYSTEM SETTINGS")
        win.geometry("860x580")
        win.minsize(780, 520)
        win.configure(bg=BG_MAIN)
        win.attributes("-topmost", True)

        # 1. Barra de Abas Superior
        barra_topo = tk.Frame(win, bg=BG_MAIN, pady=14)
        barra_topo.pack(fill="x", padx=28)

        container_abas = tk.Frame(barra_topo, bg=BG_MAIN)
        container_abas.pack(anchor="center")

        abas_nomes = ["APLICATIVOS", "APIS & VOZ", "SISTEMA"]
        aba_atual = tk.StringVar(value="APLICATIVOS")
        widgets_abas = {}

        def selecionar_aba(nome_aba: str):
            aba_atual.set(nome_aba)
            for nome, (lbl_t, barra_sub) in widgets_abas.items():
                if nome == nome_aba:
                    lbl_t.configure(fg=CYAN)
                    barra_sub.configure(bg=CYAN)
                else:
                    lbl_t.configure(fg=CORAL)
                    barra_sub.configure(bg=BG_MAIN)
            renderizar_conteudo_aba()

        for nome_aba in abas_nomes:
            f_aba = tk.Frame(container_abas, bg=BG_MAIN, padx=14)
            f_aba.pack(side="left")
            lbl_t = tk.Label(
                f_aba, text=nome_aba, fg=CORAL, bg=BG_MAIN,
                font=("Consolas", 11, "bold"), cursor="hand2"
            )
            lbl_t.pack()
            barra_sub = tk.Frame(f_aba, bg=BG_MAIN, height=2)
            barra_sub.pack(fill="x", pady=(3, 0))
            lbl_t.bind("<Button-1>", lambda e, n=nome_aba: selecionar_aba(n))
            widgets_abas[nome_aba] = (lbl_t, barra_sub)

        # 2. Corpo Principal (Coluna Esquerda + Coluna Direita)
        corpo = tk.Frame(win, bg=BG_MAIN)
        corpo.pack(fill="both", expand=True, padx=28, pady=(4, 6))

        col_esquerda = tk.Frame(corpo, bg=BG_MAIN, width=210)
        col_esquerda.pack(side="left", fill="y", padx=(0, 24))
        col_esquerda.pack_propagate(False)

        btn_bench = tk.Canvas(
            col_esquerda, width=195, height=38, bg=BG_MAIN,
            highlightthickness=0, cursor="hand2"
        )
        btn_bench.pack(pady=(8, 14), anchor="w")

        def desenhar_botao_lateral(hover=False):
            btn_bench.delete("all")
            cor_borda = CYAN if hover else CORAL_DIM
            cor_fundo = "#1E0E1D" if hover else "#160A16"
            pontos = [2, 2, 193, 2, 193, 28, 185, 36, 2, 36]
            btn_bench.create_polygon(pontos, fill=cor_fundo, outline=cor_borda, width=1.5)
            btn_bench.create_oval(12, 10, 28, 26, fill=CYAN, outline="")
            btn_bench.create_text(20, 18, text="+", fill=BG_MAIN, font=("Consolas", 11, "bold"))
            btn_bench.create_text(36, 19, text="ADICIONAR .EXE", anchor="w", fill=CYAN, font=("Consolas", 9, "bold"))

        desenhar_botao_lateral(False)
        btn_bench.bind("<Enter>", lambda e: desenhar_botao_lateral(True))
        btn_bench.bind("<Leave>", lambda e: desenhar_botao_lateral(False))
        btn_bench.bind("<Button-1>", lambda e: self.adicionar_executavel_manual(callback_atualizar_lista=renderizar_conteudo_aba))

        decor_canvas = tk.Canvas(col_esquerda, width=24, height=24, bg=BG_MAIN, highlightthickness=0)
        decor_canvas.pack(pady=60, padx=65, anchor="w")
        decor_canvas.create_rectangle(4, 4, 18, 18, outline=CYAN, width=1.5)
        decor_canvas.create_rectangle(8, 8, 14, 14, fill=CYAN, outline="")

        col_direita = tk.Frame(corpo, bg=BG_MAIN)
        col_direita.pack(side="left", fill="both", expand=True)

        # 3. Switch ON/OFF estilo Cyberpunk 2077
        def criar_switch_cyberpunk(parent, estado_inicial: bool, ao_alternar):
            cv = tk.Canvas(parent, width=118, height=26, bg=parent["bg"], highlightthickness=0, cursor="hand2")
            estado = [estado_inicial]

            def _desenhar():
                cv.delete("all")
                cv.configure(bg=parent["bg"])
                ativo = estado[0]

                cv.create_text(
                    32, 13,
                    text="ON" if ativo else "OFF",
                    fill=CYAN if ativo else CORAL,
                    font=("Consolas", 9, "bold"),
                    anchor="e"
                )

                x1, y1, x2, y2 = 42, 3, 114, 23
                pontos_caixa = [x1, y1, x2, y1, x2, y2 - 5, x2 - 5, y2, x1, y2]
                cv.create_polygon(
                    pontos_caixa,
                    fill="#160A16",
                    outline=CYAN if ativo else CORAL_DIM,
                    width=1.2
                )

                if ativo:
                    pts_bloco = [79, 5, 112, 5, 112, 17, 108, 21, 79, 21]
                    cv.create_polygon(pts_bloco, fill=CYAN, outline="")
                else:
                    cv.create_rectangle(44, 5, 77, 21, fill=CORAL_OFF, outline="")

            def _clicar(event=None):
                estado[0] = not estado[0]
                _desenhar()
                ao_alternar(estado[0])

            cv.bind("<Button-1>", _clicar)
            _desenhar()
            cv._redesenhar_fundo = _desenhar
            return cv

        def criar_divisor_secao(parent, titulo_secao: str):
            f_sec = tk.Frame(parent, bg=BG_MAIN)
            f_sec.pack(fill="x", pady=(12, 6))
            tk.Frame(f_sec, bg=CYAN, height=1).pack(fill="x")
            tk.Label(
                f_sec, text=titulo_secao, fg="#E2E8F0", bg=BG_MAIN,
                font=("Consolas", 10, "bold"), anchor="w"
            ).pack(fill="x", pady=(4, 0))

        vars_chaves = {
            "gemini_api_key": tk.StringVar(value=self.config.get("gemini_api_key", "")),
            "fish_api_key": tk.StringVar(value=self.config.get("fish_api_key", "")),
            "fish_voice_id": tk.StringVar(value=self.config.get("fish_voice_id", "")),
        }

        def salvar_chaves_em_memoria(*_):
            self.config["gemini_api_key"] = vars_chaves["gemini_api_key"].get().strip()
            self.config["fish_api_key"] = vars_chaves["fish_api_key"].get().strip()
            self.config["fish_voice_id"] = vars_chaves["fish_voice_id"].get().strip()
            salvar_configuracoes(self.config)

        for var in vars_chaves.values():
            var.trace_add("write", salvar_chaves_em_memoria)

        def renderizar_conteudo_aba():
            for w in col_direita.winfo_children():
                w.destroy()

            aba = aba_atual.get()

            if aba == "APLICATIVOS":
                canvas_lista = tk.Canvas(col_direita, bg=BG_MAIN, highlightthickness=0)
                scroll_bar = tk.Scrollbar(
                    col_direita, orient="vertical", command=canvas_lista.yview,
                    bg=BG_MAIN, troughcolor=BG_MAIN, activebackground=CORAL
                )
                frame_scroll = tk.Frame(canvas_lista, bg=BG_MAIN)
                win_id = canvas_lista.create_window((0, 0), window=frame_scroll, anchor="nw")

                canvas_lista.bind("<Configure>", lambda e: canvas_lista.itemconfig(win_id, width=e.width))
                frame_scroll.bind("<Configure>", lambda e: canvas_lista.configure(scrollregion=canvas_lista.bbox("all")))
                canvas_lista.configure(yscrollcommand=scroll_bar.set)

                canvas_lista.pack(side="left", fill="both", expand=True)
                scroll_bar.pack(side="right", fill="y", padx=(6, 0))

                def _rolar_mouse(event):
                    if canvas_lista.winfo_exists():
                        canvas_lista.yview_scroll(int(-1 * (event.delta / 120)), "units")

                canvas_lista.bind_all("<MouseWheel>", _rolar_mouse)

                apps_dict = self.config.get("apps", {})
                personalizados = [(k, v) for k, v in apps_dict.items() if v.get("personalizado", False)]
                sistema_apps = [(k, v) for k, v in apps_dict.items() if not v.get("personalizado", False)]

                personalizados.sort(key=lambda x: x[1].get("nome", x[0]).lower())
                sistema_apps.sort(key=lambda x: x[1].get("nome", x[0]).lower())

                def _adicionar_linha_app(chave_app, dados_app):
                    linha = tk.Frame(frame_scroll, bg=BG_MAIN, pady=3, padx=6)
                    linha.pack(fill="x", pady=1)

                    lbl = tk.Label(
                        linha, text=dados_app.get("nome", chave_app), fg=CORAL, bg=BG_MAIN,
                        font=("Consolas", 10, "bold"), anchor="w"
                    )
                    lbl.pack(side="left", fill="x", expand=True)

                    def _toggle(novo_estado, k=chave_app):
                        self.config["apps"][k]["ativo"] = novo_estado
                        salvar_configuracoes(self.config)

                    sw = criar_switch_cyberpunk(linha, dados_app.get("ativo", False), _toggle)
                    sw.pack(side="right")

                    def _on_enter(e):
                        linha.configure(bg=BG_ROW_HOVER)
                        lbl.configure(bg=BG_ROW_HOVER, fg=CYAN)
                        sw._redesenhar_fundo()

                    def _on_leave(e):
                        linha.configure(bg=BG_MAIN)
                        lbl.configure(bg=BG_MAIN, fg=CORAL)
                        sw._redesenhar_fundo()

                    for widget_hover in (linha, lbl):
                        widget_hover.bind("<Enter>", _on_enter)
                        widget_hover.bind("<Leave>", _on_leave)

                if personalizados:
                    criar_divisor_secao(frame_scroll, "Executáveis Personalizados (.EXE)")
                    for k, v in personalizados:
                        _adicionar_linha_app(k, v)

                criar_divisor_secao(frame_scroll, "Aplicativos Padrões do Sistema")
                for k, v in sistema_apps:
                    _adicionar_linha_app(k, v)

            elif aba == "APIS & VOZ":
                criar_divisor_secao(col_direita, "Credenciais de Inteligência Artificial & Voz")

                def _criar_linha_input(rotulo, var_tk, ocultar=False):
                    linha = tk.Frame(col_direita, bg=BG_MAIN, pady=8)
                    linha.pack(fill="x")
                    tk.Label(
                        linha, text=rotulo, fg=CORAL, bg=BG_MAIN,
                        font=("Consolas", 10, "bold"), anchor="w"
                    ).pack(side="left", fill="x", expand=True)
                    moldura = tk.Frame(linha, bg=CORAL_DIM, padx=1, pady=1)
                    moldura.pack(side="right")
                    ent = tk.Entry(
                        moldura, textvariable=var_tk, bg=BG_INPUT, fg=CYAN,
                        insertbackground=CYAN, font=("Consolas", 10, "bold"),
                        relief="flat", width=34, justify="center",
                        show="*" if ocultar else ""
                    )
                    ent.pack(ipady=4, ipadx=6)

                _criar_linha_input("Gemini API Key", vars_chaves["gemini_api_key"], ocultar=True)
                _criar_linha_input("Fish Audio API Key", vars_chaves["fish_api_key"], ocultar=True)
                _criar_linha_input("Fish Audio Voice ID", vars_chaves["fish_voice_id"], ocultar=False)

                criar_divisor_secao(col_direita, "Configuração de Módulos")

                def _linha_seletor(nome, valor):
                    f = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                    f.pack(fill="x")
                    tk.Label(f, text=nome, fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")).pack(side="left")
                    box = tk.Frame(f, bg=CORAL_DIM, padx=1, pady=1)
                    box.pack(side="right")
                    inner = tk.Frame(box, bg=BG_INPUT, width=260, height=26)
                    inner.pack_propagate(False)
                    inner.pack()
                    tk.Label(inner, text="◁", fg=CYAN, bg=BG_INPUT, font=("Consolas", 9)).pack(side="left", padx=8)
                    tk.Label(inner, text=valor, fg=CYAN, bg=BG_INPUT, font=("Consolas", 9, "bold")).pack(expand=True)
                    tk.Label(inner, text="▷", fg=CYAN, bg=BG_INPUT, font=("Consolas", 9)).pack(side="right", padx=8)

                _linha_seletor("Motor de Pesquisa", "Gemini 2.5 Flash")
                _linha_seletor("Controle de Mídia", "Spotify Desktop")

            elif aba == "SISTEMA":
                criar_divisor_secao(col_direita, "Preferências de Operação")

                linha_mute = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_mute.pack(fill="x")
                tk.Label(
                    linha_mute, text="Escuta de Microfone Ativa",
                    fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")
                ).pack(side="left")
                criar_switch_cyberpunk(
                    linha_mute,
                    not getattr(self, "pausada", False),
                    lambda ativo: self.alternar_pausa() if (ativo == getattr(self, "pausada", False)) else None
                ).pack(side="right")

                linha_startup = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_startup.pack(fill="x")
                tk.Label(
                    linha_startup, text="Iniciar junto com o Windows",
                    fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")
                ).pack(side="left")

                def _alternar_startup(ativo):
                    self.config["iniciar_com_windows"] = ativo
                    salvar_configuracoes(self.config)
                    configurar_inicializacao_windows(ativo)

                criar_switch_cyberpunk(
                    linha_startup,
                    self.config.get("iniciar_com_windows", True),
                    _alternar_startup
                ).pack(side="right")

        # 4. Rodapé Cyberpunk
        rodape = tk.Frame(win, bg=BG_MAIN, pady=12)
        rodape.pack(fill="x", padx=28, side="bottom")

        def fechar_e_aplicar(*_):
            try:
                win.unbind_all("<MouseWheel>")
            except Exception:
                pass
            salvar_chaves_em_memoria()
            self.reiniciar_ia = True
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", fechar_e_aplicar)

        borda_central = tk.Frame(rodape, bg=CORAL_DIM, padx=1, pady=1)
        borda_central.pack(anchor="center")
        tk.Button(
            borda_central, text="SALVAR E APLICAR", bg=BG_MAIN, fg=CYAN,
            activebackground=BG_ROW_HOVER, activeforeground=CYAN,
            font=("Consolas", 10, "bold"), relief="flat", cursor="hand2",
            padx=26, pady=5, command=fechar_e_aplicar
        ).pack()

        selecionar_aba("APLICATIVOS")