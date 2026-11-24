import os
import time
import ctypes
from urllib.parse import quote

from core.logger import obter_logger
from audio.comandos import (
    PADROES_MUSICA_DIRETO,
    PALAVRAS_GENERICAS_MUSICA,
    VERBOS_PEDIR_MUSICA,
    COMANDOS_MIDIA,
    normalizar_frase,
)

log = obter_logger("spotify")

USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32


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
    scan = USER32.MapVirtualKeyW(vk, 0)
    USER32.keybd_event(vk, scan, 0x0002 if soltar else 0x0000, 0)


def _enviar_atalho(vk_mod: int, vk_tecla: int):
    _pressionar_tecla_fisica(vk_mod, False)
    time.sleep(0.025)
    _pressionar_tecla_fisica(vk_tecla, False)
    time.sleep(0.03)
    _pressionar_tecla_fisica(vk_tecla, True)
    time.sleep(0.025)
    _pressionar_tecla_fisica(vk_mod, True)


def _obter_executavel_janela(hwnd: int) -> str:
    pid = ctypes.c_ulong(0)
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h_proc = KERNEL32.OpenProcess(0x1000, False, pid.value)
    if not h_proc:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        tamanho = ctypes.c_ulong(512)
        if KERNEL32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(tamanho)):
            return os.path.basename(buf.value).lower()
    finally:
        KERNEL32.CloseHandle(h_proc)
    return ""


def encontrar_janela_spotify() -> int:
    janelas_spotify = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, _):
        if hwnd and USER32.IsWindowVisible(hwnd) and USER32.GetWindowTextLengthW(hwnd) > 0:
            rect = _RECT()
            USER32.GetWindowRect(hwnd, ctypes.byref(rect))
            if (rect.right - rect.left) > 300 and (rect.bottom - rect.top) > 300:
                if _obter_executavel_janela(hwnd) == "spotify.exe":
                    janelas_spotify.append(hwnd)
        return True

    USER32.EnumWindows(WNDENUMPROC(_callback), 0)
    return janelas_spotify[0] if janelas_spotify else 0


def _forcar_foco_janela(hwnd: int):
    try:
        if USER32.IsIconic(hwnd):
            USER32.ShowWindow(hwnd, 9)
            time.sleep(0.18)

        _pressionar_tecla_fisica(0x12, False)
        USER32.BringWindowToTop(hwnd)
        USER32.SetForegroundWindow(hwnd)
        USER32.SwitchToThisWindow(hwnd, True)
        _pressionar_tecla_fisica(0x12, True)
        time.sleep(0.18)
    except Exception as e:
        log.warning("Aviso foco Spotify: %s", e)


def tocar_musica_spotify(nome_musica: str) -> str:
    limpo = (nome_musica or "").strip()
    if not limpo:
        return "Qual música você quer que eu coloque no Spotify?"

    uri_busca = f"spotify:search:{quote(limpo)}"
    ja_estava_aberto = encontrar_janela_spotify() != 0

    try:
        os.startfile(uri_busca)
    except Exception as e:
        log.warning("Falha ao abrir URI do Spotify: %s", e)
        return f"Não encontrei o aplicativo do Spotify instalado: {str(e)}"

    if ja_estava_aberto:
        time.sleep(1.6)
    else:
        for _ in range(10):
            if encontrar_janela_spotify():
                break
            time.sleep(0.5)
        time.sleep(2.2)

    hwnd_sp = encontrar_janela_spotify()
    if hwnd_sp:
        try:
            _forcar_foco_janela(hwnd_sp)
            rect = _RECT()
            USER32.GetWindowRect(hwnd_sp, ctypes.byref(rect))
            if (rect.right - rect.left) > 400 and (rect.bottom - rect.top) > 300:
                pos_original = _POINT()
                USER32.GetCursorPos(ctypes.byref(pos_original))

                USER32.SetCursorPos(rect.left + 430, rect.top + 150)
                time.sleep(0.04)
                USER32.mouse_event(0x0002, 0, 0, 0, 0)
                USER32.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.08)
                USER32.SetCursorPos(pos_original.x, pos_original.y)

                for _ in range(2):
                    _pressionar_tecla_fisica(0x09, False)
                    _pressionar_tecla_fisica(0x09, True)
                    time.sleep(0.07)

                _pressionar_tecla_fisica(0x0D, False)
                time.sleep(0.04)
                _pressionar_tecla_fisica(0x0D, True)
        except Exception as e:
            log.warning("Aviso ao dar play no Spotify: %s", e)

    return (
        f"Trocando para {limpo} no Spotify."
        if ja_estava_aberto
        else f"Colocando {limpo} para tocar no Spotify."
    )


def ajustar_volume_spotify(acao: str, nivel_porcentagem: int = -1) -> str:
    janela_anterior = USER32.GetForegroundWindow()
    hwnd_sp = encontrar_janela_spotify()
    VK_CONTROL, VK_UP, VK_DOWN = 0x11, 0x26, 0x28

    if hwnd_sp:
        try:
            _forcar_foco_janela(hwnd_sp)
            if nivel_porcentagem >= 0:
                nivel = max(0, min(100, nivel_porcentagem))
                for _ in range(18):
                    _enviar_atalho(VK_CONTROL, VK_DOWN)
                    time.sleep(0.012)
                for _ in range(round((nivel / 100.0) * 16)):
                    _enviar_atalho(VK_CONTROL, VK_UP)
                    time.sleep(0.012)
                msg = f"Volume do Spotify em {nivel} por cento."
            elif acao == "aumentar":
                for _ in range(5):
                    _enviar_atalho(VK_CONTROL, VK_UP)
                    time.sleep(0.015)
                msg = "Aumentando o volume do Spotify."
            else:
                for _ in range(5):
                    _enviar_atalho(VK_CONTROL, VK_DOWN)
                    time.sleep(0.015)
                msg = "Abaixando o volume do Spotify."

            if janela_anterior and janela_anterior != hwnd_sp:
                time.sleep(0.06)
                _forcar_foco_janela(janela_anterior)
            return msg
        except Exception as e:
            log.warning("Aviso volume Spotify: %s", e)

    tecla_win = 0xAF if acao == "aumentar" else 0xAE
    for _ in range(5):
        USER32.keybd_event(tecla_win, 0, 1, 0)
        USER32.keybd_event(tecla_win, 0, 3, 0)
    return "Volume ajustado."


def controlar_midia_windows(acao: str) -> str:
    mapa = {
        "pausar": (0xB3, "Reprodução pausada."),
        "continuar": (0xB3, "Retomando a música."),
        "proxima": (0xB0, "Próxima faixa."),
        "anterior": (0xB1, "Faixa anterior."),
    }
    acao_limpa = acao.lower().strip()
    if acao_limpa not in mapa:
        return "Comando de mídia não reconhecido."
    tecla_vk, msg = mapa[acao_limpa]
    USER32.keybd_event(tecla_vk, 0, 1, 0)
    USER32.keybd_event(tecla_vk, 0, 3, 0)
    return msg


def detectar_pedido_musica(comando: str) -> tuple[bool, str]:
    cmd = normalizar_frase(comando)

    # Ignora se for comando de pausar, continuar, pular, voltar ou volume
    for lista_midia in COMANDOS_MIDIA.values():
        if any(f in cmd for f in lista_midia):
            return False, ""
    if "volume" in cmd:
        return False, ""

    gatilhos_busca = ("música", "musica", "som", "spotify") + VERBOS_PEDIR_MUSICA
    if any(p in cmd for p in gatilhos_busca):
        for regex in PADROES_MUSICA_DIRETO:
            m = regex.search(cmd)
            if m:
                nome = m.group(1).strip(" .,!?")
                if nome and nome not in PALAVRAS_GENERICAS_MUSICA:
                    return True, nome

    if any(p in cmd for p in ("música", "musica", "som")) and any(
        v in cmd for v in VERBOS_PEDIR_MUSICA
    ):
        return True, ""

    return False, ""