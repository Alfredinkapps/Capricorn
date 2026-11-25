import io
import os
import time
import ctypes
import threading
from ctypes import wintypes
from typing import Any

import mss
from PIL import Image
from google.genai import types

from core.logger import obter_logger
from audio.comandos import remover_acentos

log = obter_logger("visao")

MODELO_VISAO = "gemini-3.5-flash"
MODELOS_VISAO_FALLBACK = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]

_CLASSES_IGNORADAS_VISAO = {
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Progman",
    "WorkerW",
    "NotifyIconOverflowWindow",
    "Windows.UI.Core.CoreWindow",
    "TaskListThumbnailWnd",
    "MultitaskingViewFrame",
}

_TERMOS_FOCO_JANELA = (
    "codigo", "erro", "bug", "terminal", "console", "traceback", "pylance",
    "vscode", "vs code", "funcao", "classe", "corrige", "corrija", "completa",
    "complete", "le esse", "ler esse", "janela", "programa", "script",
)


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def listar_monitores() -> list[dict[str, Any]]:
    """Lista todos os monitores físicos disponíveis (índice 1-based compatível com mss)."""
    monitores: list[dict[str, Any]] = []
    try:
        with mss.mss() as sct:
            for idx, mon in enumerate(sct.monitors[1:], start=1):
                w = int(mon["width"])
                h = int(mon["height"])
                monitores.append({
                    "indice": idx,
                    "width": w,
                    "height": h,
                    "rotulo": f"Monitor {idx} ({w}x{h})",
                })
    except Exception as e:
        log.warning("Falha ao listar monitores: %s", e)

    if not monitores:
        monitores.append({"indice": 1, "width": 1920, "height": 1080, "rotulo": "Monitor 1 (Padrão)"})
    return monitores


def _obter_retangulo_janela_visivel(hwnd: int, user32: Any, dwmapi: Any) -> tuple[int, int, int, int] | None:
    """Retorna (left, top, right, bottom) reais da janela sem sombra invisível do Windows."""
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None

    # Ignora janelas UWP ocultas em segundo plano (DWMWA_CLOAKED = 14)
    if dwmapi is not None:
        cloaked = wintypes.DWORD(0)
        res_cloak = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(14),
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        if res_cloak == 0 and cloaked.value != 0:
            return None

    rect = _RECT()
    if dwmapi is not None:
        res = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(9),
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if res == 0:
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)

    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return None


def _janela_externa_valida(hwnd: int, pid_capri: int, user32: Any, dwmapi: Any) -> dict[str, int] | None:
    if not hwnd:
        return None

    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == pid_capri:
        return None

    buf_classe = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf_classe, 256)
    if buf_classe.value in _CLASSES_IGNORADAS_VISAO:
        return None

    if user32.GetWindowTextLengthW(hwnd) <= 0:
        return None

    bounds = _obter_retangulo_janela_visivel(hwnd, user32, dwmapi)
    if bounds is None:
        return None

    left, top, right, bottom = bounds
    larg = right - left
    alt = bottom - top
    if larg < 300 or alt < 200:
        return None

    return {"left": left, "top": top, "width": larg, "height": alt}


def _obter_regiao_janela_ativa() -> dict[str, int] | None:
    """
    Retorna a região da janela ativa externa à Capri.
    Se o usuário acabou de clicar no HUD da Capri para digitar, pega a janela logo atrás em Z-order.
    """
    try:
        user32 = ctypes.windll.user32
        try:
            dwmapi = ctypes.windll.dwmapi
        except Exception:
            dwmapi = None

        pid_capri = os.getpid()

        # 1. Tenta primeiro a janela em foco direto (caso o comando tenha vindo por voz)
        hwnd_foco = int(user32.GetForegroundWindow())
        regiao = _janela_externa_valida(hwnd_foco, pid_capri, user32, dwmapi)
        if regiao is not None:
            return regiao

        # 2. Se o foco está no CAPRI HUD, percorre janelas em Z-order (da frente para trás)
        encontrada: list[dict[str, int]] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def _callback(hwnd: int, _lparam: int) -> bool:
            cand = _janela_externa_valida(hwnd, pid_capri, user32, dwmapi)
            if cand is not None:
                encontrada.append(cand)
                return False  # Para na primeira janela externa no topo
            return True

        user32.EnumWindows(WNDENUMPROC(_callback), 0)
        return encontrada[0] if encontrada else None
    except Exception as e:
        log.debug("Falha ao localizar janela ativa para captura: %s", e)
        return None


def _recortar_para_tela_virtual(regiao: dict[str, int], virtual: dict[str, Any]) -> dict[str, int] | None:
    """Garante que o retângulo da janela fique dentro da área virtual capturável pelo mss."""
    v_left = int(virtual["left"])
    v_top = int(virtual["top"])
    v_right = v_left + int(virtual["width"])
    v_bottom = v_top + int(virtual["height"])

    left = max(v_left, regiao["left"])
    top = max(v_top, regiao["top"])
    right = min(v_right, regiao["left"] + regiao["width"])
    bottom = min(v_bottom, regiao["top"] + regiao["height"])

    larg = right - left
    alt = bottom - top
    if larg < 200 or alt < 150:
        return None
    return {"left": left, "top": top, "width": larg, "height": alt}


def capturar_tela_jpeg(
    largura_max: int = 1024,
    qualidade: int = 75,
    monitor_idx: int = 1,
    apenas_janela_ativa: bool = False,
) -> bytes:
    """Captura a janela ativa ou o monitor selecionado direto na RAM em JPEG leve."""
    with mss.mss() as sct:
        alvo: dict[str, Any] | None = None
        if apenas_janela_ativa:
            reg_janela = _obter_regiao_janela_ativa()
            if reg_janela is not None:
                alvo = _recortar_para_tela_virtual(reg_janela, sct.monitors[0])

        if alvo is None:
            indice = monitor_idx if 1 <= monitor_idx < len(sct.monitors) else 1
            if indice >= len(sct.monitors):
                indice = 0
            alvo = sct.monitors[indice]

        captura = sct.grab(alvo)
        img = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")

    if img.width > largura_max:
        proporcao = largura_max / float(img.width)
        nova_altura = max(1, int(img.height * proporcao))
        img = img.resize((largura_max, nova_altura), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=qualidade, optimize=True)
    return buffer.getvalue()


def _deve_focar_janela_ativa(pedido_usuario: str, modo_captura: str) -> bool:
    modo = (modo_captura or "auto").strip().lower()
    if modo == "janela_ativa":
        return True
    if modo == "monitor_inteiro":
        return False
    pedido_limpo = remover_acentos((pedido_usuario or "").lower())
    return any(termo in pedido_limpo for termo in _TERMOS_FOCO_JANELA)


def analisar_tela_sob_demanda(
    client: Any,
    pedido_usuario: str,
    monitor_idx: int = 1,
    modo_captura: str = "auto",
) -> str:
    """
    Modo Sob Demanda: lê a janela ativa ou o monitor escolhido em boa nitidez
    para ajudar com código, explicar erros ou responder perguntas sobre a tela.
    """
    if client is None:
        return "Configure sua chave da API do Gemini antes de usar a visão de tela."

    focar_janela = _deve_focar_janela_ativa(pedido_usuario, modo_captura)
    # Em modo janela ativa a área já é recortada, permitindo 1152px leves e muito nítidos
    largura_alvo = 1152 if focar_janela else 1024

    try:
        img_bytes = capturar_tela_jpeg(
            largura_max=largura_alvo,
            qualidade=75,
            monitor_idx=monitor_idx,
            apenas_janela_ativa=focar_janela,
        )
        parte_imagem = types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
        log.info(
            "Captura de visão pronta (modo=%s, monitor=%d, %.1f KB).",
            "janela_ativa" if focar_janela else "monitor_inteiro",
            monitor_idx,
            len(img_bytes) / 1024.0,
        )
    except Exception as e:
        log.warning("Falha ao capturar tela para visão sob demanda: %s", e)
        return "Não consegui capturar a imagem da sua tela agora."

    prompt = (
        "Você é a Capri, uma assistente virtual de PC com personalidade cyberpunk, "
        "direta, inteligente e parceira. Ignore qualquer janela pequena chamada 'CAPRI HUD' na tela.\n"
        f"Pedido do usuário: \"{pedido_usuario}\"\n"
        "Instruções:\n"
        "- Se houver código na tela (VS Code, Dev-C++, terminal, etc.), leia o trecho visível "
        "e sugira o complemento ou correção de forma clara e objetiva.\n"
        "- Seja breve o suficiente para fazer sentido tanto lendo no card quanto ouvindo por voz."
    )

    ultimo_erro: Exception | None = None
    for modelo in MODELOS_VISAO_FALLBACK:
        try:
            resp = client.models.generate_content(
                model=modelo,
                contents=[prompt, parte_imagem],
            )
            texto = (getattr(resp, "text", "") or "").strip()
            if texto:
                log.info("Visão sob demanda respondida via %s", modelo)
                return texto
        except Exception as e:
            ultimo_erro = e
            log.warning("Erro Visão Sob Demanda (%s): %s", modelo, e)

    if ultimo_erro and "504" in str(ultimo_erro):
        return (
            "O servidor do Gemini demorou demais para responder a imagem (erro 504). "
            "Tente novamente em alguns segundos."
        )
    return "Tive um problema ao analisar a imagem da sua tela."


class ObservadorTela:
    """
    Modo Co-Piloto para jogos (futebol, Forza, Assetto Corsa, etc.).
    Captura 2 quadros espaçados para detectar eventos reais e só comenta quando vale a pena.
    """

    def __init__(
        self,
        hud: Any,
        estado_compartilhado: dict[str, Any],
        lock: threading.Lock,
        funcao_falar: Any,
    ):
        self.hud = hud
        self.estado = estado_compartilhado
        self.lock = lock
        self.funcao_falar = funcao_falar

        self.ativo = False
        self.thread: threading.Thread | None = None
        self.ultimo_comentario_ts = 0.0
        self.cooldown_segundos = 14.0
        self.ultimo_resumo = ""

    def iniciar(self) -> None:
        if self.ativo:
            return
        self.ativo = True
        self.thread = threading.Thread(target=self._loop_observador, daemon=True)
        self.thread.start()
        log.info("Modo Observador ATIVADO.")

    def parar(self) -> None:
        if not self.ativo:
            return
        self.ativo = False
        log.info("Modo Observador DESATIVADO.")

    def _loop_observador(self) -> None:
        while self.ativo and self.hud.rodando:
            try:
                client = self.estado.get("client")
                if not client or not self.estado.get("pronto"):
                    time.sleep(2.0)
                    continue

                if time.time() - self.ultimo_comentario_ts < self.cooldown_segundos:
                    time.sleep(1.0)
                    continue

                monitor_idx = int(self.hud.config.get("monitor_visao", 1) or 1)
                frame_antes = capturar_tela_jpeg(
                    largura_max=768, qualidade=65, monitor_idx=monitor_idx
                )
                time.sleep(2.5)
                if not self.ativo or not self.hud.rodando:
                    break
                frame_depois = capturar_tela_jpeg(
                    largura_max=768, qualidade=65, monitor_idx=monitor_idx
                )

                comentario = self._avaliar_jogada(client, frame_antes, frame_depois)

                if comentario and "SILENCIO" not in comentario.upper():
                    self.ultimo_comentario_ts = time.time()
                    self.ultimo_resumo = comentario

                    palavras_hype = (
                        "gol", "golaço", "primeiro", "1º", "vitória", "venceu", "ganhou", "pódio"
                    )
                    if any(p in comentario.lower() for p in palavras_hype):
                        self.hud.acionar_sprite_temporario("capri-idle-happy.png", duracao=4.0)

                    if self.lock.acquire(blocking=False):
                        try:
                            self.funcao_falar(self.hud, comentario, usar_cache=False)
                            estado_pos = "MIC SILENCIADO" if self.hud.pausada else "EM ESPERA"
                            self.hud.atualizar_estado(estado_pos, self.hud.BORDER_PINK)
                        finally:
                            self.lock.release()

                time.sleep(2.5)
            except Exception as e:
                log.warning("Aviso Observador de Tela: %s", e)
                time.sleep(4.0)

    def _avaliar_jogada(self, client: Any, frame_1: bytes, frame_2: bytes) -> str:
        p1 = types.Part.from_bytes(data=frame_1, mime_type="image/jpeg")
        p2 = types.Part.from_bytes(data=frame_2, mime_type="image/jpeg")

        prompt = (
            "Você é a Capri, assistente cyberpunk assistindo a tela do usuário em tempo real. "
            "Você recebeu 2 capturas seguidas (2.5 segundos de diferença). Ignore a janela 'CAPRI HUD'.\n"
            f"Seu último comentário foi: \"{self.ultimo_resumo}\". NÃO repita o mesmo assunto.\n\n"
            "Regras estritas de reação:\n"
            "1. JOGO DE FUTEBOL: Se acabou de sair um GOL (comemoração, placar subiu, replay de gol) "
            "ou uma defesa absurda, comemore empolgada!\n"
            "2. JOGO DE CORRIDA (Forza, Assetto Corsa, etc.): Observe o velocímetro e a posição (POS). "
            "Comente se estiver em altíssima velocidade (acima de 260 km/h), fazendo uma ultrapassagem "
            "ou se acabou de chegar/assumir o 1º lugar.\n"
            "3. QUALQUER OUTRA COISA: Se for apenas menu, tela estática, navegação normal ou jogada comum "
            "sem nada marcante, responda EXATAMENTE com a palavra: SILENCIO\n\n"
            "Se houver um evento real, responda em português do Brasil com NO MÁXIMO 1 frase curta e natural."
        )

        for modelo in MODELOS_VISAO_FALLBACK:
            try:
                resp = client.models.generate_content(
                    model=modelo,
                    contents=[prompt, p1, p2],
                )
                texto = (getattr(resp, "text", "") or "").strip()
                if texto:
                    return texto
            except Exception as e:
                log.warning("Aviso Observador (%s): %s", modelo, e)

        return "SILENCIO"