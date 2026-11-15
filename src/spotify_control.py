import os
import re
import time
import ctypes
from urllib.parse import quote


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _pressionar_tecla_fisica(vk: int, soltar: bool = False):
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    flags = 0x0002 if soltar else 0x0000
    ctypes.windll.user32.keybd_event(vk, scan, flags, 0)


def _enviar_atalho(vk_mod: int, vk_tecla: int):
    _pressionar_tecla_fisica(vk_mod, soltar=False)
    time.sleep(0.03)
    _pressionar_tecla_fisica(vk_tecla, soltar=False)
    time.sleep(0.04)
    _pressionar_tecla_fisica(vk_tecla, soltar=True)
    time.sleep(0.03)
    _pressionar_tecla_fisica(vk_mod, soltar=True)


def _obter_executavel_janela(hwnd: int) -> str:
    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h_proc = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
    if not h_proc:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        tamanho = ctypes.c_ulong(512)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(tamanho)):
            return os.path.basename(buf.value).lower()
    finally:
        ctypes.windll.kernel32.CloseHandle(h_proc)
    return ""


def encontrar_janela_spotify() -> int:
    janelas_spotify = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, lParam):
        if hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
            if ctypes.windll.user32.GetWindowTextLengthW(hwnd) > 0:
                rect = _RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                if (rect.right - rect.left) > 300 and (rect.bottom - rect.top) > 300:
                    if _obter_executavel_janela(hwnd) == "spotify.exe":
                        janelas_spotify.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_callback), 0)
    return janelas_spotify[0] if janelas_spotify else 0


def _forcar_foco_janela(hwnd: int):
    try:
        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            time.sleep(0.20)

        _pressionar_tecla_fisica(0x12, soltar=False)
        ctypes.windll.user32.BringWindowToTop(hwnd)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        _pressionar_tecla_fisica(0x12, soltar=True)
        time.sleep(0.20)
    except Exception as e:
        print(f"[Aviso foco Spotify]: {e}")


def tocar_musica_spotify(nome_musica: str) -> str:
    limpo = nome_musica.strip()
    uri_busca = f"spotify:search:{quote(limpo)}"
    ja_estava_aberto = encontrar_janela_spotify() != 0

    try:
        os.startfile(uri_busca)
    except Exception as e:
        return f"Não consegui encontrar o aplicativo do Spotify instalado: {str(e)}"

    if ja_estava_aberto:
        time.sleep(1.8)
    else:
        for _ in range(10):
            if encontrar_janela_spotify():
                break
            time.sleep(0.5)
        time.sleep(2.5)

    hwnd_sp = encontrar_janela_spotify()
    if hwnd_sp:
        try:
            _forcar_foco_janela(hwnd_sp)
            rect = _RECT()
            ctypes.windll.user32.GetWindowRect(hwnd_sp, ctypes.byref(rect))
            if (rect.right - rect.left) > 400 and (rect.bottom - rect.top) > 300:
                pos_original = _POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pos_original))

                ctypes.windll.user32.SetCursorPos(rect.left + 430, rect.top + 150)
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.10)
                ctypes.windll.user32.SetCursorPos(pos_original.x, pos_original.y)

                for _ in range(2):
                    _pressionar_tecla_fisica(0x09, soltar=False)
                    _pressionar_tecla_fisica(0x09, soltar=True)
                    time.sleep(0.08)

                _pressionar_tecla_fisica(0x0D, soltar=False)
                time.sleep(0.05)
                _pressionar_tecla_fisica(0x0D, soltar=True)
        except Exception as e:
            print(f"[Aviso ao dar play no Spotify]: {e}")

    return f"Trocando para {limpo} no Spotify." if ja_estava_aberto else f"Colocando {limpo} para tocar no Spotify."


def ajustar_volume_spotify(acao: str, nivel_porcentagem: int = -1) -> str:
    janela_anterior = ctypes.windll.user32.GetForegroundWindow()
    hwnd_sp = encontrar_janela_spotify()
    VK_CONTROL, VK_UP, VK_DOWN = 0x11, 0x26, 0x28

    if hwnd_sp:
        try:
            _forcar_foco_janela(hwnd_sp)
            if nivel_porcentagem >= 0:
                nivel = max(0, min(100, nivel_porcentagem))
                for _ in range(18):
                    _enviar_atalho(VK_CONTROL, VK_DOWN)
                    time.sleep(0.015)
                for _ in range(round((nivel / 100.0) * 16)):
                    _enviar_atalho(VK_CONTROL, VK_UP)
                    time.sleep(0.015)
                msg = f"Volume do Spotify ajustado para {nivel} por cento."
            elif acao == "aumentar":
                for _ in range(5):
                    _enviar_atalho(VK_CONTROL, VK_UP)
                    time.sleep(0.02)
                msg = "Aumentando o volume do Spotify."
            else:
                for _ in range(5):
                    _enviar_atalho(VK_CONTROL, VK_DOWN)
                    time.sleep(0.02)
                msg = "Abaixando o volume do Spotify."

            if janela_anterior and janela_anterior != hwnd_sp:
                time.sleep(0.08)
                _forcar_foco_janela(janela_anterior)
            return msg
        except Exception as e:
            print(f"[Aviso volume Spotify]: {e}")

    tecla_win = 0xAF if acao == "aumentar" else 0xAE
    for _ in range(5):
        ctypes.windll.user32.keybd_event(tecla_win, 0, 1, 0)
        ctypes.windll.user32.keybd_event(tecla_win, 0, 3, 0)
    return "Volume ajustado."


def controlar_midia_windows(acao: str) -> str:
    mapa = {
        "pausar": (0xB3, "Reprodução pausada no Spotify."),
        "continuar": (0xB3, "Retomando a música no Spotify."),
        "proxima": (0xB0, "Pulando para a próxima faixa."),
        "anterior": (0xB1, "Voltando para a faixa anterior."),
    }
    if acao.lower().strip() not in mapa:
        return "Comando de mídia não reconhecido."
    tecla_vk, msg = mapa[acao.lower().strip()]
    ctypes.windll.user32.keybd_event(tecla_vk, 0, 1, 0)
    ctypes.windll.user32.keybd_event(tecla_vk, 0, 3, 0)
    return msg


def detectar_pedido_musica(comando: str) -> tuple[bool, str]:
    if any(p in comando for p in ["pausar", "pausa", "pause", "parar", "para a música", "continuar", "continua", "retomar", "próxima", "proxima", "anterior", "volume"]):
        return False, ""

    padroes_diretos = [
        r"(?:trocar|troque|troca|mudar|mude|muda)\s+(?:a\s+|de\s+)?m[úu]sica\s+(?:para|pra|por)\s+(.+)",
        r"(?:colocar|coloque|coloca|tocar|toque|toca|botar|bota|bote)\s+(?:a\s+)?m[úu]sica\s+(.+)"
    ]
    for padrao in padroes_diretos:
        m = re.search(padrao, comando)
        if m:
            nome = m.group(1).strip()
            if nome and nome not in ["uma", "outra", "alguma", "aí", "ai", "no spotify"]:
                return True, nome

    verbos_musica = ["coloque", "coloca", "colocar", "toque", "toca", "tocar", "bota", "bote", "botar", "troque", "troca", "trocar", "mude", "muda", "mudar", "outra"]
    if ("música" in comando or "musica" in comando) and any(v in comando for v in verbos_musica):
        return True, ""

    return False, ""