import ctypes
import threading
from ctypes import wintypes
from collections.abc import Callable

from core.logger import obter_logger

log = obter_logger("atalhos")

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000

VK_SPACE = 0x20
VK_C = 0x43

ID_HOTKEY_FALAR = 101
ID_HOTKEY_CHAT = 102


class GerenciadorAtalhosGlobais:
    """
    Escuta atalhos globais do Windows via Win32 RegisterHotKey (zero dependências externas):
    - Alt + Espaço: ativa escuta de voz imediata (Push-to-Talk sem dizer 'Capri').
    - Alt + C: traz o HUD ou Mini-Chat para frente e foca a barra de texto.
    """

    def __init__(
        self,
        ao_pressionar_falar: Callable[[], None],
        ao_pressionar_chat: Callable[[], None],
    ):
        self._ao_falar = ao_pressionar_falar
        self._ao_chat = ao_pressionar_chat
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._rodando = False

    def iniciar(self) -> None:
        if self._rodando:
            return
        self._rodando = True
        self._thread = threading.Thread(target=self._loop_win32, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        if not self._rodando:
            return
        self._rodando = False
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass

    def _loop_win32(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = int(kernel32.GetCurrentThreadId())

        ok_falar = bool(user32.RegisterHotKey(None, ID_HOTKEY_FALAR, MOD_ALT | MOD_NOREPEAT, VK_SPACE))
        ok_chat = bool(user32.RegisterHotKey(None, ID_HOTKEY_CHAT, MOD_ALT | MOD_NOREPEAT, VK_C))

        if ok_falar or ok_chat:
            log.info(
                "Atalhos globais registrados (Alt+Espaço=%s, Alt+C=%s).",
                "OK" if ok_falar else "OCUPADO",
                "OK" if ok_chat else "OCUPADO",
            )
        else:
            log.warning("Não foi possível registrar os atalhos globais Alt+Espaço / Alt+C.")
            self._rodando = False
            return

        msg = wintypes.MSG()
        try:
            while self._rodando:
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res <= 0:
                    break
                if msg.message == WM_HOTKEY:
                    if msg.wParam == ID_HOTKEY_FALAR:
                        try:
                            self._ao_falar()
                        except Exception as e:
                            log.warning("Erro callback Alt+Espaço: %s", e)
                    elif msg.wParam == ID_HOTKEY_CHAT:
                        try:
                            self._ao_chat()
                        except Exception as e:
                            log.warning("Erro callback Alt+C: %s", e)
        finally:
            if ok_falar:
                user32.UnregisterHotKey(None, ID_HOTKEY_FALAR)
            if ok_chat:
                user32.UnregisterHotKey(None, ID_HOTKEY_CHAT)
            self._rodando = False