"""Sous Linux, de fausses versions de ce que Windows fournit (winreg, msvcrt, les DLL via
ctypes.WinDLL) : les modules écrits pour Windows se chargent tels quels, et chaque appel à
Windows lève OSError, que le code attrape déjà là où une source peut manquer. Installé une
fois, au tout début de l'appli (g19_monitor.py), avant tout autre import du paquet g19."""
import ctypes
import os
import sys
import types

NOT_HERE = "propre à Windows (indisponible sous Linux)"


class _Fn:
    """Fonction d'une DLL Windows : on peut régler argtypes / restype, l'appel échoue."""

    def __call__(self, *args, **kw):
        raise OSError(NOT_HERE)


class _Dll:
    def __init__(self, name=""):
        self._name = name
        self._fns = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self._fns.setdefault(name, _Fn())

    def __getitem__(self, name):
        return getattr(self, name)


class _Loader:
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Dll(name)

    def LoadLibrary(self, name):
        return _Dll(name)


def _fail(*_a, **_k):
    raise OSError(NOT_HERE)


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__doc__ = f"{name} factice : {NOT_HERE}"
    m.__getattr__ = lambda attr: _fail     # toute fonction : échoue à l'appel
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def install():
    if os.name == "nt" or getattr(ctypes, "_g19_compat", False):
        return
    ctypes._g19_compat = True
    ctypes.WinDLL = ctypes.OleDLL = _Dll
    ctypes.windll = ctypes.oledll = _Loader()
    if not hasattr(ctypes, "WINFUNCTYPE"):
        ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE
    if not hasattr(ctypes, "WinError"):
        ctypes.WinError = lambda code=None, descr=None: OSError(code, descr or NOT_HERE)
    for fn in ("get_last_error", "set_last_error"):
        if not hasattr(ctypes, fn):
            setattr(ctypes, fn, lambda *a: 0)
    if not hasattr(ctypes, "FormatError"):
        ctypes.FormatError = lambda code=None: NOT_HERE
    hkeys = {k: 0x80000000 + i for i, k in enumerate(
        ("HKEY_CLASSES_ROOT", "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE", "HKEY_USERS",
         "HKEY_PERFORMANCE_DATA", "HKEY_CURRENT_CONFIG"))}
    consts = {"KEY_READ": 0x20019, "KEY_WRITE": 0x20006, "KEY_ALL_ACCESS": 0xF003F,
              "KEY_SET_VALUE": 2, "KEY_QUERY_VALUE": 1, "KEY_WOW64_64KEY": 0x100,
              "REG_SZ": 1, "REG_EXPAND_SZ": 2, "REG_BINARY": 3, "REG_DWORD": 4,
              "REG_MULTI_SZ": 7, "REG_QWORD": 11}
    sys.modules.setdefault("winreg", _module("winreg", **hkeys, **consts))
    sys.modules.setdefault("msvcrt", _module("msvcrt"))
