"""HoldKey: seçilen tuşları kısayolla basılı tutar, tekrar tekrar basar ya da bırakır."""
import json
import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import core
from lang import DEFAULT, LANGUAGES

APPDATA = Path(os.environ.get("APPDATA", Path.home()))
SETTINGS_FILE = APPDATA / "HoldKey" / "settings.json"
OLD_SETTINGS_FILE = APPDATA / "BasiliTut" / "settings.json"  # uygulamanın eski adı
# Exe içinde dosyalar geçici bir klasöre (_MEIPASS) açılıyor
ICON_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "icon.ico"
TICK_MS = 20  # arayüz ve kısayol yoklaması; tuş basma ayrı iş parçacığında

# Renkler: beyaz zemin, siyah vurgu, tek renk dışı durum kırmızı
BG, FG, MUTED, LINE, SOFT = "#ffffff", "#111111", "#8a8a8a", "#e4e4e4", "#f2f2f2"
ACTIVE = "#e5484d"
FONT = ("Segoe UI", 10)
SMALL = ("Segoe UI", 8)
HEADING = ("Segoe UI Semibold", 9)


def load_settings():
    try:
        # Yeni klasörde ayar yoksa eski addaki ayarları bir kereliğine okuyoruz
        path = SETTINGS_FILE if SETTINGS_FILE.exists() else OLD_SETTINGS_FILE
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    # Kayıtlı dil geçerliyse normalize_settings onu korur, değilse Windows dili kullanılır
    return core.normalize_settings(data, LANGUAGES, core.system_language(LANGUAGES, DEFAULT))


def save_settings(settings):
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


def setup_style(root):
    style = ttk.Style(root)
    style.theme_use("clam")  # Windows temasının kabartmalı kenarları yerine düz çizgiler
    style.configure(".", background=BG, foreground=FG, font=FONT)
    for name in ("TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=BG, background=BG, bordercolor=LINE,
                        lightcolor=BG, darkcolor=BG, arrowcolor=FG, arrowsize=13, padding=(8, 5))
        style.map(name, bordercolor=[("focus", FG)], lightcolor=[("focus", BG)],
                  fieldbackground=[("readonly", BG), ("disabled", SOFT)],
                  foreground=[("disabled", MUTED)], arrowcolor=[("disabled", LINE)],
                  selectbackground=[("readonly", BG), ("!readonly", "#d0d0d0")],
                  selectforeground=[("readonly", FG), ("!readonly", FG)])
    # Açılır listelerin kendisi tk penceresi; renklerini ayrıca veriyoruz
    root.option_add("*TCombobox*Listbox.background", BG)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", FG)
    root.option_add("*TCombobox*Listbox.selectForeground", BG)
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)


class Segmented(tk.Frame):
    """İki seçenekli düz anahtar (Basılı tut | Tekrarla)."""

    def __init__(self, parent, values, command):
        super().__init__(parent, bg=LINE, padx=1, pady=1)
        self.command, self.value, self.enabled = command, values[0], True
        self.items = {}
        for col, value in enumerate(values):
            item = tk.Label(self, font=FONT, pady=6, cursor="hand2")
            item.grid(row=0, column=col, sticky="ew", padx=(0, 1) if col < len(values) - 1 else 0)
            item.bind("<Button-1>", lambda e, v=value: self.enabled and self.command(v))
            self.columnconfigure(col, weight=1, uniform="seg")
            self.items[value] = item

    def set(self, value, texts, enabled):
        self.value, self.enabled = value, enabled
        for v, item in self.items.items():
            on = v == value
            item.config(text=texts[v], bg=FG if on else BG,
                        fg=BG if on else (FG if enabled else MUTED),
                        cursor="hand2" if enabled else "arrow")


class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.holder = core.Holder(core.send_press, core.send_release)
        self.lock = threading.Lock()
        self.running = False
        self.hotkey_down = False
        root.resizable(False, False)
        root.configure(bg=BG)
        try:
            root.iconbitmap(default=str(ICON_FILE))
        except tk.TclError:
            pass
        setup_style(root)

        body = tk.Frame(root, bg=BG, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure((0, 1), weight=1, uniform="col")
        self.headings = {}

        self.heading(body, "keys", row=0)
        self.key_boxes = []
        for n in range(core.MAX_KEYS):
            box = ttk.Combobox(body, state="readonly", width=24, height=16)
            box.grid(row=1 + n, column=0, columnspan=2, sticky="ew", pady=(0, 6))
            box.bind("<<ComboboxSelected>>", lambda e: self.set_keys())
            self.key_boxes.append(box)

        self.heading(body, "mode", row=4, top=8)
        self.mode_switch = Segmented(body, core.MODES, self.set_mode)
        self.mode_switch.grid(row=5, column=0, columnspan=2, sticky="ew")

        self.heading(body, "interval", row=6, top=14)
        self.heading(body, "duration", row=6, column=1, top=14)
        self.interval_var = tk.StringVar(value=str(self.settings["interval_ms"]))
        self.interval_box = ttk.Spinbox(body, from_=core.MIN_INTERVAL_MS, to=core.MAX_INTERVAL_MS,
                                        increment=10, width=8, textvariable=self.interval_var)
        self.interval_box.grid(row=7, column=0, sticky="ew", padx=(0, 6))
        self.duration_var = tk.StringVar(value=f"{self.settings['duration_s']:g}")
        self.duration_box = ttk.Spinbox(body, from_=0, to=core.MAX_DURATION_S, increment=1,
                                        width=8, textvariable=self.duration_var)
        self.duration_box.grid(row=7, column=1, sticky="ew", padx=(6, 0))
        self.duration_hint = tk.Label(body, bg=BG, fg=MUTED, font=SMALL)
        self.duration_hint.grid(row=8, column=1, sticky="w", padx=(6, 0), pady=(2, 0))

        tk.Frame(body, bg=LINE, height=1).grid(row=9, column=0, columnspan=2, sticky="ew", pady=12)

        self.heading(body, "hotkey", row=10, top=0)
        self.heading(body, "language", row=10, column=1, top=0)
        self.hotkey_box = ttk.Combobox(body, state="readonly", width=8, values=list(core.HOTKEYS))
        self.hotkey_box.grid(row=11, column=0, sticky="ew", padx=(0, 6))
        self.hotkey_box.bind("<<ComboboxSelected>>", lambda e: self.set_hotkey())
        self.lang_codes = list(LANGUAGES)
        self.lang_box = ttk.Combobox(body, state="readonly", width=8,
                                     values=[LANGUAGES[c]["name"] for c in self.lang_codes])
        self.lang_box.grid(row=11, column=1, sticky="ew", padx=(6, 0))
        self.lang_box.bind("<<ComboboxSelected>>", lambda e: self.set_language())

        self.topmost_var = tk.BooleanVar(value=self.settings["topmost"])
        # clam temasının onay kutusu "X" çiziyor; Windows'un kendi kutusu daha sade
        self.topmost_check = tk.Checkbutton(body, variable=self.topmost_var, command=self.set_topmost,
                                            bg=BG, activebackground=BG, fg=MUTED, activeforeground=FG,
                                            font=SMALL, bd=0, highlightthickness=0, cursor="hand2")
        self.topmost_check.grid(row=12, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.button = tk.Label(body, font=("Segoe UI Semibold", 11), fg=BG, pady=11, cursor="hand2")
        self.button.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(16, 8))
        self.button.bind("<Button-1>", lambda e: self.toggle())
        self.status = tk.Label(body, bg=BG, font=SMALL)
        self.status.grid(row=14, column=0, columnspan=2)

        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.attributes("-topmost", self.settings["topmost"])
        self.refresh()
        self.tick()

    def heading(self, parent, name, row, column=0, top=0):
        label = tk.Label(parent, bg=BG, fg=MUTED, font=HEADING, anchor="w")
        label.grid(row=row, column=column, columnspan=2 if column == 0 and name in ("keys", "mode") else 1,
                   sticky="w", padx=(6, 0) if column else 0, pady=(top, 4))
        self.headings[name] = label

    def t(self, name, **kw):
        return LANGUAGES[self.settings["language"]][name].format(**kw)

    def label(self, choice):
        # Harf, rakam ve F tuşları her dilde aynı; diğerleri çevriliyor ya da adı var
        if choice in LANGUAGES[self.settings["language"]]:
            return self.t(choice)
        return core.KEY_NAMES.get(choice, choice)

    def combo_text(self, keys):
        return " + ".join(self.label(k) for k in keys)

    def refresh(self):
        s = self.settings
        active = self.holder.active
        self.root.title(self.t("title"))
        for name, label in self.headings.items():
            label.config(text=self.t(name))
        self.duration_hint.config(text=self.t("duration_hint"))
        self.topmost_check.config(text=self.t("topmost"))
        self.mode_switch.set(s["mode"], {m: self.t(f"mode_{m}") for m in core.MODES}, not active)

        # Kutulardaki görünen ad -> tuş kimliği eşlemesi dile göre yeniden kuruluyor
        self.choices = core.key_choices(s["hotkey"])
        names = [self.label(c) for c in self.choices]
        for n, box in enumerate(self.key_boxes):
            box.config(values=names if n == 0 else [self.t("none")] + names,
                       state="disabled" if active else "readonly")
            box.set(self.label(s["keys"][n]) if n < len(s["keys"]) else self.t("none"))

        self.interval_box.config(state="disabled" if active or s["mode"] == "hold" else "normal")
        self.duration_box.config(state="disabled" if active else "normal")
        self.hotkey_box.set(s["hotkey"])
        self.hotkey_box.config(state="disabled" if active else "readonly")
        self.lang_box.set(LANGUAGES[s["language"]]["name"])
        self.update_status()

    def update_status(self):
        hotkey = self.settings["hotkey"]
        if not self.holder.active:
            self.button.config(text=self.t("start", hotkey=hotkey), bg=FG)
            self.status.config(text=self.t("idle"), fg=MUTED)
            return
        self.button.config(text=self.t("stop", hotkey=hotkey), bg=ACTIVE)
        state = "holding" if self.holder.mode == "hold" else "repeating"
        text = "●  " + self.t(state, keys=self.combo_text(self.holder.keys))
        remaining = self.holder.remaining(time.monotonic())
        if remaining is not None:
            text += "  ·  " + self.t("remaining", seconds=int(remaining + 0.999))
        self.status.config(text=text, fg=ACTIVE)

    def update_settings(self, **changes):
        self.settings = core.normalize_settings({**self.settings, **changes}, LANGUAGES,
                                                self.settings["language"])
        save_settings(self.settings)
        self.refresh()

    def set_keys(self):
        none = self.t("none")
        by_name = dict(zip((self.label(c) for c in self.choices), self.choices))
        keys = [by_name[b.get()] for b in self.key_boxes if b.get() != none and b.get() in by_name]
        self.update_settings(keys=keys)

    def set_mode(self, mode):
        self.update_settings(mode=mode)

    def set_hotkey(self):
        self.update_settings(hotkey=self.hotkey_box.get())

    def set_language(self):
        self.update_settings(language=self.lang_codes[self.lang_box.current()])

    def set_topmost(self):
        self.root.attributes("-topmost", self.topmost_var.get())
        self.update_settings(topmost=self.topmost_var.get())

    def toggle(self):
        if self.holder.active:
            self.stop()
        elif not self.running:  # önceki iş parçacığı kapanmadan yeniden başlatma
            # Kutulara yazılan sayılar başlatırken okunup düzeltiliyor
            self.update_settings(interval_ms=self.interval_var.get(), duration_s=self.duration_var.get())
            s = self.settings
            self.interval_var.set(str(s["interval_ms"]))
            self.duration_var.set(f"{s['duration_s']:g}")
            with self.lock:
                self.holder.start(s["keys"], s["mode"], s["interval_ms"], s["duration_s"], time.monotonic())
            self.running = True
            threading.Thread(target=self.run, daemon=True).start()
        self.refresh()

    def run(self):
        # Tk zamanlayıcısı ~30 ms'den kısa aralıkları tutturamadığı için ayrı döngü
        core.precise_timer(True)
        try:
            while True:
                with self.lock:
                    if not self.holder.tick(time.monotonic()):
                        break
                time.sleep(0.001)
        finally:
            core.precise_timer(False)
            self.running = False

    def stop(self):
        with self.lock:
            self.holder.stop()

    def tick(self):
        # Önce bir sonrakini planlıyoruz ki bir hata kısayolu kalıcı olarak öldürmesin
        self.root.after(TICK_MS, self.tick)
        # Kısayol her pencereden çalışsın diye tuş durumunu yokluyoruz
        down = core.hotkey_down(self.settings["hotkey"])
        if down and not self.hotkey_down:
            self.toggle()
        self.hotkey_down = down
        if self.holder.active:
            self.update_status()
        elif self.button["bg"] != FG:
            self.refresh()  # süre doldu, arayüzü bekleme haline döndür

    def quit(self):
        self.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
