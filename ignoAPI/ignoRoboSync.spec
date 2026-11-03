# -*- mode: python ; coding: utf-8 -*-
#
#   pyinstaller ignoRoboSync.spec
#
# Onefile build, no icon/datas: ignoRoboSync.py doesn't load anything
# off disk at runtime the way ignoAPI.py does (no .ico for a tray, no
# .wav for pygame.mixer -- it never even imports mixer). If you do
# want a taskbar icon, add an icon=... line the same way ignoAPI.spec
# does and list the .ico under datas too if anything in the app reads
# it back at run time (ignoRoboSync.py currently doesn't).
#
# ignoClient.py is a plain top-level import ("import ignoClient as c"
# at module level) -- PyInstaller finds it by static analysis the same
# way ignoAPI.spec's ignomdns is found, but it's listed under
# hiddenimports anyway to make the dependency explicit. Build from a
# folder that has ignoRoboSync.py and ignoClient.py side by side.

a = Analysis(
    ['ignoRoboSync.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'ignoClient',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Carried over from ignoAPI.spec's own excludes, verified
        # against ignoRoboSync.py the same way: no numpy, OpenGL,
        # tkinter, or any of the rest below are imported anywhere in
        # this file. They still ride in beside pygame if left in.
        #
        #   OpenGL      pulled in beside pygame, never called
        #   numpy       pygame only needs it for surfarray, which
        #               ignoRoboSync.py does not use
        #   setuptools  a build-time tool, not a runtime one
        #
        # UNVERIFIED CAVEAT: this only checked ignoRoboSync.py itself.
        # ignoClient.py wasn't available to check the same way ignoAPI
        # checked ignomdns/ignodiscover/comserial/hardwareCSV -- if
        # the frozen exe raises a missing-module error at runtime
        # (rather than at build time), it's almost certainly
        # ignoClient.py reaching for one of these; delete that one
        # line and rebuild.
        'OpenGL',
        'numpy',
        'setuptools',
        'pkg_resources',
        'scipy',
        'matplotlib',
        'pandas',
        'cv2',
        'torch',
        'unittest',
        # Unlike ignoAPI.py, ignoRoboSync.py never opens a filedialog
        # (the FTP folder is a typed-in text field, not a folder
        # picker), so tkinter is excluded here rather than kept.
        'tkinter',
        # No system tray in this app, so -- also unlike ignoAPI.py --
        # these are never imported.
        'pystray',
        'PIL',
    ],
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
    name='ignoRoboSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX OFF, same reasoning as ignoAPI.spec: packed executables are
    # a well-known antivirus false-positive trigger, and the excludes
    # above already do most of the size-cutting UPX would have done.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Windowed, not console: every status line this app produces goes
    # through log()'s self.set_status(...) into the pygame window
    # itself (footer/status text), and print() is only a duplicate of
    # that -- so, same as ignoAPI.py, there's nothing meant for a
    # console to actually catch. Switch to True temporarily if you
    # need to see the print() output while debugging a build.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='ignoRoboSync.ico',   # uncomment and point at a real .ico
)
