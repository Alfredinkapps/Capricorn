import os
import re
import sys
import math
import time
import queue
import random
import zipfile
import ctypes
import threading
from collections.abc import Callable
from typing import Any, TYPE_CHECKING
import tkinter as tk
from tkinter import filedialog
import pygame
import pystray
from PIL import Image, ImageDraw, ImageTk, ImageOps

from core.config import (
    PASTA_PROJETO,
    configurar_inicializacao_windows,
    carregar_configuracoes,
    salvar_configuracoes,
)
from core.logger import obter_logger
from system.apps import escanear_e_atualizar_apps

if TYPE_CHECKING:
    from ui.modo_livre import CapriModoLivre

log = obter_logger("hud")

try:
    pygame.mixer.init()
except Exception as e:
    log.warning("Aviso Mixer Pygame: %s", e)


# =====================================================================
# 1. COMPONENTES VISUAIS TIPADOS (SEM MONKEY-PATCH EM FRAME / CANVAS)
# =====================================================================
class BotaoQuadrado(tk.Frame):
    """Botão quadrado estilizado com moldura neon e label interno tipado."""

    def __init__(
        self,
        parent: tk.Misc,
        texto: str,
        comando: Callable[[], Any],
        bg_bar: str,
        cor_hover_borda: str,
        cor_borda: str,
        cor_texto: str,
        largura: int = 28,
        altura: int = 26,
    ):
        super().__init__(parent, bg=cor_borda, padx=1, pady=1)
        self._bg_bar = bg_bar
        self._cor_hover_borda = cor_hover_borda
        self._cor_borda_atual = cor_borda

        inner = tk.Frame(self, bg=bg_bar, width=largura, height=altura)
        inner.pack_propagate(False)
        inner.pack()

        self.lbl = tk.Label(
            inner,
            text=texto,
            fg=cor_texto,
            bg=bg_bar,
            font=("Consolas", 9, "bold"),
            cursor="hand2",
        )
        self.lbl.pack(expand=True, fill="both")

        self.lbl.bind("<Enter>", self._on_enter)
        self.lbl.bind("<Leave>", self._on_leave)
        self.lbl.bind("<Button-1>", lambda _e: comando())

    def _on_enter(self, _event: Any = None) -> None:
        self.configure(bg=self._cor_hover_borda)
        self.lbl.configure(bg="#26111B")

    def _on_leave(self, _event: Any = None) -> None:
        self.configure(bg=self._cor_borda_atual)
        self.lbl.configure(bg=self._bg_bar)

    def definir_estilo(self, cor_borda: str, cor_texto: str, texto: str | None = None) -> None:
        self._cor_borda_atual = cor_borda
        self.configure(bg=cor_borda)
        if texto is not None:
            self.lbl.configure(text=texto, fg=cor_texto)
        else:
            self.lbl.configure(fg=cor_texto)


class SwitchCyberpunk(tk.Canvas):
    """Switch ON/OFF com estética Cyberpunk."""

    def __init__(
        self,
        parent: tk.Widget,
        estado_inicial: bool,
        ao_alternar: Callable[[bool], Any],
        cor_cyan: str = "#54F2F2",
        cor_coral: str = "#E8504B",
        cor_coral_dim: str = "#7A282A",
        cor_coral_off: str = "#D6453D",
    ):
        bg_pai = str(parent.cget("bg"))
        super().__init__(parent, width=118, height=26, bg=bg_pai, highlightthickness=0, cursor="hand2")
        self._parent_widget = parent
        self._ativo = estado_inicial
        self._ao_alternar = ao_alternar
        self._cyan = cor_cyan
        self._coral = cor_coral
        self._coral_dim = cor_coral_dim
        self._coral_off = cor_coral_off

        self.bind("<Button-1>", self._clicar)
        self.redesenhar_fundo()

    def redesenhar_fundo(self) -> None:
        self.delete("all")
        self.configure(bg=str(self._parent_widget.cget("bg")))
        ativo = self._ativo
        self.create_text(
            32, 13,
            text="ON" if ativo else "OFF",
            fill=self._cyan if ativo else self._coral,
            font=("Consolas", 9, "bold"),
            anchor="e",
        )
        x1, y1, x2, y2 = 42, 3, 114, 23
        self.create_polygon(
            [x1, y1, x2, y1, x2, y2 - 5, x2 - 5, y2, x1, y2],
            fill="#160A16",
            outline=self._cyan if ativo else self._coral_dim,
            width=1.2,
        )
        if ativo:
            self.create_polygon(
                [79, 5, 112, 5, 112, 17, 108, 21, 79, 21],
                fill=self._cyan,
                outline="",
            )
        else:
            self.create_rectangle(44, 5, 77, 21, fill=self._coral_off, outline="")

    def _clicar(self, _event: Any = None) -> None:
        self._ativo = not self._ativo
        self.redesenhar_fundo()
        self._ao_alternar(self._ativo)


# =====================================================================
# 2. MOTOR DE SPRITES DINÂMICOS DA CAPRI (CACHE EM RAM + ANIMAÇÕES)
# =====================================================================
class GerenciadorSpritesCapri:
    """Indexa, extrai automaticamente (se estiver em .zip dentro de assets/) e gerencia sprites na RAM."""

    def __init__(self, pasta_assets: str, tamanho_alvo: tuple[int, int] = (250, 200)):
        self.pasta_assets = pasta_assets
        self.tamanho_alvo = tamanho_alvo
        self.mapa_arquivos: dict[str, str] = {}
        self.cache_tk: dict[str, ImageTk.PhotoImage] = {}
        self.cache_notas_tk: list[ImageTk.PhotoImage] = []

        self._extrair_zip_se_necessario()
        self._indexar_sprites()

    def _extrair_zip_se_necessario(self) -> None:
        pasta_v1 = os.path.join(self.pasta_assets, "capri", "sprites", "v1")
        if os.path.exists(pasta_v1) or not os.path.exists(self.pasta_assets):
            return

        # Busca apenas dentro de assets/ para nunca extrair pacotes de Release da raiz
        for arq in os.listdir(self.pasta_assets):
            if arq.lower().endswith(".zip"):
                caminho_zip = os.path.join(self.pasta_assets, arq)
                try:
                    with zipfile.ZipFile(caminho_zip, "r") as zf:
                        nomes = zf.namelist()
                        if any("capri/sprites/" in n or "capri-neutral.png" in n for n in nomes):
                            log.info("Extraindo pacote de sprites '%s' para assets/...", arq)
                            zf.extractall(self.pasta_assets)
                            log.info("Sprites extraídos com sucesso.")
                            return
                except Exception as e:
                    log.warning("Aviso Extração ZIP de sprites: %s", e)

    def _indexar_sprites(self) -> None:
        self.mapa_arquivos.clear()
        for base_dir in (
            self.pasta_assets,
            os.path.join(PASTA_PROJETO, "capri"),
            os.path.join(PASTA_PROJETO, "default"),
        ):
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

    def obter_sprite_tk(
        self, nome_arquivo: str, sobrepor_efeito: str = ""
    ) -> ImageTk.PhotoImage | None:
        chave_cache = f"{nome_arquivo.lower()}__{sobrepor_efeito.lower()}__{self.tamanho_alvo}"
        if chave_cache in self.cache_tk:
            return self.cache_tk[chave_cache]

        caminho = self.obter_caminho(nome_arquivo)
        if not caminho:
            caminho = (
                self.obter_caminho("capri-neutral.png")
                or self.obter_caminho("avatar.png")
                or self.obter_caminho("icone.png")
            )
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
                    ef = ImageOps.contain(
                        ef,
                        (int(img.width * 0.42), int(img.height * 0.42)),
                        Image.Resampling.LANCZOS,
                    )
                    pos_x = max(0, img.width - ef.width - 10)
                    img.alpha_composite(ef, (pos_x, 10))

            img = ImageOps.contain(img, self.tamanho_alvo, Image.Resampling.LANCZOS)
            foto_tk = ImageTk.PhotoImage(img)
            self.cache_tk[chave_cache] = foto_tk
            return foto_tk
        except Exception as e:
            log.warning("Aviso Sprite %s: %s", nome_arquivo, e)
            return None

    def obter_notas_musicais_tk(self) -> list[ImageTk.PhotoImage]:
        if self.cache_notas_tk:
            return self.cache_notas_tk
        nomes_notas = [
            "01-eighth-cyan.png",
            "02-beamed-lime.png",
            "03-quarter-pink.png",
            "04-sixteenth-violet.png",
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
# 3. INTERFACE GRÁFICA PRINCIPAL + BALÃO DE FALA CYBERPUNK
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
    VERSAO_HUD = "v0.2.0"

    def __init__(self):
        self.config: dict[str, Any] = escanear_e_atualizar_apps(carregar_configuracoes())
        self.rodando = True
        self.pausada = False
        self.reiniciar_ia = False
        self.limpar_contexto = False
        self.forcar_escuta_voz = False
        self.voz_mutada = not self.config.get("voz_ativa", True)
        self.painel_status_visivel = True
        self.anexar_tela = False
        self.modo_livre: "CapriModoLivre | None" = None
        self.ao_encerrar: Callable[[], None] | None = None

        # Controle do Balão de Fala lateral (atributos declarados para segurança de tipos)
        self.balao_fala: tk.Toplevel | None = None
        self.btn_copiar_tudo: tk.Button | None = None
        self.btn_copiar_codigo: tk.Button | None = None
        self.txt_balao: tk.Text | None = None
        self.balao_aberto = False
        self.ultima_fala_capri = ""
        self.ultimo_codigo_extraido = ""

        self.fila_comandos_texto: queue.Queue[str] = queue.Queue()

        self.nivel_voz = 0.0
        self.fase_onda = 0.0
        self.pos_barra_progresso = 0.0
        self.estado_atual = "A LIGAR"
        self.subtitulo_card = "Iniciando núcleo local..."
        self.legenda_card = "Diga 'Capri' ou digite abaixo..."
        self.cor_atual = self.BORDER_PINK
        self.janela_config: tk.Toplevel | None = None
        self.icone_bandeja: Any = None
        self._icones_ref: list[ImageTk.PhotoImage] = []

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

        self.root.geometry("465x475+40+40")
        self.root.configure(bg=self.BG_OUTER)
        self.root.overrideredirect(True)

        self._offset_x = 0
        self._offset_y = 0

        self.main_frame = tk.Frame(self.root, bg=self.BG_OUTER, padx=10, pady=8)
        self.main_frame.pack(fill="both", expand=True)

        # IMPORTANTE: Barra de pesquisa é empacotada PRIMEIRO com side="bottom"
        # para NUNCA sumir independentemente do conteúdo do card central
        self._construir_barra_pesquisa()
        self._construir_visor_central()

        self._aplicar_modo_transparencia()
        self._iniciar_bandeja_sistema()
        self._animar_hud()

        tem_alguma_chave = any(
            str(self.config.get(k, "")).strip()
            for k in ("gemini_api_key", "claude_api_key", "deepseek_api_key")
        )
        if not tem_alguma_chave:
            self.root.after(600, self.abrir_configuracoes)

    def _criar_botao_quadrado(
        self,
        parent: tk.Misc,
        texto: str,
        comando: Callable[[], Any],
        cor_borda: str | None = None,
        cor_texto: str | None = None,
        largura: int = 28,
        altura: int = 26,
    ) -> BotaoQuadrado:
        return BotaoQuadrado(
            parent=parent,
            texto=texto,
            comando=comando,
            bg_bar=self.BG_BAR,
            cor_hover_borda=self.ACCENT_CYAN,
            cor_borda=cor_borda or self.BORDER_DIM,
            cor_texto=cor_texto or self.TEXT_PINK,
            largura=largura,
            altura=altura,
        )

    def _construir_visor_central(self) -> None:
        self.container_central = tk.Frame(self.main_frame, bg=self.BG_OUTER)
        self.container_central.pack(side="top", fill="both", expand=True, pady=(0, 8))

        # Visor CRT dos Sprites
        self.canvas_sprite = tk.Canvas(
            self.container_central,
            width=445,
            height=245,
            bg=self.BG_SCREEN,
            highlightthickness=0,
            cursor="hand2",
        )
        self.canvas_sprite.pack(fill="both", expand=True)
        self.canvas_sprite.bind("<Button-1>", self._ao_clicar_sprite)
        self.canvas_sprite.bind("<B1-Motion>", self._arrastar_janela)

        # Card Central compacto ("CAPRI pre-alpha" + Botões)
        self.borda_card_status = tk.Frame(self.container_central, bg=self.BORDER_PINK, padx=1, pady=1)
        self.borda_card_status.pack(fill="x", side="bottom")

        self.card_status = tk.Frame(self.borda_card_status, bg=self.BG_CARD, padx=14, pady=10)
        self.card_status.pack(fill="x")
        self.card_status.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.card_status.bind("<B1-Motion>", self._arrastar_janela)

        f_titulo_card = tk.Frame(self.card_status, bg=self.BG_CARD)
        f_titulo_card.pack(fill="x", pady=(0, 6))
        f_titulo_card.bind("<ButtonPress-1>", self._iniciar_arraste)
        f_titulo_card.bind("<B1-Motion>", self._arrastar_janela)

        lbl_capri = tk.Label(
            f_titulo_card,
            text="CAPRI ",
            fg=self.TEXT_WHITE,
            bg=self.BG_CARD,
            font=("Consolas", 11, "bold"),
        )
        lbl_capri.pack(side="left")
        lbl_capri.bind("<ButtonPress-1>", self._iniciar_arraste)
        lbl_capri.bind("<B1-Motion>", self._arrastar_janela)

        lbl_ver = tk.Label(
            f_titulo_card,
            text="pre-alpha",
            fg=self.TEXT_GRAY,
            bg=self.BG_CARD,
            font=("Consolas", 10, "bold"),
        )
        lbl_ver.pack(side="left")
        lbl_ver.bind("<ButtonPress-1>", self._iniciar_arraste)
        lbl_ver.bind("<B1-Motion>", self._arrastar_janela)

        f_controles_card = tk.Frame(f_titulo_card, bg=self.BG_CARD)
        f_controles_card.pack(side="right")

        self.btn_fechar = tk.Button(
            f_controles_card,
            text="—",
            fg=self.TEXT_GRAY,
            bg="#28131E",
            activebackground="#FF0055",
            activeforeground="#FFFFFF",
            font=("Consolas", 9, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.ocultar_para_bandeja,
            padx=7,
            pady=1,
        )
        self.btn_fechar.pack(side="right", padx=(4, 0))

        self.btn_balao_toggle = tk.Button(
            f_controles_card,
            text="💬",
            fg=self.ACCENT_VIOLET,
            bg="#28131E",
            activebackground="#381A2A",
            activeforeground="#FFFFFF",
            font=("Consolas", 9, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.alternar_balao_fala,
            padx=6,
            pady=1,
        )
        self.btn_balao_toggle.pack(side="right", padx=3)

        self.btn_modo_livre = tk.Button(
            f_controles_card,
            text="🐾",
            fg=self.ACCENT_LIME,
            bg="#28131E",
            activebackground="#381A2A",
            activeforeground="#FFFFFF",
            font=("Consolas", 9, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.ativar_modo_livre,
            padx=6,
            pady=1,
        )
        self.btn_modo_livre.pack(side="right", padx=3)

        self.btn_config = tk.Button(
            f_controles_card,
            text="⚙ CONFIG",
            fg=self.ACCENT_CYAN,
            bg="#28131E",
            activebackground="#381A2A",
            activeforeground="#FFFFFF",
            font=("Consolas", 8, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.abrir_configuracoes,
            padx=8,
            pady=2,
        )
        self.btn_config.pack(side="right", padx=3)

        self.btn_pausa = tk.Button(
            f_controles_card,
            text="MIC ON",
            fg="#090D16",
            bg="#00FF66",
            activebackground="#00CC52",
            activeforeground="#090D16",
            font=("Consolas", 8, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.alternar_pausa,
            padx=8,
            pady=2,
        )
        self.btn_pausa.pack(side="right", padx=3)

        self.lbl_subtitulo_card = tk.Label(
            self.card_status,
            text=self.subtitulo_card,
            fg=self.TEXT_WHITE,
            bg=self.BG_CARD,
            font=("Consolas", 10),
            anchor="w",
        )
        self.lbl_subtitulo_card.pack(fill="x", pady=(0, 6))

        self.canvas_progresso = tk.Canvas(
            self.card_status, height=4, bg="#38242E", highlightthickness=0
        )
        self.canvas_progresso.pack(fill="x", pady=(0, 8))

        # Legenda sempre de 1 linha curta (respostas completas vão para o Balão de Fala)
        self.lbl_legenda_card = tk.Label(
            self.card_status,
            text=self.legenda_card,
            fg=self.TEXT_GRAY,
            bg=self.BG_CARD,
            font=("Consolas", 9),
            anchor="w",
            justify="left",
            cursor="hand2",
        )
        self.lbl_legenda_card.pack(fill="x")
        self.lbl_legenda_card.bind("<Button-1>", lambda _e: self.alternar_balao_fala())

    def _construir_barra_pesquisa(self) -> None:
        """Barra inferior 'Conversar com Capri...' travada na base da janela."""
        self.borda_pesquisa = tk.Frame(self.main_frame, bg=self.BORDER_PINK, padx=1, pady=1)
        self.borda_pesquisa.pack(fill="x", side="bottom", pady=(2, 0))

        self.barra_pesquisa_inner = tk.Frame(self.borda_pesquisa, bg=self.BG_BAR, padx=8, pady=7)
        self.barra_pesquisa_inner.pack(fill="x")

        tk.Frame(self.barra_pesquisa_inner, bg=self.ACCENT_VIOLET, width=3, height=22).pack(
            side="left", padx=(2, 6)
        )
        tk.Label(
            self.barra_pesquisa_inner,
            text="〰",
            fg=self.ACCENT_VIOLET,
            bg=self.BG_BAR,
            font=("Consolas", 10, "bold"),
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
            bd=0,
        )
        self.entry_pesquisa.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)

        self.entry_pesquisa.bind("<Button-1>", self._focar_entrada_pesquisa)
        self.entry_pesquisa.bind("<FocusIn>", self._ao_ganhar_foco_pesquisa)
        self.entry_pesquisa.bind("<FocusOut>", self._ao_perder_foco_pesquisa)
        self.entry_pesquisa.bind("<Return>", self._submeter_pesquisa_interface)
        self.entry_pesquisa.bind("<KP_Enter>", self._submeter_pesquisa_interface)

        # Botões acessíveis na barra inferior: [👁 Tela] [🎙 Mutar] [⚙ Config] [↗ Enviar]
        f_acoes_barra = tk.Frame(self.barra_pesquisa_inner, bg=self.BG_BAR)
        f_acoes_barra.pack(side="right")

        self.btn_visao_barra = self._criar_botao_quadrado(
            f_acoes_barra,
            "👁",
            self._alternar_anexar_tela,
            cor_borda=self.BORDER_DIM,
            cor_texto=self.TEXT_GRAY,
            largura=28,
            altura=25,
        )
        self.btn_visao_barra.pack(side="left", padx=2)

        self.btn_mic_barra = self._criar_botao_quadrado(
            f_acoes_barra,
            "🎙",
            self.alternar_pausa,
            cor_borda="#00FF66",
            cor_texto="#00FF66",
            largura=28,
            altura=25,
        )
        self.btn_mic_barra.pack(side="left", padx=2)

        self.btn_cfg_barra = self._criar_botao_quadrado(
            f_acoes_barra,
            "⚙",
            self.abrir_configuracoes,
            cor_borda=self.ACCENT_CYAN,
            cor_texto=self.ACCENT_CYAN,
            largura=28,
            altura=25,
        )
        self.btn_cfg_barra.pack(side="left", padx=2)

        self._criar_botao_quadrado(
            f_acoes_barra,
            "↗",
            self._submeter_pesquisa_interface,
            cor_borda=self.BORDER_PINK,
            cor_texto=self.TEXT_PINK,
            largura=28,
            altura=25,
        ).pack(side="left", padx=(2, 0))

    # =====================================================================
    # BALÃO DE FALA CYBERPUNK LATERAL (TEXTO LONGO & CÓDIGO COPIÁVEL)
    # =====================================================================
    def _extrair_blocos_codigo(self, texto: str) -> str:
        """Extrai o conteúdo de blocos ```codigo``` se existirem na resposta."""
        blocos = re.findall(r"```(?:[a-zA-Z0-9_+-]*)\n?(.*?)```", texto, flags=re.DOTALL)
        if blocos:
            return "\n\n".join(b.strip() for b in blocos if b.strip())
        return ""

    def _reposicionar_balao(self) -> None:
        """Mantém o balão ancorado ao lado do HUD ou da Capri solta no Modo Livre."""
        try:
            if not (self.balao_fala is not None and self.balao_fala.winfo_exists() and self.balao_aberto):
                return

            tela_w = self.root.winfo_screenwidth()
            tela_h = self.root.winfo_screenheight()

            if (
                self.modo_livre is not None
                and self.modo_livre.ativo
                and self.modo_livre.win is not None
                and self.modo_livre.win.winfo_exists()
            ):
                ref_x = int(self.modo_livre.x)
                ref_y = int(self.modo_livre.y)
                ref_w = self.modo_livre.largura
                ref_h = self.modo_livre.altura
            else:
                self.root.update_idletasks()
                ref_x = self.root.winfo_x()
                ref_y = self.root.winfo_y()
                ref_w = self.root.winfo_width()
                ref_h = self.root.winfo_height()

            balao_w = 430
            balao_h = self.balao_fala.winfo_height()
            if balao_h < 100:
                balao_h = 260

            if ref_x + ref_w + 12 + balao_w <= tela_w:
                bx = ref_x + ref_w + 12
            else:
                bx = max(10, ref_x - balao_w - 12)

            by = ref_y + 12
            if by + balao_h > tela_h - 56:
                by = max(10, (ref_y + ref_h) - balao_h)

            self.balao_fala.geometry(f"{balao_w}x{balao_h}+{bx}+{by}")
        except Exception:
            pass

    def mostrar_balao_fala(self, texto: str) -> None:
        """Abre ou atualiza o Balão de Fala Cyberpunk com o texto completo (thread-safe)."""
        conteudo = (texto or "").strip()
        if not conteudo:
            return

        self.ultima_fala_capri = conteudo
        self.ultimo_codigo_extraido = self._extrair_blocos_codigo(conteudo)

        def _renderizar_balao() -> None:
            try:
                if not (self.balao_fala is not None and self.balao_fala.winfo_exists()):
                    win = tk.Toplevel(self.root)
                    win.overrideredirect(True)
                    win.attributes("-topmost", True)
                    win.configure(bg=self.BORDER_PINK)
                    win.attributes("-alpha", 0.96)
                    self.balao_fala = win

                    inner = tk.Frame(win, bg=self.BG_CARD, padx=10, pady=8)
                    inner.pack(fill="both", expand=True, padx=1, pady=1)

                    topo = tk.Frame(inner, bg=self.BG_CARD)
                    topo.pack(fill="x", pady=(0, 6))

                    tk.Frame(topo, bg=self.ACCENT_VIOLET, width=3, height=16).pack(
                        side="left", padx=(0, 6)
                    )
                    tk.Label(
                        topo,
                        text="CAPRI // FALA",
                        fg=self.ACCENT_VIOLET,
                        bg=self.BG_CARD,
                        font=("Consolas", 9, "bold"),
                    ).pack(side="left")

                    tk.Button(
                        topo,
                        text="✕",
                        fg=self.TEXT_GRAY,
                        bg="#28131E",
                        activebackground="#FF0055",
                        activeforeground="#FFFFFF",
                        font=("Consolas", 8, "bold"),
                        relief="flat",
                        bd=0,
                        cursor="hand2",
                        command=self.fechar_balao_fala,
                        padx=6,
                        pady=1,
                    ).pack(side="right", padx=(4, 0))

                    btn_tudo = tk.Button(
                        topo,
                        text="COPIAR",
                        fg=self.ACCENT_CYAN,
                        bg="#28131E",
                        activebackground="#381A2A",
                        activeforeground="#FFFFFF",
                        font=("Consolas", 8, "bold"),
                        relief="flat",
                        bd=0,
                        cursor="hand2",
                        command=self._copiar_texto_balao,
                        padx=7,
                        pady=1,
                    )
                    btn_tudo.pack(side="right", padx=3)
                    self.btn_copiar_tudo = btn_tudo

                    self.btn_copiar_codigo = tk.Button(
                        topo,
                        text="COPIAR CÓDIGO",
                        fg="#090D16",
                        bg=self.ACCENT_LIME,
                        activebackground="#84CC16",
                        activeforeground="#090D16",
                        font=("Consolas", 8, "bold"),
                        relief="flat",
                        bd=0,
                        cursor="hand2",
                        command=self._copiar_codigo_balao,
                        padx=7,
                        pady=1,
                    )

                    tk.Frame(inner, bg=self.BORDER_DIM, height=1).pack(fill="x", pady=(0, 6))

                    corpo = tk.Frame(inner, bg=self.BG_BAR)
                    corpo.pack(fill="both", expand=True)

                    scroll = tk.Scrollbar(
                        corpo,
                        orient="vertical",
                        bg=self.BG_CARD,
                        troughcolor=self.BG_BAR,
                        activebackground=self.BORDER_PINK,
                    )
                    scroll.pack(side="right", fill="y")

                    txt = tk.Text(
                        corpo,
                        bg=self.BG_BAR,
                        fg=self.TEXT_WHITE,
                        insertbackground=self.ACCENT_CYAN,
                        selectbackground=self.ACCENT_VIOLET,
                        selectforeground="#FFFFFF",
                        font=("Consolas", 9),
                        wrap="word",
                        relief="flat",
                        bd=0,
                        padx=8,
                        pady=6,
                        yscrollcommand=scroll.set,
                    )
                    txt.pack(side="left", fill="both", expand=True)
                    scroll.config(command=txt.yview)
                    self.txt_balao = txt

                if (
                    self.balao_fala is None
                    or self.txt_balao is None
                    or self.btn_copiar_codigo is None
                ):
                    return

                if self.ultimo_codigo_extraido:
                    self.btn_copiar_codigo.pack(side="right", padx=3)
                else:
                    self.btn_copiar_codigo.pack_forget()

                self.txt_balao.configure(state="normal")
                self.txt_balao.delete("1.0", tk.END)
                self.txt_balao.insert("1.0", self.ultima_fala_capri)
                self.txt_balao.configure(state="disabled")
                self.txt_balao.see("1.0")

                linhas_estimadas = sum(
                    max(1, math.ceil(len(linha) / 48))
                    for linha in self.ultima_fala_capri.splitlines()
                )
                altura_ideal = min(420, max(145, 65 + linhas_estimadas * 19))

                self.balao_aberto = True
                self.balao_fala.deiconify()
                self.balao_fala.geometry(f"430x{altura_ideal}")
                self._reposicionar_balao()
                self.balao_fala.lift()
            except Exception as e:
                log.warning("Aviso Balão de Fala: %s", e)

        try:
            self.root.after(0, _renderizar_balao)
        except Exception:
            pass

    def fechar_balao_fala(self) -> None:
        self.balao_aberto = False
        try:
            if self.balao_fala is not None and self.balao_fala.winfo_exists():
                self.balao_fala.withdraw()
        except Exception:
            pass

    def alternar_balao_fala(self) -> None:
        if self.balao_aberto:
            self.fechar_balao_fala()
        elif self.ultima_fala_capri:
            self.mostrar_balao_fala(self.ultima_fala_capri)

    def ativar_modo_livre(self) -> None:
        """Solta a Capri na tela (thread-safe)."""
        def _executar() -> None:
            if self.modo_livre is None:
                from ui.modo_livre import CapriModoLivre
                self.modo_livre = CapriModoLivre(self)
            self.modo_livre.ativar()

        try:
            self.root.after(0, _executar)
        except Exception:
            pass

    def desativar_modo_livre(self) -> None:
        """Traz a Capri de volta para a caixa do HUD (thread-safe)."""
        def _executar() -> None:
            if self.modo_livre is not None:
                self.modo_livre.desativar()

        try:
            self.root.after(0, _executar)
        except Exception:
            pass

    def _copiar_texto_balao(self) -> None:
        if not self.ultima_fala_capri or self.btn_copiar_tudo is None:
            return
        btn = self.btn_copiar_tudo
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.ultima_fala_capri)
            btn.configure(text="COPIADO!", fg=self.ACCENT_LIME)
            self.root.after(
                1400,
                lambda: btn.configure(text="COPIAR", fg=self.ACCENT_CYAN)
                if btn.winfo_exists()
                else None,
            )
        except Exception:
            pass

    def _copiar_codigo_balao(self) -> None:
        if not self.ultimo_codigo_extraido or self.btn_copiar_codigo is None:
            return
        btn = self.btn_copiar_codigo
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.ultimo_codigo_extraido)
            btn.configure(text="CÓDIGO COPIADO!")
            self.root.after(
                1400,
                lambda: btn.configure(text="COPIAR CÓDIGO") if btn.winfo_exists() else None,
            )
        except Exception:
            pass

    # =====================================================================
    # FUNÇÕES DA BARRA DE PESQUISA, VISÃO E CONTROLES
    # =====================================================================
    def _atualizar_visual_visao(self) -> None:
        if self.anexar_tela:
            self.btn_visao_barra.definir_estilo(self.ACCENT_CYAN, self.ACCENT_CYAN)
            self.borda_pesquisa.configure(bg=self.ACCENT_CYAN)
            self.placeholder_texto = "Pergunte sobre sua tela..."
        else:
            self.btn_visao_barra.definir_estilo(self.BORDER_DIM, self.TEXT_GRAY)
            self.borda_pesquisa.configure(bg=self.BORDER_PINK)
            self.placeholder_texto = "Conversar com Capri..."

    def _alternar_anexar_tela(self) -> None:
        estava_placeholder = self.var_pesquisa.get().strip() in (
            "",
            "Conversar com Capri...",
            "Pergunte sobre sua tela...",
        )
        self.anexar_tela = not self.anexar_tela
        self._atualizar_visual_visao()
        if estava_placeholder:
            self.var_pesquisa.set(self.placeholder_texto)
            self.entry_pesquisa.configure(
                fg=self.ACCENT_CYAN if self.anexar_tela else self.TEXT_GRAY
            )

    def _focar_entrada_pesquisa(self, _event: Any = None) -> None:
        try:
            self.root.focus_force()
            self.entry_pesquisa.focus_set()
            if self.var_pesquisa.get() in ("Conversar com Capri...", "Pergunte sobre sua tela..."):
                self.var_pesquisa.set("")
                self.entry_pesquisa.configure(fg=self.TEXT_WHITE)
        except Exception:
            pass

    def _ao_ganhar_foco_pesquisa(self, _event: Any = None) -> None:
        if self.var_pesquisa.get() in ("Conversar com Capri...", "Pergunte sobre sua tela..."):
            self.var_pesquisa.set("")
            self.entry_pesquisa.configure(fg=self.TEXT_WHITE)

    def _ao_perder_foco_pesquisa(self, _event: Any = None) -> None:
        if not self.var_pesquisa.get().strip():
            self.var_pesquisa.set(self.placeholder_texto)
            self.entry_pesquisa.configure(
                fg=self.ACCENT_CYAN if self.anexar_tela else self.TEXT_GRAY
            )

    def _submeter_pesquisa_interface(self, _event: Any = None) -> None:
        texto = self.var_pesquisa.get().strip()
        eh_placeholder = (not texto) or (
            texto in ("Conversar com Capri...", "Pergunte sobre sua tela...")
        )

        if eh_placeholder:
            if self.anexar_tela:
                texto = "o que está acontecendo na tela?"
            else:
                return

        self.var_pesquisa.set("")
        self.entry_pesquisa.configure(fg=self.TEXT_WHITE)

        usar_visao = self.anexar_tela
        if texto.lower().startswith(("/tela", "/ver")):
            usar_visao = True
            texto = (
                texto.split(" ", 1)[1].strip()
                if " " in texto
                else "o que está acontecendo na tela?"
            )

        if usar_visao:
            self.anexar_tela = False
            self._atualizar_visual_visao()
            self.enviar_comando_texto(
                f"/tela {texto}", legenda_exibicao=f'Você [TELA]: "{texto}"'
            )
        else:
            self.enviar_comando_texto(texto)

    def enviar_comando_texto(self, texto_comando: str, legenda_exibicao: str = "") -> None:
        cmd = texto_comando.strip()
        if not cmd:
            return
        legenda = legenda_exibicao or f'Você: "{cmd}"'
        log.info("Barra de Pesquisa: '%s'", cmd)
        self.atualizar_estado("PROCESSANDO...", self.ACCENT_VIOLET, legenda)
        self.fila_comandos_texto.put(cmd)

    def tem_comando_texto(self) -> bool:
        return not self.fila_comandos_texto.empty()

    def obter_comando_texto(self) -> str:
        try:
            return self.fila_comandos_texto.get_nowait()
        except queue.Empty:
            return ""

    def _aplicar_modo_transparencia(self) -> None:
        try:
            if self.config.get("modo_recorte_transparente", False):
                self.root.attributes("-alpha", 0.98)
                self.root.attributes("-transparentcolor", self.BG_SCREEN)
            else:
                self.root.attributes("-transparentcolor", "")
                self.root.attributes("-alpha", 0.94)
        except Exception:
            pass

    def _ao_clicar_sprite(self, event: Any) -> None:
        self._iniciar_arraste(event)
        self.ate_quando_headpat = time.time() + 2.2

    def _obter_sprite_pose_base(self) -> str:
        pose = str(self.config.get("pose_padrao", "Padrao"))
        mapa_poses = {
            "Padrao": "capri-neutral.png",
            "Bracos Cruzados": "capri-arms_crossed-neutral.png",
            "Mao na Cintura": "capri-hand_on_hip-neutral.png",
            "Mao no Queixo": "capri-chin_rest-neutral.png",
            "Sentada na Borda": "capri-sit_edge-neutral.png",
            "Sentada no Chao": "capri-sit_floor-neutral.png",
            "Agachada": "capri-crouch-neutral.png",
            "Reclinada": "capri-recline-neutral.png",
        }
        return mapa_poses.get(pose, "capri-neutral.png")

    def _selecionar_nome_sprite_atual(self) -> tuple[str, str]:
        agora = time.time()

        if self.em_intro and self.sprites.tem_pacote_sprites():
            quadros_intro = [
                "01-signal.png", "02-gaze.png", "03-arrival.png",
                "04-landing.png", "05-greeting.png", "06-wink.png", "07-ready.png",
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
            pose = str(self.config.get("pose_padrao", "Padrao"))
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
            if nv < 0.42:
                return "capri-idle-mouth_small.png", ""
            if nv < 0.68:
                return "capri-idle-mouth_round.png", ""
            return "capri-idle-mouth_wide.png", ""

        if "SPOTIFY" in estado or "MÚSICA" in estado or agora < self.ate_quando_musica:
            return "capri-music-window.png", ""

        if (
            "OUVINDO" in estado
            or "COMANDO" in estado
            or "VOZ DETECTADA" in estado
            or "NOME DO APP" in estado
        ):
            pose = str(self.config.get("pose_padrao", "Padrao"))
            if pose == "Sentada na Borda":
                return "capri-sit_edge-attentive.png", ""
            if pose == "Agachada":
                return "capri-crouch-attentive.png", ""
            return "capri-lean_in-attentive.png", ""

        if any(
            k in estado
            for k in ("TRANSCREVENDO", "PESQUISANDO", "PROCESSANDO", "ANALISANDO", "GERANDO")
        ):
            pose = str(self.config.get("pose_padrao", "Padrao"))
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
            if self.etapa_piscar == 2:
                if agora - self.ultimo_tick_piscar > 0.08:
                    self.etapa_piscar = 3
                    self.ultimo_tick_piscar = agora
                return "capri-idle-blink_closed.png", ""
            if self.etapa_piscar == 3:
                if agora - self.ultimo_tick_piscar > 0.06:
                    self.etapa_piscar = 0
                    self.proximo_piscar = agora + random.uniform(3.0, 6.2)
                    if random.random() < 0.28:
                        self.expressao_idle_extra = random.choice([
                            "capri-idle-look_left.png",
                            "capri-idle-look_right.png",
                            "capri-idle-smirk.png",
                            "capri-idle-happy.png",
                            "capri-idle-wink_half.png",
                        ])
                        self.fim_expressao_idle = agora + random.uniform(1.4, 2.6)
                return "capri-idle-blink_half.png", ""

            if agora < self.fim_expressao_idle and self.expressao_idle_extra:
                return self.expressao_idle_extra, ""

        return pose_base, ""

    def _iniciar_arraste(self, event: Any) -> None:
        # Calcula offset relativo à janela inteira para evitar pulos ao arrastar pelo card inferior
        self._offset_x = event.x_root - self.root.winfo_x()
        self._offset_y = event.y_root - self.root.winfo_y()

    def _arrastar_janela(self, event: Any) -> None:
        x = event.x_root - self._offset_x
        y = event.y_root - self._offset_y
        self.root.geometry(f"+{x}+{y}")
        self._reposicionar_balao()

    def _animar_hud(self) -> None:
        if not self.rodando:
            return

        # Economiza CPU quando o HUD está minimizado na bandeja ou no Modo Livre
        try:
            oculto = self.root.state() == "withdrawn"
        except Exception:
            oculto = False
        if oculto or (self.modo_livre is not None and self.modo_livre.ativo):
            self.root.after(200, self._animar_hud)
            return

        try:
            self.canvas_sprite.delete("all")
            w = max(440, self.canvas_sprite.winfo_width())
            h = max(230, self.canvas_sprite.winfo_height())

            if not self.config.get("modo_recorte_transparente", False):
                for y_line in range(18, h - 6, 5):
                    self.canvas_sprite.create_line(
                        6, y_line, w - 6, y_line, fill=self.BG_SCANLINE, width=1
                    )

            nome_sprite, efeito = self._selecionar_nome_sprite_atual()
            foto_tk = self.sprites.obter_sprite_tk(nome_sprite, sobrepor_efeito=efeito)

            if foto_tk is not None:
                offset_resp = (
                    int(math.sin(self.fase_onda * 0.25) * 2)
                    if "FALANDO" not in self.estado_atual
                    else 0
                )
                self.canvas_sprite.create_image(
                    w // 2, (h // 2) + 8 + offset_resp, image=foto_tk
                )

                if nome_sprite == "capri-music-window.png":
                    notas = self.sprites.obter_notas_musicais_tk()
                    for idx, nota_tk in enumerate(notas):
                        ang = self.fase_onda * 0.35 + idx * 1.6
                        nx = 75 + (idx * 90) + int(math.sin(ang) * 12)
                        ny = 60 + int(math.cos(ang) * 18)
                        self.canvas_sprite.create_image(nx, ny, image=nota_tk)
            else:
                self.canvas_sprite.create_text(
                    w // 2,
                    h // 2,
                    text="[ SPRITES NÃO ENCONTRADOS ]",
                    fill=self.TEXT_PINK,
                    font=("Consolas", 10, "bold"),
                )

            pose_str = str(self.config.get("pose_padrao", "PADRAO")).upper()
            self.canvas_sprite.create_text(
                18, h - 10, text=pose_str, fill="#6E5662", font=("Consolas", 7, "bold"), anchor="w"
            )
            pontos_onda = "• " * 11
            self.canvas_sprite.create_text(
                w - 14,
                h - 10,
                text=f"{pontos_onda} {self.VERSAO_HUD}",
                fill="#6E5662",
                font=("Consolas", 7),
                anchor="e",
            )

            self.canvas_sprite.create_rectangle(
                4, 14, w - 4, h - 2, outline=self.BORDER_PINK, width=1.5
            )

            cor_canto = self.ACCENT_VIOLET
            self.canvas_sprite.create_line(2, 12, 2, 34, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(2, 12, 20, 12, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(w - 2, 12, w - 2, 34, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(w - 20, 12, w - 2, 12, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(2, h - 24, 2, h, fill=cor_canto, width=3)
            self.canvas_sprite.create_line(w - 2, h - 24, w - 2, h, fill=cor_canto, width=3)

            texto_badge = f"CAPRI // {self.estado_atual}"
            largura_badge = max(135, len(texto_badge) * 8 + 20)
            self.canvas_sprite.create_rectangle(
                24, 3, 24 + largura_badge, 25, fill="#191024", outline=self.ACCENT_VIOLET, width=2
            )
            self.canvas_sprite.create_text(
                24 + (largura_badge // 2),
                14,
                text=texto_badge,
                fill="#E2D9F3",
                font=("Consolas", 8, "bold"),
            )

            self.fase_onda += 0.25
            if self.painel_status_visivel and self.canvas_progresso.winfo_exists():
                self.canvas_progresso.delete("all")
                wp = max(380, self.canvas_progresso.winfo_width())
                if self.pausada:
                    self.canvas_progresso.create_rectangle(0, 0, 60, 4, fill="#475569", outline="")
                elif self.nivel_voz > 0.05:
                    larg_voz = int(min(1.0, self.nivel_voz * 1.2) * wp)
                    self.canvas_progresso.create_rectangle(
                        0, 0, max(40, larg_voz), 4, fill=self.TEXT_PINK, outline=""
                    )
                else:
                    self.pos_barra_progresso = (self.pos_barra_progresso + 6) % (wp + 110)
                    x1 = self.pos_barra_progresso - 110
                    x2 = self.pos_barra_progresso
                    self.canvas_progresso.create_rectangle(
                        max(0.0, x1), 0, min(float(wp), x2), 4, fill=self.TEXT_PINK, outline=""
                    )
        except Exception:
            pass

        if self.rodando:
            self.root.after(45, self._animar_hud)

    def acionar_sprite_temporario(self, nome_sprite: str, duracao: float = 2.5) -> None:
        self.sprite_forcado = nome_sprite
        self.ate_quando_forcado = time.time() + duracao

    def atualizar_estado(self, novo_estado: str, cor: str = "#D45B72", legenda: str = "") -> None:
        self.estado_atual = novo_estado
        self.cor_atual = cor
        if "SPOTIFY" in novo_estado.upper():
            self.ate_quando_musica = time.time() + 5.0

        mapa_subtitulos = {
            "EM ESPERA": "Núcleo local ativo e aguardando...",
            "OUVINDO VOCÊ...": "Captando áudio do microfone...",
            "TRANSCREVENDO...": "Processando voz localmente na RAM...",
            "PESQUISANDO IA...": f"Consultando API ({self.config.get('provedor_ia', 'Gemini')})...",
            "GERANDO CÓDIGO...": f"Gerando código ({self.config.get('provedor_ia', 'Gemini')})...",
            "ANALISANDO TELA...": "Analisando sua tela com Gemini...",
            "PROCESSANDO...": "Executando instrução...",
            "FALANDO...": "Transmitindo resposta de voz...",
            "MIC SILENCIADO": "Microfone silenciado (Use a barra abaixo).",
        }
        self.subtitulo_card = mapa_subtitulos.get(novo_estado.upper(), f"Status: {novo_estado}")

        if legenda:
            linha_unica = re.sub(r"\s+", " ", legenda).strip()
            if len(linha_unica) > 54:
                linha_unica = linha_unica[:51].rstrip() + "..."
            self.legenda_card = linha_unica

        def _atualizar_ui() -> None:
            if hasattr(self, "lbl_subtitulo_card") and self.lbl_subtitulo_card.winfo_exists():
                self.lbl_subtitulo_card.configure(text=self.subtitulo_card)
            if hasattr(self, "lbl_legenda_card") and self.lbl_legenda_card.winfo_exists():
                self.lbl_legenda_card.configure(text=self.legenda_card)

        try:
            self.root.after(0, _atualizar_ui)
        except Exception:
            pass

    def alternar_pausa(self, *_args: Any) -> None:
        self.pausada = not self.pausada
        if self.pausada:
            if hasattr(self, "btn_pausa"):
                self.btn_pausa.configure(text="MUTADA", bg="#FF0055", fg="#FFFFFF")
            if hasattr(self, "btn_mic_barra"):
                self.btn_mic_barra.definir_estilo("#FF0055", "#FF0055", "🔇")
            self.atualizar_estado(
                "MIC SILENCIADO", "#FF0055", "Microfone mutado. Use a barra abaixo."
            )
        else:
            if hasattr(self, "btn_pausa"):
                self.btn_pausa.configure(text="MIC ON", bg="#00FF66", fg="#090D16")
            if hasattr(self, "btn_mic_barra"):
                self.btn_mic_barra.definir_estilo("#00FF66", "#00FF66", "🎙")
            self.atualizar_estado(
                "EM ESPERA", self.BORDER_PINK, "Escuta ativa. Diga 'Capri' ou digite."
            )

    def _obter_pasta_assets(self) -> str:
        meipass = getattr(sys, "_MEIPASS", None)
        if getattr(sys, "frozen", False) and isinstance(meipass, str):
            pasta_empacotada = os.path.join(meipass, "assets")
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
                    img.save(
                        caminho_ico,
                        format="ICO",
                        sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)],
                    )
                return caminho_ico
            except Exception:
                return caminho_png
        if os.path.exists(caminho_ico):
            return caminho_ico
        return ""

    def _aplicar_icone_janela(self, janela: tk.Tk | tk.Toplevel) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "capricorn.capri.assistant"
            )
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
            janela.iconphoto(True, str(foto))
            self._icones_ref.append(foto)
        except Exception:
            pass

    def _criar_imagem_icone(self) -> Image.Image:
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

    def _iniciar_bandeja_sistema(self) -> None:
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Mostrar HUD", lambda: self.root.after(0, self.mostrar_da_bandeja)),
                pystray.MenuItem("Configurações", lambda: self.root.after(0, self.abrir_configuracoes)),
                pystray.MenuItem("Mutada / Ativa", lambda: self.root.after(0, self.alternar_pausa)),
                pystray.MenuItem("Encerrar Capri", lambda: self.root.after(0, self.desligar_tudo)),
            )
            self.icone_bandeja = pystray.Icon("Capri", self._criar_imagem_icone(), "Capri Assistant", menu)
            threading.Thread(target=self.icone_bandeja.run, daemon=True).start()
        except Exception as e:
            log.warning("Aviso Bandeja: %s", e)

    def ocultar_para_bandeja(self) -> None:
        self.root.withdraw()
        try:
            if self.balao_fala is not None and self.balao_fala.winfo_exists():
                self.balao_fala.withdraw()
        except Exception:
            pass

    def mostrar_da_bandeja(self) -> None:
        if self.modo_livre is not None and self.modo_livre.ativo:
            self.modo_livre.desativar()
            return
        self.root.deiconify()
        self.root.lift()
        try:
            if self.balao_aberto and self.balao_fala is not None and self.balao_fala.winfo_exists():
                self.balao_fala.deiconify()
                self._reposicionar_balao()
                self.balao_fala.lift()
        except Exception:
            pass

    def desligar_tudo(self) -> None:
        self.rodando = False
        try:
            if self.ao_encerrar is not None:
                self.ao_encerrar()
        except Exception:
            pass
        try:
            if self.icone_bandeja is not None:
                self.icone_bandeja.stop()
        except Exception:
            pass
        try:
            if self.balao_fala is not None and self.balao_fala.winfo_exists():
                self.balao_fala.destroy()
        except Exception:
            pass
        try:
            if (
                self.modo_livre is not None
                and self.modo_livre.win is not None
                and self.modo_livre.win.winfo_exists()
            ):
                self.modo_livre.win.destroy()
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
            "apelidos": list(variacoes),
        }
        salvar_configuracoes(self.config)
        return True

    def adicionar_executavel_manual(
        self, callback_atualizar_lista: Callable[[], Any] | None = None
    ) -> None:
        janela_pai: tk.Tk | tk.Toplevel = (
            self.janela_config
            if (self.janela_config is not None and self.janela_config.winfo_exists())
            else self.root
        )
        caminho = filedialog.askopenfilename(
            parent=janela_pai,
            title="Selecione o Executável ou Atalho do Programa",
            filetypes=[
                ("Executáveis e Atalhos", "*.exe *.lnk *.url *.bat *.cmd"),
                ("Todos os arquivos", "*.*"),
            ],
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
            dialogo, text="EXECUTÁVEL DETECTADO", fg=CYAN, bg=BG_DARK, font=("Consolas", 11, "bold")
        ).pack(pady=(16, 2))
        tk.Frame(dialogo, bg=CYAN, height=1).pack(fill="x", padx=30, pady=(0, 8))
        tk.Label(
            dialogo, text=os.path.basename(caminho), fg=CORAL, bg=BG_DARK, font=("Consolas", 9, "bold")
        ).pack(pady=(0, 10))
        tk.Label(
            dialogo,
            text="Como você quer chamar este executável por voz? (Ex: CS2)",
            fg="#E2E8F0",
            bg=BG_DARK,
            font=("Consolas", 9),
        ).pack(pady=2)

        borda_input = tk.Frame(dialogo, bg=BORDER_RED, padx=1, pady=1)
        borda_input.pack(pady=8)
        entrada_nome = tk.Entry(
            borda_input,
            bg="#1C0D1B",
            fg=CYAN,
            insertbackground=CYAN,
            font=("Consolas", 12, "bold"),
            relief="flat",
            justify="center",
            width=28,
        )
        entrada_nome.pack(ipady=5)
        sugestao = os.path.splitext(os.path.basename(caminho))[0]
        entrada_nome.insert(0, sugestao)
        entrada_nome.select_range(0, tk.END)
        entrada_nome.focus_set()

        def _confirmar(_event: Any = None) -> None:
            nome_escolhido = entrada_nome.get().strip()
            if nome_escolhido:
                self.salvar_executavel_personalizado(caminho, nome_escolhido)
                dialogo.destroy()
                if callback_atualizar_lista is not None:
                    callback_atualizar_lista()

        entrada_nome.bind("<Return>", _confirmar)
        borda_btn = tk.Frame(dialogo, bg=CORAL, padx=1, pady=1)
        borda_btn.pack(pady=8)
        tk.Button(
            borda_btn,
            text="SALVAR GATILHO DE VOZ",
            bg=BG_DARK,
            fg=CYAN,
            activebackground="#261224",
            activeforeground=CYAN,
            font=("Consolas", 10, "bold"),
            relief="flat",
            cursor="hand2",
            command=_confirmar,
            padx=16,
            pady=4,
        ).pack()

    # =====================================================================
    # 4. CENTRAL DE CONFIGURAÇÃO COMPLETA (ESTILO CYBERPUNK 2077)
    # =====================================================================
    def abrir_configuracoes(self, *_args: Any) -> None:
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

        chaves_ia_iniciais = (
            str(self.config.get("provedor_ia", "")).strip(),
            str(self.config.get("gemini_api_key", "")).strip(),
            str(self.config.get("claude_api_key", "")).strip(),
            str(self.config.get("deepseek_api_key", "")).strip(),
        )

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
        widgets_abas: dict[str, tuple[tk.Label, tk.Frame]] = {}

        def selecionar_aba(nome_aba: str) -> None:
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
                f_aba,
                text=nome_aba,
                fg=CORAL,
                bg=BG_MAIN,
                font=("Consolas", 11, "bold"),
                cursor="hand2",
            )
            lbl_t.pack()
            barra_sub = tk.Frame(f_aba, bg=BG_MAIN, height=2)
            barra_sub.pack(fill="x", pady=(3, 0))
            lbl_t.bind("<Button-1>", lambda _e, n=nome_aba: selecionar_aba(n))
            widgets_abas[nome_aba] = (lbl_t, barra_sub)

        corpo = tk.Frame(win, bg=BG_MAIN)
        corpo.pack(fill="both", expand=True, padx=28, pady=(4, 6))
        col_esquerda = tk.Frame(corpo, bg=BG_MAIN, width=210)
        col_esquerda.pack(side="left", fill="y", padx=(0, 24))
        col_esquerda.pack_propagate(False)

        btn_bench = tk.Canvas(
            col_esquerda, width=195, height=38, bg=BG_MAIN, highlightthickness=0, cursor="hand2"
        )
        btn_bench.pack(pady=(8, 14), anchor="w")

        def desenhar_botao_lateral(hover: bool = False) -> None:
            btn_bench.delete("all")
            cor_borda = CYAN if hover else CORAL_DIM
            cor_fundo = "#1E0E1D" if hover else "#160A16"
            pontos = [2, 2, 193, 2, 193, 28, 185, 36, 2, 36]
            btn_bench.create_polygon(pontos, fill=cor_fundo, outline=cor_borda, width=1.5)
            btn_bench.create_oval(12, 10, 28, 26, fill=CYAN, outline="")
            btn_bench.create_text(20, 18, text="+", fill=BG_MAIN, font=("Consolas", 11, "bold"))
            btn_bench.create_text(
                36, 19, text="ADICIONAR .EXE", anchor="w", fill=CYAN, font=("Consolas", 9, "bold")
            )

        desenhar_botao_lateral(False)
        btn_bench.bind("<Enter>", lambda _e: desenhar_botao_lateral(True))
        btn_bench.bind("<Leave>", lambda _e: desenhar_botao_lateral(False))
        btn_bench.bind(
            "<Button-1>",
            lambda _e: self.adicionar_executavel_manual(
                callback_atualizar_lista=renderizar_conteudo_aba
            ),
        )

        col_direita = tk.Frame(corpo, bg=BG_MAIN)
        col_direita.pack(side="left", fill="both", expand=True)

        def criar_switch_cyberpunk(
            parent: tk.Widget, estado_inicial: bool, ao_alternar: Callable[[bool], Any]
        ) -> SwitchCyberpunk:
            return SwitchCyberpunk(
                parent=parent,
                estado_inicial=estado_inicial,
                ao_alternar=ao_alternar,
                cor_cyan=CYAN,
                cor_coral=CORAL,
                cor_coral_dim=CORAL_DIM,
                cor_coral_off=CORAL_OFF,
            )

        def criar_divisor_secao(parent: tk.Misc, titulo_secao: str) -> None:
            f_sec = tk.Frame(parent, bg=BG_MAIN)
            f_sec.pack(fill="x", pady=(10, 4))
            tk.Frame(f_sec, bg=CYAN, height=1).pack(fill="x")
            tk.Label(
                f_sec,
                text=titulo_secao,
                fg="#E2E8F0",
                bg=BG_MAIN,
                font=("Consolas", 10, "bold"),
                anchor="w",
            ).pack(fill="x", pady=(4, 0))

        vars_chaves = {
            "provedor_ia": tk.StringVar(value=str(self.config.get("provedor_ia", "Gemini"))),
            "gemini_api_key": tk.StringVar(value=str(self.config.get("gemini_api_key", ""))),
            "claude_api_key": tk.StringVar(value=str(self.config.get("claude_api_key", ""))),
            "deepseek_api_key": tk.StringVar(value=str(self.config.get("deepseek_api_key", ""))),
            "fish_api_key": tk.StringVar(value=str(self.config.get("fish_api_key", ""))),
            "fish_voice_id": tk.StringVar(value=str(self.config.get("fish_voice_id", ""))),
            "pose_padrao": tk.StringVar(value=str(self.config.get("pose_padrao", "Padrao"))),
        }

        def salvar_chaves_em_memoria(*_args: Any) -> None:
            for k, v_tk in vars_chaves.items():
                self.config[k] = v_tk.get().strip()
            salvar_configuracoes(self.config)

        for var in vars_chaves.values():
            var.trace_add("write", salvar_chaves_em_memoria)

        def renderizar_conteudo_aba() -> None:
            try:
                win.unbind_all("<MouseWheel>")
            except Exception:
                pass

            for w in col_direita.winfo_children():
                w.destroy()

            aba = aba_atual.get()
            if aba == "APLICATIVOS":
                canvas_lista = tk.Canvas(col_direita, bg=BG_MAIN, highlightthickness=0)
                scroll_bar = tk.Scrollbar(
                    col_direita,
                    orient="vertical",
                    command=canvas_lista.yview,
                    bg=BG_MAIN,
                    troughcolor=BG_MAIN,
                    activebackground=CORAL,
                )
                frame_scroll = tk.Frame(canvas_lista, bg=BG_MAIN)
                win_id = canvas_lista.create_window((0, 0), window=frame_scroll, anchor="nw")
                canvas_lista.bind(
                    "<Configure>", lambda e: canvas_lista.itemconfig(win_id, width=e.width)
                )
                frame_scroll.bind(
                    "<Configure>",
                    lambda _e: canvas_lista.configure(scrollregion=canvas_lista.bbox("all")),
                )
                canvas_lista.configure(yscrollcommand=scroll_bar.set)
                canvas_lista.pack(side="left", fill="both", expand=True)
                scroll_bar.pack(side="right", fill="y", padx=(6, 0))

                def _rolar_mouse(event: Any) -> None:
                    if canvas_lista.winfo_exists():
                        canvas_lista.yview_scroll(int(-1 * (event.delta / 120)), "units")

                # Só captura a roda do mouse enquanto o cursor estiver sobre a lista
                canvas_lista.bind(
                    "<Enter>", lambda _e: canvas_lista.bind_all("<MouseWheel>", _rolar_mouse)
                )
                canvas_lista.bind("<Leave>", lambda _e: canvas_lista.unbind_all("<MouseWheel>"))

                apps_dict: dict[str, dict[str, Any]] = self.config.get("apps", {})
                personalizados = [
                    (k, v) for k, v in apps_dict.items() if v.get("personalizado", False)
                ]
                sistema_apps = [
                    (k, v) for k, v in apps_dict.items() if not v.get("personalizado", False)
                ]
                personalizados.sort(key=lambda x: str(x[1].get("nome", x[0])).lower())
                sistema_apps.sort(key=lambda x: str(x[1].get("nome", x[0])).lower())

                def _adicionar_linha_app(chave_app: str, dados_app: dict[str, Any]) -> None:
                    linha = tk.Frame(frame_scroll, bg=BG_MAIN, pady=3, padx=6)
                    linha.pack(fill="x", pady=1)
                    lbl = tk.Label(
                        linha,
                        text=str(dados_app.get("nome", chave_app)),
                        fg=CORAL,
                        bg=BG_MAIN,
                        font=("Consolas", 10, "bold"),
                        anchor="w",
                    )
                    lbl.pack(side="left", fill="x", expand=True)

                    def _toggle(novo_estado: bool, k: str = chave_app) -> None:
                        self.config["apps"][k]["ativo"] = novo_estado
                        salvar_configuracoes(self.config)

                    sw = criar_switch_cyberpunk(linha, bool(dados_app.get("ativo", False)), _toggle)
                    sw.pack(side="right")

                    def _on_enter(_e: Any) -> None:
                        linha.configure(bg=BG_ROW_HOVER)
                        lbl.configure(bg=BG_ROW_HOVER, fg=CYAN)
                        sw.redesenhar_fundo()

                    def _on_leave(_e: Any) -> None:
                        linha.configure(bg=BG_MAIN)
                        lbl.configure(bg=BG_MAIN, fg=CORAL)
                        sw.redesenhar_fundo()

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

                def _criar_linha_input(rotulo: str, var_tk: tk.StringVar, ocultar: bool = False) -> None:
                    linha = tk.Frame(col_direita, bg=BG_MAIN, pady=5)
                    linha.pack(fill="x")
                    tk.Label(
                        linha,
                        text=rotulo,
                        fg=CORAL,
                        bg=BG_MAIN,
                        font=("Consolas", 10, "bold"),
                        anchor="w",
                    ).pack(side="left", fill="x", expand=True)
                    moldura = tk.Frame(linha, bg=CORAL_DIM, padx=1, pady=1)
                    moldura.pack(side="right")
                    tk.Entry(
                        moldura,
                        textvariable=var_tk,
                        bg=BG_INPUT,
                        fg=CYAN,
                        insertbackground=CYAN,
                        font=("Consolas", 10, "bold"),
                        relief="flat",
                        width=34,
                        justify="center",
                        show="*" if ocultar else "",
                    ).pack(ipady=3, ipadx=6)

                _criar_linha_input("Gemini API Key", vars_chaves["gemini_api_key"], ocultar=True)
                _criar_linha_input("Claude API Key", vars_chaves["claude_api_key"], ocultar=True)
                _criar_linha_input("DeepSeek API Key", vars_chaves["deepseek_api_key"], ocultar=True)
                _criar_linha_input("Fish Audio API Key", vars_chaves["fish_api_key"], ocultar=True)
                _criar_linha_input("Fish Audio Voice ID", vars_chaves["fish_voice_id"], ocultar=False)

                criar_divisor_secao(col_direita, "Configuração de Módulos (Clique para alternar IA)")
                opcoes_ia = ["Gemini", "Claude", "DeepSeek"]

                f_sel = tk.Frame(col_direita, bg=BG_MAIN, pady=5)
                f_sel.pack(fill="x")
                tk.Label(
                    f_sel,
                    text="Provedor de Pesquisa IA",
                    fg=CORAL,
                    bg=BG_MAIN,
                    font=("Consolas", 10, "bold"),
                ).pack(side="left")
                box_ia = tk.Frame(f_sel, bg=CORAL_DIM, padx=1, pady=1)
                box_ia.pack(side="right")
                inner_ia = tk.Frame(box_ia, bg=BG_INPUT, width=260, height=26, cursor="hand2")
                inner_ia.pack_propagate(False)
                inner_ia.pack()

                def _mudar_ia(delta: int) -> None:
                    atual = vars_chaves["provedor_ia"].get()
                    idx = opcoes_ia.index(atual) if atual in opcoes_ia else 0
                    novo = opcoes_ia[(idx + delta) % len(opcoes_ia)]
                    vars_chaves["provedor_ia"].set(novo)

                btn_esq = tk.Label(
                    inner_ia, text="<", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2"
                )
                btn_esq.pack(side="left", padx=10)
                lbl_val = tk.Label(
                    inner_ia,
                    textvariable=vars_chaves["provedor_ia"],
                    fg=CYAN,
                    bg=BG_INPUT,
                    font=("Consolas", 10, "bold"),
                    cursor="hand2",
                )
                lbl_val.pack(expand=True)
                btn_dir = tk.Label(
                    inner_ia, text=">", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2"
                )
                btn_dir.pack(side="right", padx=10)

                btn_esq.bind("<Button-1>", lambda _e: _mudar_ia(-1))
                lbl_val.bind("<Button-1>", lambda _e: _mudar_ia(1))
                btn_dir.bind("<Button-1>", lambda _e: _mudar_ia(1))

            elif aba == "SISTEMA":
                criar_divisor_secao(col_direita, "Preferências de Operação & Sprites")

                linha_mute = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_mute.pack(fill="x")
                tk.Label(
                    linha_mute,
                    text="Escuta de Microfone Ativa",
                    fg=CORAL,
                    bg=BG_MAIN,
                    font=("Consolas", 10, "bold"),
                ).pack(side="left")
                criar_switch_cyberpunk(
                    linha_mute,
                    not self.pausada,
                    lambda ativo: self.alternar_pausa() if (ativo == self.pausada) else None,
                ).pack(side="right")

                linha_startup = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_startup.pack(fill="x")
                tk.Label(
                    linha_startup,
                    text="Iniciar junto com o Windows",
                    fg=CORAL,
                    bg=BG_MAIN,
                    font=("Consolas", 10, "bold"),
                ).pack(side="left")

                def _alternar_startup(ativo: bool) -> None:
                    self.config["iniciar_com_windows"] = ativo
                    salvar_configuracoes(self.config)
                    configurar_inicializacao_windows(ativo)

                criar_switch_cyberpunk(
                    linha_startup,
                    bool(self.config.get("iniciar_com_windows", True)),
                    _alternar_startup,
                ).pack(side="right")

                linha_recorte = tk.Frame(col_direita, bg=BG_MAIN, pady=6)
                linha_recorte.pack(fill="x")
                tk.Label(
                    linha_recorte,
                    text="Modo Mascote (Recorte 100% Transparente)",
                    fg=CORAL,
                    bg=BG_MAIN,
                    font=("Consolas", 10, "bold"),
                ).pack(side="left")

                def _alternar_recorte(ativo: bool) -> None:
                    self.config["modo_recorte_transparente"] = ativo
                    salvar_configuracoes(self.config)
                    self._aplicar_modo_transparencia()

                criar_switch_cyberpunk(
                    linha_recorte,
                    bool(self.config.get("modo_recorte_transparente", False)),
                    _alternar_recorte,
                ).pack(side="right")

                poses_disponiveis = [
                    "Padrao", "Bracos Cruzados", "Mao na Cintura",
                    "Mao no Queixo", "Sentada na Borda", "Sentada no Chao",
                    "Agachada", "Reclinada",
                ]
                f_pose = tk.Frame(col_direita, bg=BG_MAIN, pady=8)
                f_pose.pack(fill="x")
                tk.Label(
                    f_pose,
                    text="Pose Padrão da Capri",
                    fg=CORAL,
                    bg=BG_MAIN,
                    font=("Consolas", 10, "bold"),
                ).pack(side="left")
                box_p = tk.Frame(f_pose, bg=CORAL_DIM, padx=1, pady=1)
                box_p.pack(side="right")
                inner_p = tk.Frame(box_p, bg=BG_INPUT, width=240, height=26, cursor="hand2")
                inner_p.pack_propagate(False)
                inner_p.pack()

                def _mudar_pose(delta: int) -> None:
                    atual = vars_chaves["pose_padrao"].get()
                    idx = poses_disponiveis.index(atual) if atual in poses_disponiveis else 0
                    novo = poses_disponiveis[(idx + delta) % len(poses_disponiveis)]
                    vars_chaves["pose_padrao"].set(novo)

                b_pe = tk.Label(
                    inner_p, text="<", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2"
                )
                b_pe.pack(side="left", padx=10)
                l_pv = tk.Label(
                    inner_p,
                    textvariable=vars_chaves["pose_padrao"],
                    fg=CYAN,
                    bg=BG_INPUT,
                    font=("Consolas", 10, "bold"),
                    cursor="hand2",
                )
                l_pv.pack(expand=True)
                b_pd = tk.Label(
                    inner_p, text=">", fg=CYAN, bg=BG_INPUT, font=("Consolas", 10, "bold"), cursor="hand2"
                )
                b_pd.pack(side="right", padx=10)

                b_pe.bind("<Button-1>", lambda _e: _mudar_pose(-1))
                l_pv.bind("<Button-1>", lambda _e: _mudar_pose(1))
                b_pd.bind("<Button-1>", lambda _e: _mudar_pose(1))

        rodape = tk.Frame(win, bg=BG_MAIN, pady=12)
        rodape.pack(fill="x", padx=28, side="bottom")

        def fechar_e_aplicar(*_args: Any) -> None:
            try:
                win.unbind_all("<MouseWheel>")
            except Exception:
                pass
            salvar_chaves_em_memoria()
            chaves_ia_finais = (
                str(self.config.get("provedor_ia", "")).strip(),
                str(self.config.get("gemini_api_key", "")).strip(),
                str(self.config.get("claude_api_key", "")).strip(),
                str(self.config.get("deepseek_api_key", "")).strip(),
            )
            if chaves_ia_finais != chaves_ia_iniciais:
                self.reiniciar_ia = True
            self.janela_config = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", fechar_e_aplicar)
        borda_central = tk.Frame(rodape, bg=CORAL_DIM, padx=1, pady=1)
        borda_central.pack(anchor="center")
        tk.Button(
            borda_central,
            text="SALVAR E APLICAR",
            bg=BG_MAIN,
            fg=CYAN,
            activebackground=BG_ROW_HOVER,
            activeforeground=CYAN,
            font=("Consolas", 10, "bold"),
            relief="flat",
            cursor="hand2",
            padx=26,
            pady=5,
            command=fechar_e_aplicar,
        ).pack()

        selecionar_aba("APLICATIVOS")

    def iniciar(self) -> None:
        self.root.mainloop()