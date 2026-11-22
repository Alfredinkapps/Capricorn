# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = collect_dynamic_libs('vosk')

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        'core.config',
        'core.logger',
        'core.engine',
        'ui.hud',
        'ui.modo_livre',
        'ai.cerebro',
        'ai.visao',
        'ai.memoria',
        'agents.reigns',
        'audio.voz',
        'audio.comandos',
        'system.apps',
        'system.spotify',
        'vosk',
        'pystray._win32',
        'pytweening',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'cv2',
        'torch',
        'tensorflow',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'IPython',
        'jupyter',
        'pytest',
        'unittest',
        'doctest',
        'pydoc',
        'tkinter.test',
        'setuptools',
        'pip',
        'wheel',
        # 'numpy',  # Descomente se o Select-String acima não encontrar uso de numpy
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Capri',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    contents_directory='_internal',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Capri',
)