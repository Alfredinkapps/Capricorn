import os
import re
import sys
import json
import math
import time
import queue
import random
import zipfile
import winreg
import threading
import tkinter as tk
from tkinter import filedialog
import pygame
import pystray
from PIL import Image, ImageDraw, ImageTk, ImageOps

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
# 2. SCANNER INTELIGENTE DE APLICATIVOS PADRÕES (LISTA COMPLETA)
# =====================================================================
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
    "qbittorrent": ("qBittorrent", "qbittorrent.exe", ["qbittorrent", "torrent"])
}

UTILITARIOS_NATIVOS_WINDOWS = {
    "notepad": {"nome": "Notepad", "caminho_abrir": "notepad.exe", "executavel": "notepad.exe", "apelidos": ["notepad", "bloco de notas", "notas"]},
    "cmd": {"nome": "Prompt de Comando (CMD)", "caminho_abrir": "cmd.exe", "executavel": "cmd.exe", "apelidos": ["cmd", "prompt de comando", "terminal"]},
    "calculadora": {"nome": "Calculadora", "caminho_abrir": "calc.exe", "executavel": "CalculatorApp.exe", "apelidos": ["calculadora", "calc"]},
    "explorer": {"nome": "Explorador de Arquivos", "caminho_abrir": "explorer.exe", "executavel": "explorer.exe", "apelidos": ["explorador de arquivos", "arquivos", "pastas"]},
    "mspaint": {"nome": "Paint", "caminho_abrir": "mspaint.exe", "executavel": "mspaint.exe", "apelidos": ["paint", "mspaint"]},
    "taskmgr": {"nome": "Gerenciador de Tarefas", "caminho_abrir": "taskmgr.exe", "executavel": "Taskmgr.exe", "apelidos": ["gerenciador de tarefas", "taskmgr"]}
}

TERMOS_BLOQUEADOS_ATALHO = (
    "uninstall", "desinstalar", "setup", "installer", "ajuda", "help", "readme",
    "documentation", "website", "command prompt", "privativa", "private", "odbc",
    "narrator", "on-screen", "performance monitor", "última versão", "ultima versao",
    "32-bit", "64-bit", "updater", "update", "diagnostic", "manual", "license",
    "release notes", "safe mode", "modo de segurança", "server", "reparar", "repair"
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
            "apelidos": dados_nat["apelidos"]
        }
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
# 3. MOTOR DE SPRITES DINÂMICOS DA CAPRI (CACHE EM RAM + ANIMAÇÕES)
# =====================================================================
class GerenciadorSpritesCapri:
    """Indexa, extrai automaticamente (se estiver em .zip) e gerencia todos os sprites na RAM."""

    def __init__(self, pasta_assets: str, tamanho_alvo: tuple = (250, 200)):
        self.pasta_assets = pasta_assets
        self.tamanho_alvo = tamanho_alvo
        self.mapa_arquivos = {}
        self.cache_tk = {}
        self.cache_notas_tk = []

        self._extrair_zip_se_necessario()
        self._indexar_sprites()

    def _extrair_zip_se_necessario(self):
        pasta_v1 = os.path.join(self.pasta_assets, "capri", "sprites", "v1")
        if os.path.exists(pasta_v1):
            return

        locais_busca = [self.pasta_assets, PASTA_PROJETO]
        for local in locais_busca:
            if not os.path.exists(local):
                continue
            for arq in os.listdir(local):
                if arq.lower().endswith(".zip"):
                    caminho_zip = os.path.join(local, arq)
                    try:
                        with zipfile.ZipFile(caminho_zip, "r") as zf:
                            nomes = zf.namelist()
                            if any("capri/sprites/" in n or "capri-neutral.png" in n for n in nomes):
                                print(f"  [Sprites Capri]: Extraindo pacote '{arq}' para assets/...")
                                zf.extractall(self.pasta_assets)
                                print("  [Sprites Capri]: Sprites extraídos com sucesso!")
                                return
                    except Exception as e:
                        print(f"  [Aviso Extração ZIP]: {e}")

    def _indexar_sprites(self):
        self.mapa_arquivos.clear()
        for base_dir in (self.pasta_assets, os.path.join(PASTA_PROJETO, "capri"), os.path.join(PASTA_PROJETO, "default")):
            if not os.path.exists(base_dir):
                continue
            for raiz, _, arquivos in os.walk(base_dir):
                for arq in arquivos:
                    if arq.lower().endswith((".png", ".ico", ".mp3")):
                        chave = arq.lower()
                        caminho_completo = os.path.join(raiz, arq)
                        if chave not in self.mapa_arquivos or "v1" in raiz.lower():
                            self.mapa_arquivos[chave] = caminho_completo

    def tem_pacote_sprites(self) -> bool:
        return "capri-neutral.png" in self.mapa_arquivos

    def obter_caminho(self, nome_arquivo: str) -> str:
        return self.mapa_arquivos.get(nome_arquivo.lower(), "")

    def obter_sprite_tk(self, nome_arquivo: str, sobrepor_efeito: str = "") -> ImageTk.PhotoImage:
        chave_cache = f"{nome_arquivo.lower()}__{sobrepor_efeito.lower()}__{self.tamanho_alvo}"
        if chave_cache in self.cache_tk:
            return self.cache_tk[chave_cache]

        caminho = self.obter_caminho(nome_arquivo)
        if not caminho:
            caminho = self.obter_caminho("capri-neutral.png") or self.obter_caminho("avatar.png") or self.obter_caminho("icone.png")
        if not caminho or not os.path.exists(caminho):
            return None

        try:
            img = Image.open(caminho).convert("RGBA")
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)

            if sobrepor_efeito:
                caminho_ef = self.obter_caminho(sobrepor_efeito)
                if caminho_ef and os.path.exists(caminho_ef):
                    ef = Image.open(caminho_ef).convert("RGBA")
                    ef_bbox = ef.getbbox()
                    if ef_bbox:
                        ef = ef.crop(ef_bbox)
                    ef = ImageOps.contain(ef, (int(img.width * 0.42), int(img.height * 0.42)), Image.Resampling.LANCZOS)
                    img.alpha_composite(ef, (img.width - ef.width - 10, 10))

            img = ImageOps.contain(img, self.tamanho_alvo, Image.Resampling.LANCZOS)
            foto_tk = ImageTk.PhotoImage(img)
            self.cache_tk[chave_cache] = foto_tk
            return foto_tk
        except Exception as e:
            print(f"[Aviso Sprite {nome_arquivo}]: {e}")
            return None

    def obter_notas_musicais_tk(self) -> list:
        if self.cache_notas_tk:
            return self.cache_notas_tk
        nomes_notas = [
            "01-eighth-cyan.png",
            "02-beamed-lime.png",
            "03-quarter-pink.png",
            "04-sixteenth-violet.png"
        ]
        for nome in nomes_notas:
            caminho = self.obter_caminho(nome)
            if caminho and os.path.exists(caminho):
                try:
                    img = Image.open(caminho).convert("RGBA")
                    img = ImageOps.contain(img, (24, 24), Image.Resampling.LANCZOS)
                    self.cache_notas_tk.append(ImageTk.PhotoImage(img))
                except Exception:
                    pass
        return self.cache_notas_tk


# =====================================================================
# 4. INTERFACE GRÁFICA PRINCIPAL (SEM BOTÕES NO TOPO + CONTROLES ACESSÍVEIS)
# =====================================================================
class CapriHUD:
    BG_OUTER = "#11090E"
    BG_SCREEN = "#1B0B13"
    BG_SCANLINE = "#250F1A"
    BG_CARD = "#1D0E15"
    BG_BAR = "#170A10"
    BORDER_PINK = "#D45B72"
    BORDER_DIM = "#5E2A37"
    ACCENT_VIOLET = "#9B72FF"
    ACCENT_LIME = "#A3E635"
    ACCENT_CYAN = "#54F2F2"
    TEXT_WHITE = "#F1F5F9"
    TEXT_GRAY = "#A3969C"
    TEXT_PINK = "#F06A82"

    def __init__(self):
        self.config = escanear_e_atualizar_apps(carregar_configuracoes())
        self.rodando = True
        self.pausada = False
        self.reiniciar_ia = False
        self.limpar_contexto = False
        self.forcar_escuta_voz = False
        self.voz_mutada = not self.config.get("voz_ativa", True)
        self.painel_status_visivel = True

        self.fila_comandos_texto = queue.Queue()

        self.nivel_voz = 0.0
        self.fase_onda = 0.0
        self.pos_barra_progresso = 0.0
        self.estado_atual = "A LIGAR"
        self.subtitulo_card = "Iniciando núcleo local..."
        self.legenda_card = "Ainda preparando. Digite abaixo ou chame 'Capri' por voz."
        self.cor_atual = self.BORDER_PINK
        self.janela_config = None
        self.icone_bandeja = None

        # Controle de animação de sprites
        self.em_intro = True
        self.idx_intro = 0
        self.ultimo_frame_intro = 0.0
        self.proximo_piscar = time.time() + random.uniform(2.8, 5.5)
        self.etapa_piscar = 0
        self.ultimo_tick_piscar = 0.0
        self.expressao_idle_extra = ""
        self.fim_expressao_idle = 0.0
        self.ate_quando_headpat = 0.0
        self.ate_quando_musica = 0.0
        self.sprite_forcado = ""
        self.ate_quando_forcado = 0.0

        self.root = tk.Tk()
        self.root.title("CAPRI HUD")

        self.sprites = GerenciadorSpritesCapri(self._obter_pasta_assets(), tamanho_alvo=(240, 195))
        self._aplicar_icone_janela(self.root)

        # Altura compacta sem a área de botões do topo
        self.root.geometry("465x475+40+40")
        self.root.configure(bg=self.BG_OUTER)
        self.root.overrideredirect(True)

        self._offset_x = 0
        self._offset_y = 0

        self.main_frame = tk.Frame(self.root, bg=self.BG_OUTER, padx=10, pady=8)
        self.main_frame.pack(fill="both", expand=True)

        self._construir_visor_central()
        self._construir_barra_pesquisa()

        self._aplicar_modo_transparencia()
        self._iniciar_bandeja_sistema()
        self._animar_hud()

        tem_alguma_chave = any(
            self.config.get(k, "").strip()
            for k in ("gemini_api_key", "claude_api_key", "deepseek_api_key")
        )
        if not tem_alguma_chave:
            self.root.after(600, self.abrir_configuracoes)

    def _criar_botao_quadrado(self, parent, texto: str, comando, cor_borda=None, cor_texto=None, largura=28, altura=26):
        borda = cor_borda or self.BORDER_DIM
        fg = cor_texto or self.TEXT_PINK
        moldura = tk.Frame(parent, bg=borda, padx=1, pady=1)
        inner = tk.Frame(moldura, bg=self.BG_BAR, width=largura, height=altura)
        inner.pack_propagate(False)
        inner.pack()
        lbl = tk.Label(inner, text=texto, fg=fg, bg=self.BG_BAR, font=("Consolas", 9, "bold"), cursor="hand2")
        lbl.pack(expand=True, fill="both")

        def _enter(e):
            moldura.configure(bg=self.ACCENT_CYAN)
            lbl.configure(bg="#26111B")

        def _leave(e):
            moldura.configure(bg=moldura._cor_borda_atual)
            lbl.configure(bg=self.BG_BAR)

        moldura._cor_borda_atual = borda
        moldura.lbl = lbl
        lbl.bind("<Enter>", _enter)
        lbl.bind("<Leave>", _leave)
        lbl.bind("<Button-1>", lambda e: comando())
        return moldura

    def _construir_visor_central(self):
        self.container_central = tk.Frame(self.main_frame, bg=self.BG_OUTER)
        self.container_central.pack(fill="both", expand=True, pady=(0, 8))

        # Visor CRT dos Sprites (Inicia direto no topo da janela)
        self.canvas_sprite = tk.Canvas(
            self.container_central, width=445, height=255,
            bg=self.BG_SCREEN, highlightthickness=0, cursor="hand2"
        )
        self.canvas_sprite.pack(fill="both", expand=True)
        self.canvas_sprite.bind("<Button-1>", self._ao_clicar_sprite)
        self.canvas_sprite.bind("<B1-Motion>", self._arrastar_janela)

        # Card Central ("CAPRI pre-alpha" + Botões Acessíveis de Mute, Config e Minimizar)
        self.borda_card_status = tk.Frame(self.container_central, bg=self.BORDER_PINK, padx=1, pady=1)
        self.borda_card_status.pack(fill="x")

        self.card_status = tk.Frame(self.borda_card_status, bg=self.BG_CARD, padx=14, pady=10)
        self.card_status.pack(fill="x")
        self.card_status.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.card_status.bind("<B1-Motion>", self._arrastar_janela)

        f_titulo_card = tk.Frame(self.card_status, bg=self.BG_CARD)
        f_titulo_card.pack(fill="x", pady=(0, 6))
        f_titulo_card.bind("<ButtonPress-1>", self._iniciar_arraste)
        f_titulo_card.bind("<B1-Motion>", self._arrastar_janela)

        lbl_capri = tk.Label(
            f_titulo_card, text="CAPRI ",
            fg=self.TEXT_WHITE, bg=self.BG_CARD, font=("Consolas", 11, "bold")
        )
        lbl_capri.pack(side="left")
        lbl_capri.bind("<ButtonPress-1>", self._iniciar_arraste)
        lbl_capri.bind("<B1-Motion>", self._arrastar_janela)

        lbl_ver = tk.Label(
            f_titulo_card, text="pre-alpha",
            fg=self.TEXT_GRAY, bg=self.BG_CARD, font=("Consolas", 10, "bold")
        )
        lbl_ver.pack(side="left")
        lbl_ver.bind("<ButtonPress-1>", self._iniciar_arraste)
        lbl_ver.bind("<B1-Motion>", self._arrastar_janela)

        # Botões de acesso rápido direto no cabeçalho do Card Central
        f_controles_card = tk.Frame(f_titulo_card, bg=self.BG_CARD)
        f_controles_card.pack(side="right")

        self.btn_fechar = tk.Button(
            f_controles_card, text="—", fg=self.TEXT_GRAY, bg="#28131E",
            activebackground="#FF0055", activeforeground="#FFFFFF",
            font=("Consolas", 9, "bold"), relief="flat", bd=0, cursor="hand2",
            command=self.ocultar_para_bandeja, padx=7, pady=1
        )
        self.btn_fechar.pack(side="right", padx=(4, 0))

        self.btn_config = tk.Button(
            f_controles_card, text="⚙ CONFIG", fg=self.ACCENT_CYAN, bg="#28131E",
            activebackground="#381A2A", activeforeground="#FFFFFF",
            font=("Consolas", 8, "bold"), relief="flat", bd=0, cursor="hand2",
            command=self.abrir_configuracoes, padx=8, pady=2
        )
        self.btn_config.pack(side="right", padx=4)

        self.btn_pausa = tk.Button(
            f_controles_card, text="MIC ON", fg="#090D16", bg="#00FF66",
            activebackground="#00CC52", activeforeground="#090D16",
            font=("Consolas", 8, "bold"), relief="flat", bd=0, cursor="hand2",
            command=self.alternar_pausa, padx=8, pady=2
        )
        self.btn_pausa.pack(side="right", padx=4)

        self.lbl_subtitulo_card = tk.Label(
            self.card_status, text=self.subtitulo_card,
            fg=self.TEXT_WHITE, bg=self.BG_CARD, font=("Consolas", 10), anchor="w"
        )
        self.lbl_subtitulo_card.pack(fill="x", pady=(0, 8))

        self.canvas_progresso = tk.Canvas(
            self.card_status, height=4, bg="#38242E", highlightthickness=0
        )
        self.canvas_progresso.pack(fill="x", pady=(0, 10))

        self.lbl_legenda_card = tk.Label(
            self.card_status, text=self.legenda_card,
            fg=self.TEXT_GRAY, bg=self.BG_CARD, font=("Consolas", 9),
            anchor="w", justify="left", wraplength=415
        )
        self.lbl_legenda_card.pack(fill="x")

    def _construir_barra_pesquisa(self):
        """Barra inferior 'Conversar com Capri...' limpa com botões de Mutar, Configurações e Enviar."""
        self.borda_pesquisa = tk.Frame(self.main_frame, bg=self.BORDER_PINK, padx=1, pady=1)
        self.borda_pesquisa.pack(fill="x", side="bottom", pady=(2, 0))

        self.barra_pesquisa_inner = tk.Frame(self.borda_pesquisa, bg=self.BG_BAR, padx=8, pady=7)
        self.barra_pesquisa_inner.pack(fill="x")

        tk.Frame(self.barra_pesquisa_inner, bg=self.ACCENT_VIOLET, width=3, height=22).pack(side="left", padx=(2, 6))
        tk.Label(
            self.barra_pesquisa_inner, text="〰",
            fg=self.ACCENT_VIOLET, bg=self.BG_BAR, font=("Consolas", 10, "bold")
        ).pack(side="left", padx=(0, 6))

        self.placeholder_texto = "Conversar com Capri..."
        self.var_pesquisa = tk.StringVar(value=self.placeholder_texto)

        self.entry_pesquisa = tk.Entry(
            self.barra_pesquisa_inner,
            textvariable=self.var_pesquisa,
            bg=self.BG_BAR,
            fg=self.TEXT_GRAY,
            insertbackground=self.TEXT_PINK,
            font=("Consolas", 10),
            relief="flat",
            bd=0
        )
        self.entry_pesquisa.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)

        self.entry_pesquisa.bind("<Button-1>", self._focar_entrada_pesquisa)
        self.entry_pesquisa.bind("<FocusIn>", self._ao_ganhar_foco_pesquisa)
        self.entry_pesquisa.bind("<FocusOut>", self._ao_perder_foco_pesquisa)
        self.entry_pesquisa.bind("<Return>", self._submeter_pesquisa_interface)

        # Botões acessíveis na barra inferior: [🎙 Mutar] [⚙ Config] [↗ Enviar]
        f_acoes_barra = tk.Frame(self.barra_pesquisa_inner, bg=self.BG_BAR)
        f_acoes_barra.pack(side="right")

        self.btn_mic_barra = self._criar_botao_quadrado(
            f_acoes_barra, "🎙", self.alternar_pausa,
            cor_borda="#00FF66", cor_texto="#00FF66", largura=28, altura=25
        )
        self.btn_mic_barra.pack(side="left", padx=2)

        self.btn_cfg_barra = self._criar_botao_quadrado(
            f_acoes_barra, "⚙", self.abrir_configuracoes,
            cor_borda=self.ACCENT_CYAN, cor_texto=self.ACCENT_CYAN, largura=28, altura=25
        )
        self.btn_cfg_barra.pack(side="left", padx=2)

        self._criar_botao_quadrado(
            f_acoes_barra, "↗", self._submeter_pesquisa_interface,
            cor_borda=self.BORDER_PINK, cor_texto=self.TEXT_PINK, largura=28, altura=25
        ).pack(side="left", padx=(2, 0))

    # =====================================================================
    # FUNÇÕES DA BARRA DE PESQUISA E CONTROLES
    # =====================================================================
    def _focar_entrada_pesquisa(self, event=None):
        try:
            self.root.focus_force()
            self.entry_pesquisa.focus_set()
            if self.var_pesquisa.get() == self.placeholder_texto:
                self.var_pesquisa.set("")
                self.entry_pesquisa.configure(fg=self.TEXT_WHITE)
        except Exception:
            pass

    def _ao_ganhar_foco_pesquisa(self, event=None):
        if self.var_pesquisa.get() == self.placeholder_texto:
            self.var_pesquisa.set("")
            self.entry_pesquisa.configure(fg=self.TEXT_WHITE)

    def _ao_perder_foco_pesquisa(self, event=None):
        if not self.var_pesquisa.get().strip():
            self.var_pesquisa.set(self.placeholder_texto)
            self.entry_pesquisa.configure(fg=self.TEXT_GRAY)

    def _submeter_pesquisa_interface(self, event=None):
        texto = self.var_pesquisa.get().strip()
        if not texto or texto == self.placeholder_texto:
            return
        self.var_pesquisa.set("")
        self.entry_pesquisa.configure(fg=self.TEXT_WHITE)
        self.enviar_comando_texto(texto)

    def enviar_comando_texto(self, texto_comando: str):
        cmd = texto_comando.strip()
        if not cmd:
            return
        print(f"  [Barra de Pesquisa]: '{cmd}'")
        self.atualizar_estado("PROCESSANDO...", self.ACCENT_VIOLET, f"Você: \"{cmd}\"")
        self.fila_comandos_texto.put(cmd)

    def tem_comando_texto(self) -> bool:
        return not self.fila_comandos_texto.empty()

    def obter_comando_texto(self) -> str:
        try:
            return self.fila_comandos_texto.get_nowait()
        except queue.Empty:
            return ""

    def _aplicar_modo_transparencia(self):
        try:
            if self.config.get("modo_recorte_transparente", False):
                self.root.attributes("-alpha", 0.98)
                self.root.attributes("-transparentcolor", self.BG_SCREEN)
            else:
                self.root.attributes("-transparentcolor", "")
                self.root.attributes("-alpha", 0.94)
        except Exception:
            pass

    def _ao_clicar_sprite(self, event):
        self._iniciar_arraste(event)
        self.ate_quando_headpat = time.time() + 2.2

    def _obter_sprite_pose_base(self) -> str:
        pose = self.config.get("pose_padrao", "Padrao")
        mapa_poses = {
            "Padrao": "capri-neutral.png",
            "Bracos Cruzados": "capri-arms_crossed-neutral.png",
            "Mao na Cintura": "capri-hand_on_hip-neutral.png",
            "Mao no Queixo": "capri-chin_rest-neutral.png",
            "Sentada na Borda": "capri-sit_edge-neutral.png",
            "Sentada no Chao": "capri-sit_floor-neutral.png",
            "Agachada": "capri-crouch-neutral.png",
            "Reclinada": "capri-recline-neutral.png"
        }
        return mapa_poses.get(pose, "capri-neutral.png")

    def _selecionar_nome_sprite_atual(self) -> tuple[str, str]:
        agora = time.time()

        if self.em_intro and self.sprites.tem_pacote_sprites():
            quadros_intro = [
                "01-signal.png", "02-gaze.png", "03-arrival.png",
                "04-landing.png", "05-greeting.png", "06-wink.png", "07-ready.png"
            ]
            if agora - self.ultimo_frame_intro > 0.16:
                self.ultimo_frame_intro = agora
                self.idx_intro += 1
            if self.idx_intro < len(quadros_intro):
                return quadros_intro[self.idx_intro], ""
            self.em_intro = False

        if agora < self.ate_quando_headpat:
            return "capri-headpat.png", "capri-effect-heart.png"

        if agora < self.ate_quando_forcado and self.sprite_forcado:
            return self.sprite_forcado, ""

        if self.pausada:
            pose = self.config.get("pose_padrao", "Padrao")
            if pose == "Sentada no Chao":
                return "capri-sit_floor-sleepy.png", ""
            if pose == "Reclinada":
                return "capri-recline-sleepy.png", ""
            return "capri-idle-sleepy.png", ""

        estado = self.estado_atual.upper()

        if "FALANDO" in estado:
            nv = self.nivel_voz
            if nv < 0.18:
                return "capri-neutral.png", ""
            elif nv < 0.42:
                return "capri-idle-mouth_small.png", ""
            elif nv < 0.68:
                return "capri-idle-mouth_round.png", ""
            else:
                return "capri-idle-mouth_wide.png", ""

        if "SPOTIFY" in estado or "MÚSICA" in estado or agora < self.ate_quando_musica:
            return "capri-music-window.png", ""

        if "OUVINDO" in estado or "COMANDO" in estado or "VOZ DETECTADA" in estado or "NOME DO APP" in estado:
            pose = self.config.get("pose_padrao", "Padrao")
            if pose == "Sentada na Borda":
                return "capri-sit_edge-attentive.png", ""
            if pose == "Agachada":
                return "capri-crouch-attentive.png", ""
            return "capri-lean_in-attentive.png", ""

        if "TRANSCREVENDO" in estado or "PESQUISANDO" in estado or "PROCESSANDO" in estado:
            pose = self.config.get("pose_padrao", "Padrao")
            if pose == "Bracos Cruzados":
                return "capri-arms_crossed-focused.png", ""
            if pose == "Sentada no Chao":
                return "capri-sit_floor-thinking.png", ""
            return "capri-idle-thinking.png", ""

        pose_base = self._obter_sprite_pose_base()
        if pose_base == "capri-neutral.png":
            if self.etapa_piscar == 0 and agora >= self.proximo_piscar:
                self.etapa_piscar = 1
                self.ultimo_tick_piscar = agora
            if self.etapa_piscar == 1:
                if agora - self.ultimo_tick_piscar > 0.06:
                    self.etapa_piscar = 2
                    self.ultimo_tick_piscar = agora
                return "capri-idle-blink_half.png", ""
            elif self.etapa_piscar == 2:
                if agora - self.ultimo_tick_piscar > 0.08:
                    self.etapa_piscar = 3
                    self.ultimo_tick_piscar = agora
                return "capri-idle-blink_closed.png", ""
            elif self.etapa_piscar == 3:
                if agora - self.ultimo_tick_piscar > 0.06:
                    self.etapa_piscar = 0
                    self.proximo_piscar = agora + random.uniform(3.0, 6.2)
                    if random.random() < 0.28:
                        self.expressao_idle_extra = random.choice([
                            "capri-idle-look_left.png",
                            "capri-idle-look_right.png",
                            "capri-idle-smirk.png",
                            "capri-idle-happy.png",
                            "capri-idle-wink_half.png"
                        ])
                        self.fim_expressao_idle = agora + random.uniform(1.4, 2.6)
                return "capri-idle-blink_half.png", ""

            if agora < self.fim_expressao_idle and self.expressao_idle_extra:
                return self.expressao_idle_extra, ""

        return pose_base, ""

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
            self.canvas_sprite.delete("all")
            w = max(440, self.canvas_sprite.winfo_width())
            h = max(240, self.canvas_sprite.winfo_height())

            # 1. Linhas horizontais de monitor CRT (Scanlines)
            if not self.config.get("modo_recorte_transparente", False):
                for y_line in range(18, h - 6, 5):
                    self.canvas_sprite.create_line(6, y_line, w - 6, y_line, fill=self.BG_SCANLINE, width=1)

            # 2. Sprite Central da Capri
            nome_sprite, efeito = self._selecionar_nome_sprite_atual()
            foto_tk = self.sprites.obter_sprite_tk(nome_sprite, sobrepor_efeito=efeito)

            if foto_tk:
                offset_resp = int(math.sin(self.fase_onda * 0.25) * 2) if "FALANDO" not in self.estado_atual else 0
                self.canvas_sprite.create_image(w // 2, (h // 2) + 8 + offset_resp, image=foto_tk)

                if nome_sprite == "capri-music-window.png":
                    notas = self.sprites.obter_notas_musicais_tk()
                    for idx, nota_tk in enumerate(notas):
                        ang = self.fase_onda * 0.35 + idx * 1.6
                        nx = 75 + (idx * 90) + int(math.sin(ang) * 12)
                        ny = 60 + int(math.cos(ang) * 18)
                        self.canvas_sprite.create_image(nx, ny, image=nota_tk)
            else:
                self.canvas_sprite.create_text(
                    w // 2, h // 2, text="[ SPRITES NÃO ENCONTRADOS ]",
                    fill=self.TEXT_PINK, font=("Consolas", 10, "bold")
                )

            # 3. Telemetria discreta nos cantos inferiores do visor CRT
            pose_str = self.config.get("pose_padrao", "PADRAO").upper()
            self.canvas_sprite.create_text(18, h - 10, text=pose_str, fill="#6E5662", font=("Consolas", 7, "bold"), anchor="w")
            pontos_onda = "• " * 11
            self.canvas_sprite.create_text(w - 14, h - 10, text=f"{pontos_onda} v0.1.5", fill="#6E5662", font=("Consolas", 7), anchor="e")

            # 4. Moldura Rosa do Visor + Cantoneiras Violetas
            self.canvas_sprite.create_rectangle(4, 14, w - 4, h - 2, outline=self.BORDER_PINK, width=1.5)

            cor_canto = self.ACCENT_VIOLET
            self.canvas_sprite.create_line(2, 12, 2, 34, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(2, 12, 20, 12, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(w - 2, 12, w - 2, 34, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(w - 20, 12, w - 2, 12, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(2, h - 24, 2, h, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(w - 2, h - 24, w - 2, h, fill=cor_canto, width=3)

            # 5. Badge Sobreposto Superior Esquerdo: [ CAPRI // ESTADO ]
            texto_badge = f"CAPRI // {self.estado_atual}"
            largura_badge = max(135, len(texto_badge) * 8 + 20)
            self.canvas_sprite.create_rectangle(24, 3, 24 + largura_badge, 25, fill="#191024", outline=self.ACCENT_VIOLET, width=2)
            self.canvas_sprite.create_text(
                24 + (largura_badge // 2), 14,
                text=texto_badge, fill="#E2D9F3", font=("Consolas", 8, "bold")
            )

            # 6. Animação da Barra de Progresso / Voz no Card "CAPRI pre-alpha"
            self.fase_onda += 0.25
            if self.painel_status_visivel and self.canvas_progresso.winfo_exists():
                self.canvas_progresso.delete("all")
                wp = max(380, self.canvas_progresso.winfo_width())
                if self.pausada:
                    self.canvas_progresso.create_rectangle(0, 0, 60, 4, fill="#475569", outline="")
                elif self.nivel_voz > 0.05:
                    larg_voz = int(min(1.0, self.nivel_voz * 1.2) * wp)
                    self.canvas_progresso.create_rectangle(0, 0, max(40, larg_voz), 4, fill=self.TEXT_PINK, outline="")
                else:
                    self.pos_barra_progresso = (self.pos_barra_progresso + 6) % (wp + 110)
                    x1 = self.pos_barra_progresso - 110
                    x2 = self.pos_barra_progresso
                    self.canvas_progresso.create_rectangle(max(0, x1), 0, min(wp, x2), 4, fill=self.TEXT_PINK, outline="")
        except Exception:
            pass
        if self.rodando:
            self.root.after(45, self._animar_hud)

    def acionar_sprite_temporario(self, nome_sprite: str, duracao: float = 2.5):
        self.sprite_forcado = nome_sprite
        self.ate_quando_forcado = time.time() + duracao

    def atualizar_estado(self, novo_estado: str, cor: str = "#D45B72", legenda: str = ""):
        self.estado_atual = novo_estado
        self.cor_atual = cor
        if "SPOTIFY" in novo_estado.upper():
            self.ate_quando_musica = time.time() + 5.0

        mapa_subtitulos = {
            "EM ESPERA": "Núcleo local ativo e aguardando...",
            "OUVINDO VOCÊ...": "Captando áudio do microfone...",
            "TRANSCREVENDO...": "Processando voz localmente na RAM...",
            "PESQUISANDO IA...": f"Consultando API ({self.config.get('provedor_ia', 'Gemini')})...",
            "PROCESSANDO...": "Executando instrução...",
            "FALANDO...": "Transmitindo resposta de voz...",
            "MIC SILENCIADO": "Microfone silenciado (Use a barra abaixo)."
        }
        self.subtitulo_card = mapa_subtitulos.get(novo_estado.upper(), f"Status: {novo_estado}")
        if legenda:
            self.legenda_card = legenda

        def _atualizar_ui():
            if hasattr(self, "lbl_subtitulo_card") and self.lbl_subtitulo_card.winfo_exists():
                self.lbl_subtitulo_card.configure(text=self.subtitulo_card)
            if hasattr(self, "lbl_legenda_card") and self.lbl_legenda_card.winfo_exists():
                self.lbl_legenda_card.configure(text=self.legenda_card)
        try:
            self.root.after(0, _atualizar_ui)
        except Exception:
            pass

    def alternar_pausa(self, *args):
        self.pausada = not self.pausada
        if self.pausada:
            if hasattr(self, "btn_pausa"):
                self.btn_pausa.configure(text="MUTADA", bg="#FF0055", fg="#FFFFFF")
            if hasattr(self, "btn_mic_barra"):
                self.btn_mic_barra._cor_borda_atual = "#FF0055"
                self.btn_mic_barra.configure(bg="#FF0055")
                self.btn_mic_barra.lbl.configure(text="🔇", fg="#FF0055")
            self.atualizar_estado("MIC SILENCIADO", "#FF0055", "Microfone mutado. Você ainda pode digitar na barra abaixo.")
        else:
            if hasattr(self, "btn_pausa"):
                self.btn_pausa.configure(text="MIC ON", bg="#00FF66", fg="#090D16")
            if hasattr(self, "btn_mic_barra"):
                self.btn_mic_barra._cor_borda_atual = "#00FF66"
                self.btn_mic_barra.configure(bg="#00FF66")
                self.btn_mic_barra.lbl.configure(text="🎙", fg="#00FF66")
            self.atualizar_estado("EM ESPERA", self.BORDER_PINK, "Escuta ativa. Diga 'Capri' ou digite abaixo.")

    def _obter_pasta_assets(self) -> str:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            pasta_empacotada = os.path.join(sys._MEIPASS, "assets")
            if os.path.exists(pasta_empacotada):
                return pasta_empacotada
        pasta_local = os.path.join(PASTA_PROJETO, "assets")
        os.makedirs(pasta_local, exist_ok=True)
        return pasta_local

    def _obter_caminho_icone(self) -> str:
        pasta_assets = self._obter_pasta_assets()
        if hasattr(self, "sprites"):
            ico_pacote = self.sprites.obter_caminho("app.ico")
            if ico_pacote and os.path.exists(ico_pacote):
                return ico_pacote
        caminho_ico = os.path.join(pasta_assets, "icone.ico")
        caminho_png = os.path.join(pasta_assets, "icone.png")
        if os.path.exists(caminho_png):
            try:
                if not os.path.exists(caminho_ico) or os.path.getmtime(caminho_png) > os.path.getmtime(caminho_ico):
                    img = Image.open(caminho_png).convert("RGBA")
                    img.save(caminho_ico, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
                return caminho_ico
            except Exception:
                return caminho_png
        if os.path.exists(caminho_ico):
            return caminho_ico
        return ""

    def _aplicar_icone_janela(self, janela):
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
            foto = ImageTk.PhotoImage(img_tk)
            janela.iconphoto(True, foto)
            janela._icone_ref = foto
        except Exception:
            pass

    def _criar_imagem_icone(self):
        if hasattr(self, "sprites"):
            for candidato in ("icon-source.png", "avatar.png", "app.ico"):
                cam = self.sprites.obter_caminho(candidato)
                if cam and os.path.exists(cam):
                    try:
                        return Image.open(cam).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
                    except Exception:
                        pass
        pasta_assets = self._obter_pasta_assets()
        for nome_arq in ("icone.png", "icone.ico"):
            caminho = os.path.join(pasta_assets, nome_arq)
            if os.path.exists(caminho):
                try:
                    return Image.open(caminho).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
                except Exception:
                    pass
        img = Image.new("RGBA", (64, 64), (17, 9, 14, 255))
        d = ImageDraw.Draw(img)
        d.polygon([(32, 6), (58, 32), (32, 58), (6, 32)], outline=(212, 91, 114, 255), width=4)
        d.ellipse((22, 22, 42, 42), fill=(155, 114, 255, 255))
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

    def salvar_executavel_personalizado(self, caminho_arquivo: str, nome_chamada: str) -> bool:
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
        janela_pai = getattr(self, "janela_config", None)
        if not (janela_pai and janela_pai.winfo_exists()):
            janela_pai = self.root
        caminho = filedialog.askopenfilename(
            parent=janela_pai,
            title="Selecione o Executável ou Atalho do Programa",
            filetypes=[("Executáveis e Atalhos", "*.exe *.lnk *.url *.bat *.cmd"), ("Todos os arquivos", "*.*")]
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
        tk.Label(dialogo, text="EXECUTÁVEL DETECTADO", fg=CYAN, bg=BG_DARK, font=("Consolas", 11, "bold")).pack(pady=(16, 2))
        tk.Frame(dialogo, bg=CYAN, height=1).pack(fill="x", padx=30, pady=(0, 8))
        tk.Label(dialogo, text=os.path.basename(caminho), fg=CORAL, bg=BG_DARK, font=("Consolas", 9, "bold")).pack(pady=(0, 10))
        tk.Label(dialogo, text="Como você quer chamar este executável por voz? (Ex: CS2)", fg="#E2E8F0", bg=BG_DARK, font=("Consolas", 9)).pack(pady=2)
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

    # =====================================================================
    # 5. CENTRAL DE CONFIGURAÇÃO COMPLETA (ESTILO CYBERPUNK 2077)
    # =====================================================================
    def abrir_configuracoes(self, *args):
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
            lbl_t = tk.Label(f_aba, text=nome_aba, fg=CORAL, bg=BG_MAIN, font=("Consolas", 11, "bold"), cursor="hand2")
            lbl_t.pack()
            barra_sub = tk.Frame(f_aba, bg=BG_MAIN, height=2)
            barra_sub.pack(fill="x", pady=(3, 0))
            lbl_t.bind("<Button-1>", lambda e, n=nome_aba: selecionar_aba(n))
            widgets_abas[nome_aba] = (lbl_t, barra_sub)

        corpo = tk.Frame(win, bg=BG_MAIN)
        corpo.pack(fill="both", expand=True, padx=28, pady=(4, 6))
        col_esquerda = tk.Frame(corpo, bg=BG_MAIN, width=210)
        col_esquerda.pack(side="left", fill="y", padx=(0, 24))
        col_esquerda.pack_propagate(False)

        btn_bench = tk.Canvas(col_esquerda, width=195, height=38, bg=BG_MAIN, highlightthickness=0, cursor="hand2")
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

        col_direita = tk.Frame(corpo, bg=BG_MAIN)
        col_direita.pack(side="left", fill="both", expand=True)

        def criar_switch_cyberpunk(parent, estado_inicial: bool, ao_alternar):
            cv = tk.Canvas(parent, width=118, height=26, bg=parent["bg"], highlightthickness=0, cursor="hand2")
            estado = [estado_inicial]

            def _desenhar():
                cv.delete("all")
                cv.configure(bg=parent["bg"])
                ativo = estado[0]
                cv.create_text(32, 13, text="ON" if ativo else "OFF", fill=CYAN if ativo else CORAL, font=("Consolas", 9, "bold"), anchor="e")
                x1, y1, x2, y2 = 42, 3, 114, 23
                cv.create_polygon([x1, y1, x2, y1, x2, y2 - 5, x2 - 5, y2, x1, y2], fill="#160A16", outline=CYAN if ativo else CORAL_DIM, width=1.2)
                if ativo:
                    cv.create_polygon([79, 5, 112, 5, 112, 17, 108, 21, 79, 21], fill=CYAN, outline="")
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
            f_sec.pack(fill="x", pady=(10, 4))
            tk.Frame(f_sec, bg=CYAN, height=1).pack(fill="x")
            tk.Label(f_sec, text=titulo_secao, fg="#E2E8F0", bg=BG_MAIN, font=("Consolas", 10, "bold"), anchor="w").pack(fill="x", pady=(4, 0))

        vars_chaves = {
            "provedor_ia": tk.StringVar(value=self.config.get("provedor_ia", "Gemini")),
            "gemini_api_key": tk.StringVar(value=self.config.get("gemini_api_key", "")),
            "claude_api_key": tk.StringVar(value=self.config.get("claude_api_key", "")),
            "deepseek_api_key": tk.StringVar(value=self.config.get("deepseek_api_key", "")),
            "fish_api_key": tk.StringVar(value=self.config.get("fish_api_key", "")),
            "fish_voice_id": tk.StringVar(value=self.config.get("fish_voice_id", "")),
            "pose_padrao": tk.StringVar(value=self.config.get("pose_padrao", "Padrao")),
        }

        def salvar_chaves_em_memoria(*_):
            for k, v_tk in vars_chaves.items():
                self.config[k] = v_tk.get().strip()
            salvar_configuracoes(self.config)

        for var in vars_chaves.values():
            var.trace_add("write", salvar_chaves_em_memoria)

        def renderizar_conteudo_aba():
            for w in col_direita.winfo_children():
                w.destroy()
            aba = aba_atual.get()
            if aba == "APLICATIVOS":
                canvas_lista = tk.Canvas(col_direita, bg=BG_MAIN, highlightthickness=0)
                scroll_bar = tk.Scrollbar(col_direita, orient="vertical", command=canvas_lista.yview, bg=BG_MAIN, troughcolor=BG_MAIN, activebackground=CORAL)
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
                    lbl = tk.Label(linha, text=dados_app.get("nome", chave_app), fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold"), anchor="w")
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
                    linha = tk.Frame(col_direita, bg=BG_MAIN, pady=5)
                    linha.pack(fill="x")
                    tk.Label(linha, text=rotulo, fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
                    moldura = tk.Frame(linha, bg=CORAL_DIM, padx=1, pady=1)
                    moldura.pack(side="right")
                    tk.Entry(moldura, textvariable=var_tk, bg=BG_INPUT, fg=CYAN, insertbackground=CYAN, font=("Consolas", 10, "bold"), relief="flat", width=34, justify="center", show="*" if ocultar else "").pack(ipady=3, ipadx=6)

                _criar_linha_input("Gemini API Key", vars_chaves["gemini_api_key"], ocultar=True)
                _criar_linha_input("Claude API Key", vars_chaves["claude_api_key"], ocultar=True)
                _criar_linha_input("DeepSeek API Key", vars_chaves["deepseek_api_key"], ocultar=True)
                _criar_linha_input("Fish Audio API Key", vars_chaves["fish_api_key"], ocultar=True)
                _criar_linha_input("Fish Audio Voice ID", vars_chaves["fish_voice_id"], ocultar=False)

                criar_divisor_secao(col_direita, "Configuração de Módulos (Clique para alternar IA)")
                opcoes_ia = ["Gemini", "Claude", "DeepSeek"]

                f_sel = tk.Frame(col_direita, bg=BG_MAIN, pady=5)
                f_sel.pack(fill="x")
                tk.Label(f_sel, text="Provedor de Pesquisa IA", fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")).pack(side="left")
                box_ia = tk.Frame(f_sel, bg=CORAL_DIM, padx=1, pady=1)
                box_ia.pack(side="right")
                inner_ia = tk.Frame(box_ia, bg=BG_INPUT, width=260, height=26, cursor="hand2")
                inner_ia.pack_propagate(False)
                inner_ia.pack()

                def _mudar_ia(delta: int):
                    atual = vars_chaves["provedor_ia"].get()
                    idx = opcoes_ia.index(atual) if atual in opcoes_ia else 0
                    novo = opcoes_ia[(idx + delta) % len(opcoes_ia)]
                    vars_chaves["provedor_ia"].set(novo)

                btn_esq = tk.Label(inner_ia, text="<", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2")
                btn_esq.pack(side="left", padx=10)
                lbl_val = tk.Label(inner_ia, textvariable=vars_chaves["provedor_ia"], fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2")
                lbl_val.pack(expand=True)
                btn_dir = tk.Label(inner_ia, text=">", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2")
                btn_dir.pack(side="right", padx=10)

                btn_esq.bind("<Button-1>", lambda e: _mudar_ia(-1))
                lbl_val.bind("<Button-1>", lambda e: _mudar_ia(1))
                btn_dir.bind("<Button-1>", lambda e: _mudar_ia(1))

            elif aba == "SISTEMA":
                criar_divisor_secao(col_direita, "Preferências de Operação & Sprites")
                linha_mute = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_mute.pack(fill="x")
                tk.Label(linha_mute, text="Escuta de Microfone Ativa", fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")).pack(side="left")
                criar_switch_cyberpunk(linha_mute, not getattr(self, "pausada", False), lambda ativo: self.alternar_pausa() if (ativo == getattr(self, "pausada", False)) else None).pack(side="right")

                linha_startup = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_startup.pack(fill="x")
                tk.Label(linha_startup, text="Iniciar junto com o Windows", fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")).pack(side="left")

                def _alternar_startup(ativo):
                    self.config["iniciar_com_windows"] = ativo
                    salvar_configuracoes(self.config)
                    configurar_inicializacao_windows(ativo)

                criar_switch_cyberpunk(linha_startup, self.config.get("iniciar_com_windows", True), _alternar_startup).pack(side="right")

                linha_recorte = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_recorte.pack(fill="x")
                tk.Label(linha_recorte, text="Modo Mascote (Recorte 100% Transparente)", fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")).pack(side="left")

                def _alternar_recorte(ativo):
                    self.config["modo_recorte_transparente"] = ativo
                    salvar_configuracoes(self.config)
                    self._aplicar_modo_transparencia()

                criar_switch_cyberpunk(linha_recorte, self.config.get("modo_recorte_transparente", False), _alternar_recorte).pack(side="right")

                poses_disponiveis = [
                    "Padrao", "Bracos Cruzados", "Mao na Cintura",
                    "Mao no Queixo", "Sentada na Borda", "Sentada no Chao",
                    "Agachada", "Reclinada"
                ]
                f_pose = tk.Frame(col_direita, bg=BG_MAIN, pady=8)
                f_pose.pack(fill="x")
                tk.Label(f_pose, text="Pose Padrão da Capri", fg=CORAL, bg=BG_MAIN, font=("Consolas", 10, "bold")).pack(side="left")
                box_p = tk.Frame(f_pose, bg=CORAL_DIM, padx=1, pady=1)
                box_p.pack(side="right")
                inner_p = tk.Frame(box_p, bg=BG_INPUT, width=240, height=26, cursor="hand2")
                inner_p.pack_propagate(False)
                inner_p.pack()

                def _mudar_pose(delta: int):
                    atual = vars_chaves["pose_padrao"].get()
                    idx = poses_disponiveis.index(atual) if atual in poses_disponiveis else 0
                    novo = poses_disponiveis[(idx + delta) % len(poses_disponiveis)]
                    vars_chaves["pose_padrao"].set(novo)

                b_pe = tk.Label(inner_p, text="<", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2")
                b_pe.pack(side="left", padx=10)
                l_pv = tk.Label(inner_p, textvariable=vars_chaves["pose_padrao"], fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2")
                l_pv.pack(expand=True)
                b_pd = tk.Label(inner_p, text=">", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2")
                b_pd.pack(side="right", padx=10)

                b_pe.bind("<Button-1>", lambda e: _mudar_pose(-1))
                l_pv.bind("<Button-1>", lambda e: _mudar_pose(1))
                b_pd.bind("<Button-1>", lambda e: _mudar_pose(1))

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
        tk.Button(borda_central, text="SALVAR E APLICAR", bg=BG_MAIN, fg=CYAN, activebackground=BG_ROW_HOVER, activeforeground=CYAN, font=("Consolas", 10, "bold"), relief="flat", cursor="hand2", padx=26, pady=5, command=fechar_e_aplicar).pack()

        selecionar_aba("APLICATIVOS")

    def iniciar(self):
        self.root.mainloop()