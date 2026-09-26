"""PyInstaller hook for tkinterdnd2/TkDND native files and submodules."""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("tkinterdnd2")
