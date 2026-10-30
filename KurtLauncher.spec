# PyInstaller build: default single EXE; KURT_BUILD_MODE=folder for replaceable DLLs.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'src' / 'main.py')],
    pathex=[str(root / 'src')],
    binaries=[],
    datas=[(str(root / 'assets'), 'assets')],
    hiddenimports=['keyring.backends.Windows'] + collect_submodules('win32ctypes'),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False,
)
# Qt 6.12 imports the Windows ICU API. Poppler's different ICU build can have
# the same DLL name on PATH but incompatible (version-suffixed) exports.
# Use the operating system's ICU rather than bundling that unrelated library.
a.binaries = [entry for entry in a.binaries
              if entry[0].lower() not in ('icuuc.dll', 'icudt78.dll')]
pyz = PYZ(a.pure)
options = dict(name='KurtLauncher', debug=False, bootloader_ignore_signals=False,
               strip=False, upx=False, console=False,
               icon=str(root / 'assets' / 'icon.ico'))
if os.environ.get('KURT_BUILD_MODE') == 'folder':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='KurtLauncher')
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
