"""Tuş listesi, ayar kontrolü ve basma mantığı. Arayüzden bağımsız olduğu için test edilebilir."""
import ctypes
import string
import sys
from ctypes import wintypes

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE, KEYEVENTF_EXTENDEDKEY = 0x2, 0x8, 0x1
MOUSE_FLAGS = {"mouse_left": (0x2, 0x4), "mouse_right": (0x8, 0x10), "mouse_middle": (0x20, 0x40)}
HOTKEYS = {f"F{n}": 0x6F + n for n in range(6, 13)}  # F6..F12

KEYS = {c: ord(c) for c in string.ascii_uppercase + string.digits}
KEYS.update({f"F{n}": 0x6F + n for n in range(1, 13)})
KEYS.update({
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08, "capslock": 0x14,
    "Shift": 0xA0, "Ctrl": 0xA2, "Alt": 0xA4,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
})
KEYS.update({f"num{n}": 0x60 + n for n in range(10)})
KEYS.update({"num_mul": 0x6A, "num_add": 0x6B, "num_sub": 0x6D, "num_dec": 0x6E, "num_div": 0x6F})

# Scan code ile gönderirken "extended" bayrağı isteyen tuşlar
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x6F, 0xA3, 0xA5}

# Çevrilmeyen tuşların görünen adları (çevrilenler lang.py'de)
KEY_NAMES = {
    "enter": "Enter", "tab": "Tab", "esc": "Esc", "backspace": "Backspace", "capslock": "Caps Lock",
    "insert": "Insert", "delete": "Delete", "home": "Home", "end": "End",
    "pgup": "Page Up", "pgdn": "Page Down",
    "num_mul": "Num *", "num_add": "Num +", "num_sub": "Num -", "num_dec": "Num .", "num_div": "Num /",
    **{f"num{n}": f"Num {n}" for n in range(10)},
}

CHOICES = list(MOUSE_FLAGS) + list(KEYS)
MAX_KEYS = 3
MODES = ("hold", "repeat")
MIN_INTERVAL_MS, MAX_INTERVAL_MS = 10, 60_000
MAX_DURATION_S = 24 * 60 * 60
KEY_REPEAT_S = 0.03  # basılı tutarken klavyenin kendi tekrar hızına yakın

DEFAULT_SETTINGS = {"keys": ["W"], "hotkey": "F8", "topmost": True,
                    "mode": "hold", "interval_ms": 100, "duration_s": 0}


def key_choices(hotkey):
    # Kısayol tuşunu basılı tutmak uygulamayı kendi kendine açıp kapatırdı
    return [c for c in CHOICES if c != hotkey]


def _number(value, default, low, high, cast):
    try:
        value = cast(value)
    except (TypeError, ValueError, OverflowError):  # int(inf) OverflowError verir
        return default
    if value != value:  # NaN
        return default
    return min(max(value, low), high)


def _pick(value, allowed, default):
    # Elle düzenlenmiş dosyada liste/sözlük gibi değerler "in" kontrolünde TypeError verir
    return value if isinstance(value, str) and value in allowed else default


def normalize_settings(data, languages, fallback_language):
    """Kayıtlı ayarları kontrol eder; bozuk ya da eski değerler uygulamayı çökertmesin."""
    s = {**DEFAULT_SETTINGS, **data}
    if "key" in s:  # eski sürüm tek tuş saklıyordu
        if "keys" not in data:
            s["keys"] = [s["key"]]
        del s["key"]

    s["language"] = _pick(s.get("language"), languages, fallback_language)
    s["hotkey"] = _pick(s["hotkey"], HOTKEYS, DEFAULT_SETTINGS["hotkey"])

    allowed = key_choices(s["hotkey"])
    keys = s["keys"] if isinstance(s["keys"], list) else []
    keys = [k for k in keys if isinstance(k, str)]
    keys = [k for k in dict.fromkeys(keys) if k in allowed][:MAX_KEYS]
    s["keys"] = keys or list(DEFAULT_SETTINGS["keys"])

    s["mode"] = _pick(s["mode"], MODES, DEFAULT_SETTINGS["mode"])
    s["interval_ms"] = _number(s["interval_ms"], DEFAULT_SETTINGS["interval_ms"],
                               MIN_INTERVAL_MS, MAX_INTERVAL_MS, int)
    s["duration_s"] = _number(s["duration_s"], 0, 0, MAX_DURATION_S, float)
    s["topmost"] = bool(s["topmost"])
    return s


class Holder:
    """Seçilen tuşları basılı tutar ya da aralıkla basar. Zaman dışarıdan verilir."""

    def __init__(self, press, release):
        self.press, self.release = press, release
        self.active = False
        self.keys, self.mode = [], "hold"

    def start(self, keys, mode, interval_ms, duration_s, now):
        self.keys, self.mode = list(keys), mode
        self.interval = interval_ms / 1000
        self.ends_at = now + duration_s if duration_s > 0 else None
        self.active = True
        if mode == "hold":
            for k in self.keys:
                self.press(k)
            self.next_repeat = now + KEY_REPEAT_S
        else:
            self._tap()
            self.next_tap = now + self.interval

    def tick(self, now):
        """Döngüde çağrılır. Süre dolup durduysa False döner."""
        if not self.active:
            return False
        if self.ends_at is not None and now >= self.ends_at:
            self.stop()
            return False
        if self.mode == "hold":
            if now >= self.next_repeat:
                # Gerçek basılı tutma gibi klavye tuşunu tekrar gönder; fare tuşu zaten basılı
                for k in self.keys:
                    if k not in MOUSE_FLAGS:
                        self.press(k)
                self.next_repeat = now + KEY_REPEAT_S
        elif now >= self.next_tap:
            self._tap()
            # Uzun bir duraklamadan sonra kaçan basışları art arda göndermiyoruz
            self.next_tap = max(self.next_tap, now) + self.interval
        return True

    def remaining(self, now):
        return None if self.ends_at is None else max(self.ends_at - now, 0)

    def stop(self):
        if self.active and self.mode == "hold":
            for k in reversed(self.keys):
                self.release(k)
        self.active = False

    def _tap(self):
        for k in self.keys:
            self.press(k)
        for k in reversed(self.keys):
            self.release(k)


# --- Windows'a gerçek tuş gönderme ---

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _U(ctypes.Union):
        # Dolgu eklemiyoruz: boyut 32 ve 64 bit Python'da ayrı, en büyük üye MOUSEINPUT
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    def _send(inp):
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _key(vk, up):
        # Scan code ile gönderiyoruz ki oyunlar da algılasın
        scan = user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        if vk in EXTENDED:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(0, scan, flags, 0, 0)
        _send(inp)

    def _mouse(name, up):
        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(0, 0, 0, MOUSE_FLAGS[name][1 if up else 0], 0, 0)
        _send(inp)

    def send_press(choice):
        _mouse(choice, False) if choice in MOUSE_FLAGS else _key(KEYS[choice], False)

    def send_release(choice):
        _mouse(choice, True) if choice in MOUSE_FLAGS else _key(KEYS[choice], True)

    def precise_timer(on):
        # Windows varsayılan olarak ~15 ms'lik adımlarla uyutur; kısa aralıklar için 1 ms'ye indiriyoruz
        winmm = ctypes.WinDLL("winmm")
        (winmm.timeBeginPeriod if on else winmm.timeEndPeriod)(1)

    def hotkey_down(hotkey):
        return bool(user32.GetAsyncKeyState(HOTKEYS[hotkey]) & 0x8000)

    def system_language(languages, fallback):
        # Windows arayüz dilinden "tr-TR" gibi bir ad alıp "tr" kısmına bakıyoruz
        buf = ctypes.create_unicode_buffer(85)
        kernel32 = ctypes.windll.kernel32
        if kernel32.LCIDToLocaleName(kernel32.GetUserDefaultUILanguage(), buf, len(buf), 0):
            code = buf.value.split("-")[0].lower()
            if code in languages:
                return code
        return fallback
