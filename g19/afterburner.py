"""Lecture de la mémoire partagée de MSI Afterburner (« MAHMSharedMemory »).

Afterburner (avec RTSS pour les FPS) doit tourner ; on ne fait que lire ses capteurs.
"""
import ctypes
import struct
from ctypes import wintypes

FILE_MAP_READ = 0x0004
SIGNATURE = 0x4D41484D  # 'MAHM'
INVALID = 3.0e38        # Afterburner met FLT_MAX quand une valeur n'est pas dispo

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenFileMappingW.restype = wintypes.HANDLE
_k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                               wintypes.DWORD, ctypes.c_size_t]
_k32.MapViewOfFile.restype = ctypes.c_void_p
_k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

_HEADER = struct.Struct("<6I")  # signature, version, headerSize, numEntries, entrySize, time
_PATH = 260


def _cstr(raw):
    return raw.split(b"\0", 1)[0].decode("latin-1")


def read_sensors():
    """{nom_source: (valeur, unité, gpu_index)} ou None si Afterburner n'est pas lancé."""
    h = _k32.OpenFileMappingW(FILE_MAP_READ, False, "MAHMSharedMemory")
    if not h:
        return None
    try:
        view = _k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 0)
        if not view:
            return None
        try:
            sig, ver, hsize, n, esize, _ = _HEADER.unpack(ctypes.string_at(view, _HEADER.size))
            if sig != SIGNATURE or n > 4096:
                return None
            raw = ctypes.string_at(view + hsize, n * esize)
        finally:
            _k32.UnmapViewOfFile(view)
    finally:
        _k32.CloseHandle(h)

    out = {}
    for i in range(n):
        e = raw[i * esize:(i + 1) * esize]
        name = _cstr(e[0:_PATH])
        units = _cstr(e[_PATH:2 * _PATH])
        value, = struct.unpack_from("<f", e, 5 * _PATH)
        gpu = struct.unpack_from("<I", e, 5 * _PATH + 16)[0] if esize >= 5 * _PATH + 20 else 0
        if abs(value) >= INVALID:
            continue
        key = name if name not in out else f"{name} #{gpu}"
        out[key] = (value, units, gpu)
    return out


if __name__ == "__main__":
    for k, (v, u, g) in (read_sensors() or {}).items():
        print(f"{k:40s} {v:10.2f} {u:8s} gpu{g}")
