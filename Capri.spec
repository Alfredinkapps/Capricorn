# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = []
binaries = []
hiddenimports = [
    # Módulos internos carregados dinamicamente ou dentro de try/except
    "ui.modo_livre",
    "ai.visao",
    "ai.ferramentas",
    "ai.memoria",
    "ai.cerebro",
    "agents.reigns",
    "audio.voz",
    "audio.comandos",
    "system.apps",
    "system.spotify",
    "core.config",
    "core.logger",
    "core.engine",
    # Dependências externas com carregamento dinâmico no Windows
    "pystray._win32",
    "PIL._tkinter_finder",
    "mss",
    "mss.windows",
    "pytweening",
    "pyautogui",
    "edge_tts",
    "speech_recognition",
    "pygame",
    "sqlite3",
    "winreg",
    "spotipy",
    "spotipy.oauth2",
]

# Coleta DLLs nativas, dados e submódulos obrigatórios (Vosk, PortAudio, SSL, Gemini e Spotify)
for pkg in ("vosk", "sounddevice", "_sounddevice_data", "certifi", "google.genai", "spotipy"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Embute assets/ (sprites e ícones) sem nunca incluir data/ (chaves e SQLite)
if os.path.isdir("assets"):
    datas.append(("assets", "assets"))

# Localiza automaticamente o .ico disponível em assets/
icone_exe = None
if os.path.isdir("assets"):
    for raiz, _, arquivos in os.walk("assets"):
        for arq in arquivos:
            if arq.lower() in ("app.ico", "icone.ico"):
                icone_exe = os.path.join(raiz, arq)
                break
        if icone_exe:
            break

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(dict.fromkeys(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "pytest", "IPython", "jupyter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Capri",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icone_exe,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Capri",
)