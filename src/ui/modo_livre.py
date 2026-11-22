import os
import math
import time
import random
import ctypes
from ctypes import wintypes
import tkinter as tk
from PIL import Image, ImageOps, ImageTk
from core.logger import obter_logger
log = obter_logger("modo_livre")  # ou "cerebro", "memoria", "modo_livre", "voz"

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


CLASSES_IGNORADAS = {
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Progman",
    "WorkerW",
    "NotifyIconOverflowWindow",
    "Windows.UI.Core.CoreWindow",
    "TaskListThumbnailWnd",
}


class CapriModoLivre:
    """Modo Desktop Pet ('Fuga da Caixa'): Capri solta na tela interagindo com janelas."""

    # Cor de chroma-key rara que não conflita com o preto nem com o verde neon da Capri
    CHROMA_HEX = "#010203"
    CHROMA_RGB = (1, 2, 3)

    # Quantos pixels o sprite desce sobre o topo da janela para sentar na borda
    # (aumente este valor se quiser ela mais baixa; diminua se quiser mais alta)
    OFFSET_SENTAR_BORDA = 54

    def __init__(self, hud):
        self.hud = hud
        self.ativo = False
        self.win = None
        self.canvas = None
        self.mini_chat = None

        self.largura = 156
        self.altura = 156
        self.x = 200.0
        self.y = 200.0
        self.vx = 2.2
        self.vy = 0.0
        self.olhando_esquerda = False

        # Estados: ANDANDO | SENTADA | EMP_JANELA | CAINDO | ARRASTANDO
        self.estado_fisica = "CAINDO"
        self.tempo_proxima_decisao = 0.0
        self.fase_passo = 0.0
        self.hwnd_alvo = None
        self.offset_x_janela = 120
        self._tick_topo = 0

        # Controle de arraste e carinho
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._clique_inicio_x = 0
        self._clique_inicio_y = 0
        self._arrastou = False

        # Cache próprio de sprites recortados (normal e espelhado)
        self._cache_sprites = {}
        self._pid_atual = os.getpid()
        self._user32 = ctypes.windll.user32
        self._configurar_win32()
        try:
            self._dwmapi = ctypes.windll.dwmapi
        except Exception:
            self._dwmapi = None

    def _configurar_win32(self):
        """Tipagem explícita para chamadas 64-bit da API do Windows (evita erro com HWND_TOPMOST)."""
        try:
            self._user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            self._user32.GetAncestor.restype = wintypes.HWND
            self._user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            self._user32.SetWindowPos.restype = wintypes.BOOL
        except Exception:
            pass

    def _garantir_sempre_no_topo(self):
        """Mantém a Capri permanentemente sobre todas as janelas sem roubar o foco."""
        if not (self.win and self.win.winfo_exists()):
            return
        try:
            hwnd = self._user32.GetAncestor(wintypes.HWND(self.win.winfo_id()), 2)  # GA_ROOT = 2
            if not hwnd:
                hwnd = wintypes.HWND(self.win.winfo_id())
            # HWND_TOPMOST (-1) | SWP_NOSIZE (0x01) | SWP_NOMOVE (0x02) | SWP_NOACTIVATE (0x10) | SWP_SHOWWINDOW (0x40)
            self._user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0053)
        except Exception:
            try:
                self.win.attributes("-topmost", True)
            except Exception:
                pass

    # =====================================================================
    # 1. LEITURA DE MONITOR E JANELAS DO WINDOWS (NATIVO VIA CTYPES)
    # =====================================================================
    def _obter_area_util(self) -> tuple[int, int, int, int]:
        """Retorna (left, top, right, bottom) excluindo a barra de tarefas."""
        rect = RECT()
        if self._user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
        return 0, 0, self.hud.root.winfo_screenwidth(), self.hud.root.winfo_screenheight() - 48

    def _obter_rect_janela(self, hwnd) -> tuple[int, int, int, int] | None:
        """Obtém a borda visível real da janela (sem sombra invisível do Windows 10/11)."""
        if not hwnd or not self._user32.IsWindowVisible(hwnd) or self._user32.IsIconic(hwnd):
            return None
        rect = RECT()
        if self._dwmapi:
            res = self._dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(9),
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            if res == 0:
                return rect.left, rect.top, rect.right, rect.bottom
        if self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
        return None

    def _janela_eh_valida_para_sentar(self, hwnd) -> tuple[int, int, int, int] | None:
        if not hwnd:
            return None

        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == self._pid_atual:
            return None

        buf_classe = ctypes.create_unicode_buffer(256)
        self._user32.GetClassNameW(hwnd, buf_classe, 256)
        if buf_classe.value in CLASSES_IGNORADAS:
            return None

        bounds = self._obter_rect_janela(hwnd)
        if not bounds:
            return None

        left, top, right, bottom = bounds
        larg = right - left
        alt = bottom - top

        if larg < 220 or alt < 140 or top < 75:
            return None
        return bounds

    def _buscar_janela_ativa_valida(self):
        hwnd = self._user32.GetForegroundWindow()
        bounds = self._janela_eh_valida_para_sentar(hwnd)
        if bounds:
            return hwnd, bounds
        return None, None

    # =====================================================================
    # 2. RECORTE DE SPRITES (SEM BORDA ESCURA E COM PÉS ALINHADOS NA BASE)
    # =====================================================================
    def _obter_sprite_pet(self, nome_arquivo: str, espelhar: bool = False, efeito: str = "") -> ImageTk.PhotoImage | None:
        chave = (nome_arquivo.lower(), espelhar, efeito.lower())
        if chave in self._cache_sprites:
            return self._cache_sprites[chave]

        caminho = self.hud.sprites.obter_caminho(nome_arquivo)
        if not caminho:
            caminho = self.hud.sprites.obter_caminho("capri-neutral.png")
        if not caminho or not os.path.exists(caminho):
            return None

        try:
            rgba = Image.open(caminho).convert("RGBA")
            bbox = rgba.getbbox()
            if bbox:
                rgba = rgba.crop(bbox)

            if efeito:
                cam_ef = self.hud.sprites.obter_caminho(efeito)
                if cam_ef and os.path.exists(cam_ef):
                    ef = Image.open(cam_ef).convert("RGBA")
                    ef_bbox = ef.getbbox()
                    if ef_bbox:
                        ef = ef.crop(ef_bbox)
                    ef = ImageOps.contain(ef, (int(rgba.width * 0.40), int(rgba.height * 0.40)), Image.Resampling.LANCZOS)
                    rgba.alpha_composite(ef, (rgba.width - ef.width - 6, 6))

            if espelhar:
                rgba = ImageOps.mirror(rgba)

            rgba = ImageOps.contain(rgba, (self.largura - 12, self.altura - 12), Image.Resampling.LANCZOS)

            _, _, _, alfa = rgba.split()
            mascara = alfa.point([255 if p >= 115 else 0 for p in range(256)])

            fundo = Image.new("RGB", (self.largura, self.altura), self.CHROMA_RGB)
            px = (self.largura - rgba.width) // 2
            py = self.altura - rgba.height
            fundo.paste(rgba.convert("RGB"), (px, py), mascara)

            foto = ImageTk.PhotoImage(fundo)
            self._cache_sprites[chave] = foto
            return foto
        except Exception as e:
            print(f"[Aviso Sprite Modo Livre {nome_arquivo}]: {e}")
            return None

    def _escolher_sprite_atual(self) -> tuple[str, str]:
        agora = time.time()
        estado_hud = self.hud.estado_atual.upper()

        if agora < self.hud.ate_quando_headpat:
            return "capri-headpat.png", "capri-effect-heart.png"

        if agora < self.hud.ate_quando_forcado and self.hud.sprite_forcado:
            return self.hud.sprite_forcado, ""

        if "FALANDO" in estado_hud:
            nv = self.hud.nivel_voz
            if nv < 0.18:
                return "capri-neutral.png", ""
            elif nv < 0.42:
                return "capri-idle-mouth_small.png", ""
            elif nv < 0.68:
                return "capri-idle-mouth_round.png", ""
            return "capri-idle-mouth_wide.png", ""

        if "SPOTIFY" in estado_hud or agora < self.hud.ate_quando_musica:
            return "capri-music-window.png", ""

        if "OUVINDO" in estado_hud or "COMANDO" in estado_hud:
            if self.estado_fisica == "EMP_JANELA":
                return "capri-sit_edge-attentive.png", ""
            return "capri-lean_in-attentive.png", ""

        if any(k in estado_hud for k in ("TRANSCREVENDO", "PESQUISANDO", "PROCESSANDO", "ANALISANDO", "GERANDO")):
            if self.estado_fisica == "SENTADA":
                return "capri-sit_floor-thinking.png", ""
            return "capri-idle-thinking.png", ""

        if self.hud.pausada:
            if self.estado_fisica == "SENTADA":
                return "capri-sit_floor-sleepy.png", ""
            return "capri-idle-sleepy.png", ""

        if self.estado_fisica == "EMP_JANELA":
            return "capri-sit_edge-neutral.png", ""

        if self.estado_fisica == "SENTADA":
            return "capri-sit_floor-neutral.png", ""

        if self.estado_fisica == "ARRASTANDO":
            return "capri-crouch-attentive.png", ""

        if self.estado_fisica == "CAINDO":
            return "04-landing.png" if self.hud.sprites.obter_caminho("04-landing.png") else "capri-crouch-neutral.png", ""

        return "capri-neutral.png", ""

    # =====================================================================
    # 3. ATIVAR / DESATIVAR MODO LIVRE
    # =====================================================================
    def ativar(self):
        if self.ativo:
            return

        try:
            self.hud.root.update_idletasks()
            self.x = float(self.hud.root.winfo_x() + 140)
            self.y = float(self.hud.root.winfo_y() + 60)
        except Exception:
            self.x, self.y = 300.0, 200.0

        self.hud.root.withdraw()

        self.win = tk.Toplevel(self.hud.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=self.CHROMA_HEX)
        self.win.attributes("-transparentcolor", self.CHROMA_HEX)
        self.win.geometry(f"{self.largura}x{self.altura}+{int(self.x)}+{int(self.y)}")

        self.canvas = tk.Canvas(
            self.win,
            width=self.largura,
            height=self.altura,
            bg=self.CHROMA_HEX,
            highlightthickness=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self._iniciar_clique)
        self.canvas.bind("<B1-Motion>", self._arrastar_pet)
        self.canvas.bind("<ButtonRelease-1>", self._soltar_pet)
        self.canvas.bind("<Double-Button-1>", lambda e: self.abrir_mini_chat())
        self.canvas.bind("<Button-3>", self._abrir_menu_contexto)

        self.win.update_idletasks()
        self._garantir_sempre_no_topo()

        self.ativo = True
        self.estado_fisica = "CAINDO"
        self.vy = 0.0
        self.tempo_proxima_decisao = time.time() + 4.0

        self.hud._reposicionar_balao()
        self._loop_fisica()
        print("  [Modo Livre]: Capri escapou da caixa!")

    def desativar(self):
        if not self.ativo:
            return
        self.ativo = False
        self._fechar_mini_chat()

        try:
            if self.win and self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass
        self.win = None
        self.canvas = None
        self.hwnd_alvo = None

        self.hud.root.deiconify()
        self.hud.root.lift()
        self.hud._reposicionar_balao()
        print("  [Modo Livre]: Capri voltou para o HUD.")

    # =====================================================================
    # 4. INTERAÇÕES DO MOUSE, MENU DE CONTEXTO E MINI-CHAT FLUTUANTE
    # =====================================================================
    def _iniciar_clique(self, event):
        self._drag_offset_x = event.x
        self._drag_offset_y = event.y
        self._clique_inicio_x = event.x_root
        self._clique_inicio_y = event.y_root
        self._arrastou = False

    def _arrastar_pet(self, event):
        dx = abs(event.x_root - self._clique_inicio_x)
        dy = abs(event.y_root - self._clique_inicio_y)
        if dx > 5 or dy > 5:
            self._arrastou = True
            self.estado_fisica = "ARRASTANDO"
            self.hwnd_alvo = None
            self.vy = 0.0
            self.x = float(event.x_root - self._drag_offset_x)
            self.y = float(event.y_root - self._drag_offset_y)
            if self.win:
                self.win.geometry(f"+{int(self.x)}+{int(self.y)}")
            self.hud._reposicionar_balao()

    def _soltar_pet(self, event):
        if not self._arrastou:
            self.hud.ate_quando_headpat = time.time() + 2.2
            return

        hwnd, bounds = self._buscar_janela_ativa_valida()
        if hwnd and bounds:
            left, top, right, _ = bounds
            centro_x = self.x + (self.largura / 2)
            assento_y = self.y + self.altura - self.OFFSET_SENTAR_BORDA
            if left <= centro_x <= right and abs(assento_y - top) <= 65:
                self.hwnd_alvo = hwnd
                self.offset_x_janela = int(self.x - left)
                self.y = float(top - self.altura + self.OFFSET_SENTAR_BORDA)
                self.estado_fisica = "EMP_JANELA"
                self.tempo_proxima_decisao = time.time() + random.uniform(12.0, 22.0)
                self._garantir_sempre_no_topo()
                return

        self.estado_fisica = "CAINDO"
        self.vy = 0.0

    def _pular_para_janela_ativa(self):
        hwnd, bounds = self._buscar_janela_ativa_valida()
        if hwnd and bounds:
            left, top, right, _ = bounds
            self.hwnd_alvo = hwnd
            larg_disp = max(20, (right - left) - self.largura - 40)
            self.offset_x_janela = random.randint(25, min(larg_disp, 260))
            self.x = float(left + self.offset_x_janela)
            self.y = float(top - self.altura + self.OFFSET_SENTAR_BORDA)
            self.estado_fisica = "EMP_JANELA"
            self.tempo_proxima_decisao = time.time() + random.uniform(12.0, 24.0)
            self._garantir_sempre_no_topo()
        else:
            self.hwnd_alvo = None
            self.estado_fisica = "CAINDO"

    def _descer_para_barra(self):
        self.hwnd_alvo = None
        self.estado_fisica = "CAINDO"
        self.vy = 1.0

    def _abrir_menu_contexto(self, event):
        menu = tk.Menu(
            self.win,
            tearoff=0,
            bg="#170A10",
            fg="#F1F5F9",
            activebackground="#9B72FF",
            activeforeground="#FFFFFF",
            font=("Consolas", 9, "bold"),
        )
        menu.add_command(label="⌨  Comando Rápido / Tela", command=self.abrir_mini_chat)
        menu.add_command(label="💬  Abrir / Fechar Balão", command=self.hud.alternar_balao_fala)
        menu.add_separator()
        menu.add_command(label="🪟  Sentar na Janela Ativa", command=self._pular_para_janela_ativa)
        menu.add_command(label="🐾  Descer p/ Barra de Tarefas", command=self._descer_para_barra)
        menu.add_separator()
        menu.add_command(label="🎙  Mutar / Ativar Microfone", command=self.hud.alternar_pausa)
        menu.add_command(label="⚙  Configurações", command=self.hud.abrir_configuracoes)
        menu.add_command(label="📦  Voltar para a Caixa (HUD)", command=self.desativar)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _fechar_mini_chat(self):
        try:
            if self.mini_chat and self.mini_chat.winfo_exists():
                self.mini_chat.destroy()
        except Exception:
            pass
        self.mini_chat = None

    def abrir_mini_chat(self):
        self._fechar_mini_chat()
        if not (self.win and self.win.winfo_exists()):
            return

        mc = tk.Toplevel(self.win)
        mc.overrideredirect(True)
        mc.attributes("-topmost", True)
        mc.configure(bg=self.hud.BORDER_PINK)
        self.mini_chat = mc

        inner = tk.Frame(mc, bg=self.hud.BG_BAR, padx=8, pady=6)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        var_cmd = tk.StringVar()
        usar_tela = [False]

        entry = tk.Entry(
            inner,
            textvariable=var_cmd,
            bg=self.hud.BG_BAR,
            fg=self.hud.TEXT_WHITE,
            insertbackground=self.hud.ACCENT_CYAN,
            font=("Consolas", 10),
            relief="flat",
            width=28,
        )
        entry.pack(side="left", padx=(2, 6), ipady=3)

        btn_ver = tk.Button(
            inner, text="👁", fg=self.hud.TEXT_GRAY, bg="#28131E",
            font=("Consolas", 9, "bold"), relief="flat", cursor="hand2", padx=5
        )
        btn_ver.pack(side="left", padx=2)

        def _toggle_ver():
            usar_tela[0] = not usar_tela[0]
            btn_ver.configure(fg=self.hud.ACCENT_CYAN if usar_tela[0] else self.hud.TEXT_GRAY)
            mc.configure(bg=self.hud.ACCENT_CYAN if usar_tela[0] else self.hud.BORDER_PINK)

        btn_ver.configure(command=_toggle_ver)

        def _enviar(event=None):
            txt = var_cmd.get().strip()
            if not txt and not usar_tela[0]:
                self._fechar_mini_chat()
                return
            if not txt and usar_tela[0]:
                txt = "o que está acontecendo na tela?"

            if txt.lower().startswith(("/tela", "/ver")):
                usar_tela[0] = True
                txt = txt.split(" ", 1)[1].strip() if " " in txt else "o que está acontecendo na tela?"

            if usar_tela[0]:
                self.hud.enviar_comando_texto(f"{txt} olha minha tela", legenda_exibicao=f'Você [TELA]: "{txt}"')
            else:
                self.hud.enviar_comando_texto(txt)
            self._fechar_mini_chat()

        tk.Button(
            inner, text="↗", fg=self.hud.TEXT_PINK, bg="#28131E",
            font=("Consolas", 9, "bold"), relief="flat", cursor="hand2", padx=6, command=_enviar
        ).pack(side="left", padx=2)

        tk.Button(
            inner, text="✕", fg=self.hud.TEXT_GRAY, bg="#28131E",
            font=("Consolas", 8, "bold"), relief="flat", cursor="hand2", padx=5, command=self._fechar_mini_chat
        ).pack(side="left", padx=(2, 0))

        entry.bind("<Return>", _enviar)
        entry.bind("<KP_Enter>", _enviar)
        entry.bind("<Escape>", lambda e: self._fechar_mini_chat())

        mc.update_idletasks()
        tela_w = self.hud.root.winfo_screenwidth()
        mw = 340
        mh = 40
        mx = max(10, min(tela_w - mw - 10, int(self.x - 80)))
        my = max(10, int(self.y - mh - 8))
        mc.geometry(f"{mw}x{mh}+{mx}+{my}")
        entry.focus_force()

    # =====================================================================
    # 5. LOOP DE FÍSICA, COMPORTAMENTO AUTÔNOMO E ANIMAÇÃO (30 FPS)
    # =====================================================================
    def _loop_fisica(self):
        if not self.ativo or not self.hud.rodando or not (self.win and self.win.winfo_exists()):
            return

        try:
            agora = time.time()
            area_l, area_t, area_r, area_b = self._obter_area_util()
            chao_y = float(area_b - self.altura)
            limite_dir = float(area_r - self.largura)

            # Reafirma camada TOPMOST periodicamente (~0.5s) para nunca ficar atrás de jogos ou apps
            self._tick_topo += 1
            if self._tick_topo >= 15:
                self._tick_topo = 0
                self._garantir_sempre_no_topo()

            ocupada = any(k in self.hud.estado_atual.upper() for k in ("FALANDO", "OUVINDO", "PESQUISANDO", "ANALISANDO", "GERANDO"))

            if self.estado_fisica == "ARRASTANDO":
                pass

            elif self.estado_fisica == "CAINDO":
                self.vy = min(18.0, self.vy + 1.3)
                y_anterior_assento = self.y + self.altura - self.OFFSET_SENTAR_BORDA
                self.y += self.vy
                y_novo_assento = self.y + self.altura - self.OFFSET_SENTAR_BORDA

                hwnd, bounds = self._buscar_janela_ativa_valida()
                pousou_janela = False
                if hwnd and bounds:
                    left, top, right, _ = bounds
                    centro_x = self.x + (self.largura / 2)
                    if (left + 10) <= centro_x <= (right - 10) and y_anterior_assento <= top + 18 <= y_novo_assento + 18:
                        self.hwnd_alvo = hwnd
                        self.offset_x_janela = int(max(10, min(right - left - self.largura - 10, self.x - left)))
                        self.x = float(left + self.offset_x_janela)
                        self.y = float(top - self.altura + self.OFFSET_SENTAR_BORDA)
                        self.vy = 0.0
                        self.estado_fisica = "EMP_JANELA"
                        self.tempo_proxima_decisao = agora + random.uniform(10.0, 20.0)
                        self._garantir_sempre_no_topo()
                        pousou_janela = True

                if not pousou_janela and self.y >= chao_y:
                    self.y = chao_y
                    self.vy = 0.0
                    self.estado_fisica = "ANDANDO"
                    self.vx = random.choice([-2.2, 2.2])
                    self.olhando_esquerda = self.vx < 0
                    self.tempo_proxima_decisao = agora + random.uniform(5.0, 11.0)

            elif self.estado_fisica == "EMP_JANELA":
                bounds = self._janela_eh_valida_para_sentar(self.hwnd_alvo)
                if not bounds:
                    self.hwnd_alvo = None
                    self.estado_fisica = "CAINDO"
                    self.vy = 0.0
                else:
                    left, top, right, _ = bounds
                    max_off = max(10, (right - left) - self.largura - 10)
                    self.offset_x_janela = max(10, min(max_off, self.offset_x_janela))
                    self.x = float(left + self.offset_x_janela)
                    self.y = float(top - self.altura + self.OFFSET_SENTAR_BORDA)

                    if not ocupada and agora >= self.tempo_proxima_decisao:
                        if random.random() < 0.35:
                            self.hwnd_alvo = None
                            self.estado_fisica = "CAINDO"
                            self.vy = 0.5
                        else:
                            self.tempo_proxima_decisao = agora + random.uniform(10.0, 18.0)

            elif self.estado_fisica == "ANDANDO":
                self.y = chao_y
                if not ocupada and not self.hud.pausada:
                    self.x += self.vx
                    self.fase_passo += 0.32
                    if self.x <= area_l:
                        self.x = float(area_l)
                        self.vx = abs(self.vx)
                        self.olhando_esquerda = False
                    elif self.x >= limite_dir:
                        self.x = limite_dir
                        self.vx = -abs(self.vx)
                        self.olhando_esquerda = True

                    if agora >= self.tempo_proxima_decisao:
                        escolha = random.random()
                        if escolha < 0.40:
                            self.estado_fisica = "SENTADA"
                            self.tempo_proxima_decisao = agora + random.uniform(6.0, 14.0)
                        elif escolha < 0.72:
                            self._pular_para_janela_ativa()
                        else:
                            self.vx = -self.vx
                            self.olhando_esquerda = self.vx < 0
                            self.tempo_proxima_decisao = agora + random.uniform(4.0, 9.0)

            elif self.estado_fisica == "SENTADA":
                self.y = chao_y
                if not ocupada and not self.hud.pausada and agora >= self.tempo_proxima_decisao:
                    if random.random() < 0.45:
                        self._pular_para_janela_ativa()
                    else:
                        self.estado_fisica = "ANDANDO"
                        self.vx = random.choice([-2.2, 2.2])
                        self.olhando_esquerda = self.vx < 0
                        self.tempo_proxima_decisao = agora + random.uniform(5.0, 10.0)

            pulo_y = 0
            if self.estado_fisica == "ANDANDO" and not ocupada and not self.hud.pausada:
                pulo_y = -int(abs(math.sin(self.fase_passo)) * 5)

            self.win.geometry(f"+{int(self.x)}+{int(self.y) + pulo_y}")

            nome_sprite, efeito = self._escolher_sprite_atual()
            foto = self._obter_sprite_pet(nome_sprite, espelhar=self.olhando_esquerda, efeito=efeito)
            if foto and self.canvas is not None:
                self.canvas.delete("all")
                self.canvas.create_image(self.largura // 2, self.altura // 2, image=foto)

            if self.hud.balao_aberto:
                self.hud._reposicionar_balao()

        except Exception as e:
            print(f"[Aviso Loop Modo Livre]: {e}")

        if self.ativo and self.hud.rodando:
            self.win.after(33, self._loop_fisica)