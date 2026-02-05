# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\graphics\\local-code\\installer\\installer.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\graphics\\local-code\\client\\cli.py', '.'), ('C:\\graphics\\local-code\\client\\api_client.py', '.'), ('C:\\graphics\\local-code\\client\\agent.py', '.'), ('C:\\graphics\\local-code\\client\\tools.py', '.'), ('C:\\graphics\\local-code\\client\\config.py', '.'), ('C:\\graphics\\local-code\\client\\scanner.py', '.'), ('C:\\graphics\\local-code\\client\\chunker.py', '.'), ('C:\\graphics\\local-code\\client\\storage.py', '.'), ('C:\\graphics\\local-code\\client\\version.py', '.'), ('C:\\graphics\\local-code\\client\\updater.py', '.'), ('C:\\graphics\\local-code\\client\\claude_client.py', '.'), ('C:\\graphics\\local-code\\client\\requirements.txt', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='llmcode-setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
