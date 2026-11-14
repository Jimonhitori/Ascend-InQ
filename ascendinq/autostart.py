"""Start Ascend InQ when Windows starts (per-user Run key, no admin rights)."""
import sys
from pathlib import Path

from . import config

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "AscendInQ"


def command() -> str:
    if config.FROZEN:
        return f'"{Path(sys.executable).resolve()}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{config.ROOT / "app.py"}"'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, NAME)
            return True
    except OSError:
        return False


def set_enabled(on: bool):
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, NAME)
            except OSError:
                pass
