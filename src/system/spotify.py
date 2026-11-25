import os
import time
import ctypes
from typing import Any

from core.config import PASTA_DATA, carregar_configuracoes
from core.logger import obter_logger
from audio.comandos import (
    PADROES_MUSICA_DIRETO,
    PALAVRAS_GENERICAS_MUSICA,
    VERBOS_PEDIR_MUSICA,
    COMANDOS_MIDIA,
    normalizar_frase,
)

log = obter_logger("spotify")

try:
    import spotipy  # type: ignore[import-not-found]
    from spotipy.oauth2 import SpotifyPKCE  # type: ignore[import-not-found]
    SPOTIPY_DISPONIVEL = True
except ImportError:
    spotipy = None
    SpotifyPKCE = None
    SPOTIPY_DISPONIVEL = False

SPOTIFY_REDIRECT_URI_PADRAO = "http://127.0.0.1:8888/callback"
SPOTIFY_SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)

USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32

_CLIENTE_SPOTIFY: Any = None
_ULTIMO_CLIENT_ID = ""
_ULTIMO_REDIRECT_URI = ""


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _configurar_win32_clipboard() -> None:
    """Tipagem explícita 64-bit para manipulação segura da área de transferência do Windows."""
    try:
        USER32.OpenClipboard.argtypes = [ctypes.c_void_p]
        USER32.OpenClipboard.restype = ctypes.c_bool
        USER32.CloseClipboard.argtypes = []
        USER32.CloseClipboard.restype = ctypes.c_bool
        USER32.EmptyClipboard.argtypes = []
        USER32.EmptyClipboard.restype = ctypes.c_bool
        USER32.GetClipboardData.argtypes = [ctypes.c_uint]
        USER32.GetClipboardData.restype = ctypes.c_void_p
        USER32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        USER32.SetClipboardData.restype = ctypes.c_void_p

        KERNEL32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        KERNEL32.GlobalAlloc.restype = ctypes.c_void_p
        KERNEL32.GlobalLock.argtypes = [ctypes.c_void_p]
        KERNEL32.GlobalLock.restype = ctypes.c_void_p
        KERNEL32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        KERNEL32.GlobalUnlock.restype = ctypes.c_bool
        KERNEL32.GlobalFree.argtypes = [ctypes.c_void_p]
        KERNEL32.GlobalFree.restype = ctypes.c_void_p
    except Exception:
        pass


_configurar_win32_clipboard()


def _ler_clipboard_texto() -> str | None:
    CF_UNICODETEXT = 13
    if not USER32.OpenClipboard(None):
        return None
    try:
        handle = USER32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = KERNEL32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            KERNEL32.GlobalUnlock(handle)
    except Exception:
        return None
    finally:
        USER32.CloseClipboard()


def _escrever_clipboard_texto(texto: str) -> bool:
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    dados = texto.encode("utf-16-le") + b"\x00\x00"

    if not USER32.OpenClipboard(None):
        return False
    h_mem = None
    try:
        USER32.EmptyClipboard()
        h_mem = KERNEL32.GlobalAlloc(GMEM_MOVEABLE, len(dados))
        if not h_mem:
            return False
        ptr = KERNEL32.GlobalLock(h_mem)
        if not ptr:
            KERNEL32.GlobalFree(h_mem)
            return False
        try:
            ctypes.memmove(ptr, dados, len(dados))
        finally:
            KERNEL32.GlobalUnlock(h_mem)

        if not USER32.SetClipboardData(CF_UNICODETEXT, h_mem):
            KERNEL32.GlobalFree(h_mem)
            return False
        h_mem = None  # Propriedade transferida para o Windows
        return True
    except Exception as e:
        log.warning("Falha ao escrever na área de transferência: %s", e)
        if h_mem:
            KERNEL32.GlobalFree(h_mem)
        return False
    finally:
        USER32.CloseClipboard()


def _pressionar_tecla_fisica(vk: int, soltar: bool = False) -> None:
    scan = USER32.MapVirtualKeyW(vk, 0)
    USER32.keybd_event(vk, scan, 0x0002 if soltar else 0x0000, 0)


def _enviar_atalho(vk_mod: int, vk_tecla: int) -> None:
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
    janelas_spotify: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd: int, _lparam: int) -> bool:
        if hwnd and USER32.IsWindowVisible(hwnd) and USER32.GetWindowTextLengthW(hwnd) > 0:
            rect = _RECT()
            USER32.GetWindowRect(hwnd, ctypes.byref(rect))
            if (rect.right - rect.left) > 300 and (rect.bottom - rect.top) > 300:
                if _obter_executavel_janela(hwnd) == "spotify.exe":
                    janelas_spotify.append(int(hwnd))
        return True

    USER32.EnumWindows(WNDENUMPROC(_callback), 0)
    return janelas_spotify[0] if janelas_spotify else 0


def _forcar_foco_janela(hwnd: int) -> None:
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


# =====================================================================
# NÍVEL 1: SPOTIFY WEB API (SPOTIPY + OAUTH PKCE SEM CLIENT_SECRET)
# =====================================================================
def _obter_cliente_spotipy() -> Any:
    """Inicializa e reutiliza o cliente Spotipy PKCE se spotify_client_id estiver configurado."""
    global _CLIENTE_SPOTIFY, _ULTIMO_CLIENT_ID, _ULTIMO_REDIRECT_URI

    if not SPOTIPY_DISPONIVEL or spotipy is None or SpotifyPKCE is None:
        return None

    cfg = carregar_configuracoes()
    client_id = str(cfg.get("spotify_client_id", "")).strip()
    redirect_uri = (
        str(cfg.get("spotify_redirect_uri", SPOTIFY_REDIRECT_URI_PADRAO)).strip()
        or SPOTIFY_REDIRECT_URI_PADRAO
    )

    if not client_id:
        _CLIENTE_SPOTIFY = None
        _ULTIMO_CLIENT_ID = ""
        return None

    if (
        _CLIENTE_SPOTIFY is not None
        and client_id == _ULTIMO_CLIENT_ID
        and redirect_uri == _ULTIMO_REDIRECT_URI
    ):
        return _CLIENTE_SPOTIFY

    try:
        caminho_cache = os.path.join(PASTA_DATA, ".spotify_cache")
        auth_manager = SpotifyPKCE(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=SPOTIFY_SCOPES,
            cache_path=caminho_cache,
            open_browser=True,
        )
        _CLIENTE_SPOTIFY = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=8)
        _ULTIMO_CLIENT_ID = client_id
        _ULTIMO_REDIRECT_URI = redirect_uri
        return _CLIENTE_SPOTIFY
    except Exception as e:
        log.warning("Falha ao criar cliente Spotipy PKCE: %s", e)
        _CLIENTE_SPOTIFY = None
        return None


def _selecionar_dispositivo_spotify(sp: Any) -> dict[str, Any] | None:
    """Retorna o dispositivo ativo (ou o primeiro PC disponível, abrindo o app se necessário)."""
    def _buscar() -> dict[str, Any] | None:
        resp = sp.devices()
        lista = resp.get("devices", []) if isinstance(resp, dict) else []
        if not lista:
            return None
        for dev in lista:
            if dev.get("is_active"):
                return dev
        for dev in lista:
            if str(dev.get("type", "")).lower() == "computer":
                return dev
        return lista[0]

    dispositivo = _buscar()
    if dispositivo is not None:
        return dispositivo

    # Se o Spotify Desktop ainda não está aberto, abre e aguarda registrar o dispositivo
    if encontrar_janela_spotify() == 0:
        try:
            os.startfile("spotify:")
            for _ in range(12):
                time.sleep(0.5)
                dispositivo = _buscar()
                if dispositivo is not None:
                    return dispositivo
        except Exception:
            pass

    return None


def _tocar_via_web_api(termo: str) -> str | None:
    """Tenta buscar e tocar via Spotify Web API. Retorna None para acionar o fallback local."""
    sp = _obter_cliente_spotipy()
    if sp is None:
        return None

    try:
        dispositivo = _selecionar_dispositivo_spotify(sp)
        if dispositivo is None:
            log.info("Spotipy sem dispositivo ativo -> usando fallback local.")
            return None

        device_id = str(dispositivo["id"])
        termo_lower = termo.lower()
        quer_playlist = any(p in termo_lower for p in ("playlist", "mix", "lo-fi", "lofi"))

        if quer_playlist:
            res_pl = sp.search(q=termo, type="playlist", limit=1)
            itens_pl = (res_pl.get("playlists") or {}).get("items") or []
            itens_pl = [p for p in itens_pl if isinstance(p, dict) and p.get("uri")]
            if itens_pl:
                pl = itens_pl[0]
                sp.start_playback(device_id=device_id, context_uri=pl["uri"])
                nome_pl = str(pl.get("name", termo))
                log.info("[Spotify API] Tocando playlist: %s", nome_pl)
                return f"Tocando a playlist {nome_pl} no Spotify."

        res = sp.search(q=termo, type="track", limit=1)
        faixas = (res.get("tracks") or {}).get("items") or []
        if not faixas:
            return f"Não encontrei nenhuma música para '{termo}' no Spotify."

        faixa = faixas[0]
        uri = str(faixa["uri"])
        titulo = str(faixa.get("name", termo))
        artistas = faixa.get("artists") or []
        artista = str(artistas[0].get("name", "")) if artistas else ""

        sp.start_playback(device_id=device_id, uris=[uri])
        log.info("[Spotify API] Tocando faixa: %s - %s", titulo, artista)
        if artista:
            return f"Tocando {titulo}, de {artista}, no Spotify."
        return f"Tocando {titulo} no Spotify."
    except Exception as e:
        log.warning("Spotify Web API falhou (%s) -> usando fallback local.", e)
        return None


# =====================================================================
# NÍVEL 2: FALLBACK LOCAL SEM PIXEL FIXO (CTRL+K + CLIPBOARD + SHIFT+ENTER)
# =====================================================================
def _garantir_spotify_aberto() -> tuple[int, bool]:
    hwnd = encontrar_janela_spotify()
    if hwnd:
        return hwnd, True

    try:
        os.startfile("spotify:")
    except Exception:
        return 0, False

    for _ in range(16):
        time.sleep(0.5)
        hwnd = encontrar_janela_spotify()
        if hwnd:
            time.sleep(1.5)
            return hwnd, False
    return 0, False


def _tocar_via_atalho_teclado(termo: str) -> str:
    """Busca e dá play usando apenas atalhos nativos do Spotify Desktop (independente de DPI/resolução)."""
    janela_anterior = int(USER32.GetForegroundWindow())
    hwnd_sp, ja_estava_aberto = _garantir_spotify_aberto()
    if not hwnd_sp:
        return "Não consegui abrir ou localizar o aplicativo do Spotify instalado."

    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_RETURN = 0x0D
    VK_ESCAPE = 0x1B
    VK_A = 0x41
    VK_K = 0x4B
    VK_V = 0x56

    clipboard_backup = _ler_clipboard_texto()
    try:
        _forcar_foco_janela(hwnd_sp)
        time.sleep(0.12)

        # Abre a Busca Rápida (Ctrl+K), limpa o campo (Ctrl+A) e cola o nome da música (Ctrl+V)
        _enviar_atalho(VK_CONTROL, VK_K)
        time.sleep(0.32)

        if not _escrever_clipboard_texto(termo):
            return "Não consegui enviar o nome da música para a busca do Spotify."

        _enviar_atalho(VK_CONTROL, VK_A)
        time.sleep(0.05)
        _enviar_atalho(VK_CONTROL, VK_V)
        time.sleep(0.85)

        # Shift+Enter reproduz imediatamente o primeiro resultado na busca rápida do Spotify
        _enviar_atalho(VK_SHIFT, VK_RETURN)
        time.sleep(0.18)
        _pressionar_tecla_fisica(VK_ESCAPE, False)
        _pressionar_tecla_fisica(VK_ESCAPE, True)

        if janela_anterior and janela_anterior != hwnd_sp:
            time.sleep(0.10)
            _forcar_foco_janela(janela_anterior)

        log.info("[Spotify Fallback Ctrl+K] Busca enviada: '%s'", termo)
        return (
            f"Trocando para {termo} no Spotify."
            if ja_estava_aberto
            else f"Colocando {termo} para tocar no Spotify."
        )
    except Exception as e:
        log.warning("Aviso no fallback Ctrl+K do Spotify: %s", e)
        return f"Tive um problema ao controlar o Spotify: {e}"
    finally:
        if clipboard_backup is not None:
            _escrever_clipboard_texto(clipboard_backup)


# =====================================================================
# API PÚBLICA DO MÓDULO
# =====================================================================
def tocar_musica_spotify(nome_musica: str) -> str:
    limpo = (nome_musica or "").strip()
    if not limpo:
        return "Qual música você quer que eu coloque no Spotify?"

    # Nível 1: Web API (segundo plano, sem tirar o foco de jogos/VS Code)
    resposta_api = _tocar_via_web_api(limpo)
    if resposta_api is not None:
        return resposta_api

    # Nível 2: Atalhos de teclado (zero coordenada fixa)
    return _tocar_via_atalho_teclado(limpo)


def ajustar_volume_spotify(acao: str, nivel_porcentagem: int = -1) -> str:
    # Nível 1: Volume exato em segundo plano via Web API
    sp = _obter_cliente_spotipy()
    if sp is not None:
        try:
            dispositivo = _selecionar_dispositivo_spotify(sp)
            if dispositivo is not None:
                device_id = str(dispositivo["id"])
                vol_atual = int(dispositivo.get("volume_percent") or 50)
                if nivel_porcentagem >= 0:
                    alvo = max(0, min(100, int(nivel_porcentagem)))
                elif acao == "aumentar":
                    alvo = min(100, vol_atual + 15)
                else:
                    alvo = max(0, vol_atual - 15)
                sp.volume(alvo, device_id=device_id)
                log.info("[Spotify API] Volume definido para %d%%", alvo)
                return f"Volume do Spotify em {alvo} por cento."
        except Exception as e:
            log.warning("Volume via Spotify API falhou (%s) -> fallback local.", e)

    # Nível 2: Atalhos Ctrl+Seta no Spotify Desktop
    janela_anterior = int(USER32.GetForegroundWindow())
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
    acao_limpa = (acao or "").lower().strip()

    # Nível 1: Controle direto via Web API se configurado e ativo
    sp = _obter_cliente_spotipy()
    if sp is not None:
        try:
            dispositivo = _selecionar_dispositivo_spotify(sp)
            if dispositivo is not None:
                device_id = str(dispositivo["id"])
                if acao_limpa == "pausar":
                    sp.pause_playback(device_id=device_id)
                    return "Reprodução pausada no Spotify."
                if acao_limpa == "continuar":
                    sp.start_playback(device_id=device_id)
                    return "Retomando a música no Spotify."
                if acao_limpa == "proxima":
                    sp.next_track(device_id=device_id)
                    return "Próxima faixa no Spotify."
                if acao_limpa == "anterior":
                    sp.previous_track(device_id=device_id)
                    return "Faixa anterior no Spotify."
        except Exception as e:
            log.debug("Fallback mídia Web API -> teclas Windows: %s", e)

    # Nível 2: Teclas multimídia globais do Windows
    mapa = {
        "pausar": (0xB3, "Reprodução pausada."),
        "continuar": (0xB3, "Retomando a música."),
        "proxima": (0xB0, "Próxima faixa."),
        "anterior": (0xB1, "Faixa anterior."),
    }
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