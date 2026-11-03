"""
ignoclip.py — the system clipboard, for every pygame app in this project.

Lifted out of ignoAPI so the mapper can paste into a text box without
importing ignoAPI (which would start its servers on import). ignoAPI's own
clipboard_set/clipboard_get now delegate here, so there is one implementation
and it cannot drift.

Win32 directly rather than pygame.scrap (unreliable) or a Tk root (would need
an event loop alongside pygame's). Everything else falls back to a throwaway
withdrawn Tk root, which is fine off Windows where there is no pygame/Tk
event-loop clash to worry about.
"""
import ctypes
import os

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def clipboard_set(text):
    if os.name == "nt":
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        k32.GlobalAlloc.restype = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.restype = ctypes.c_void_p
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        if not u32.OpenClipboard(0):
            return False
        try:
            u32.EmptyClipboard()
            buf = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(buf)
            h = k32.GlobalAlloc(GMEM_MOVEABLE, size)
            p = k32.GlobalLock(h)
            ctypes.memmove(p, buf, size)
            k32.GlobalUnlock(h)
            u32.SetClipboardData(CF_UNICODETEXT, h)
        except Exception as e:
            print(f"[ignoclip] copy failed: {e}")
            return False
        finally:
            u32.CloseClipboard()
        return True
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        return False


def clipboard_get():
    if os.name == "nt":
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        u32.GetClipboardData.restype = ctypes.c_void_p
        u32.GetClipboardData.argtypes = [ctypes.c_uint]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        if not u32.OpenClipboard(0):
            return ""
        try:
            h = u32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ""
            p = k32.GlobalLock(h)
            if not p:
                return ""
            try:
                return ctypes.c_wchar_p(p).value or ""
            finally:
                k32.GlobalUnlock(h)
        except Exception:
            return ""
        finally:
            u32.CloseClipboard()
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        s = r.clipboard_get()
        r.destroy()
        return s
    except Exception:
        return ""
