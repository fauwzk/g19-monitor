"""Remet au premier plan la fenêtre d'une session Claude : celle du processus parent le plus
proche (terminal, éditeur ou appli desktop) qui possède une fenêtre visible."""
import ctypes
from ctypes import wintypes

import psutil

user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]

GW_OWNER = 4
# parents qui ne sont pas « la fenêtre de la session » (on s'arrête avant)
STOP = {"explorer.exe", "svchost.exe", "services.exe", "wininit.exe", "userinit.exe"}
SW_RESTORE, SW_SHOW = 9, 5
VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002


def _windows_by_pid():
    """pid → première fenêtre principale visible (titrée, sans propriétaire)."""
    found = {}

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.setdefault(pid.value, hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def bring_to_front(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)
    # Windows refuse le premier plan à une appli en arrière-plan : un appui virtuel sur Alt
    # (sans effet visible) lève cette restriction
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    return bool(user32.SetForegroundWindow(hwnd))


def focus_session(session):
    """True si une fenêtre de la session a été mise au premier plan."""
    pids = session.get("pids") or []
    if not pids:
        return False
    windows = _windows_by_pid()
    for pid in pids:              # du plus proche (Claude) au plus lointain
        try:
            if psutil.Process(pid).name().lower() in STOP:
                break
        except psutil.Error:
            continue              # processus terminé depuis : on remonte
        hwnd = windows.get(pid)
        if hwnd:
            return bring_to_front(hwnd)
    return False
