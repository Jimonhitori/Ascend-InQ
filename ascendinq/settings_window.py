"""Settings window (tkinter, standard library only). Runs in its own process."""
import ctypes
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk

from . import autostart, config
from .i18n import t
from .icon import make_icon

BG, PANEL, CARD, LINE = "#14181d", "#1b2027", "#232a33", "#2c343e"
TEXT, MUTED, GOLD, GOLD_DARK = "#e7e9ec", "#8b95a1", "#c8aa6e", "#9c8350"
FONT = ("Yu Gothic UI", 10)
FONT_B = ("Yu Gothic UI", 10, "bold")
FONT_H = ("Yu Gothic UI", 15, "bold")
FONT_S = ("Yu Gothic UI", 9)


class Toggle(tk.Canvas):
    """iOS-style switch."""

    def __init__(self, master, value: bool, bg=PANEL):
        super().__init__(master, width=44, height=24, bg=bg, highlightthickness=0, cursor="hand2")
        self.var = tk.BooleanVar(value=value)
        self.bind("<Button-1>", lambda e: self.set(not self.var.get()))
        self.draw()

    def set(self, v):
        self.var.set(v)
        self.draw()

    def get(self):
        return self.var.get()

    def draw(self):
        self.delete("all")
        on = self.var.get()
        c = GOLD if on else "#3a424c"
        self.create_oval(2, 2, 22, 22, fill=c, outline=c)
        self.create_oval(22, 2, 42, 22, fill=c, outline=c)
        self.create_rectangle(12, 2, 32, 22, fill=c, outline=c)
        x = 32 if on else 12
        self.create_oval(x - 8, 4, x + 8, 20, fill="#ffffff", outline="")


class ChoiceCards(tk.Frame):
    """Radio choices shown as cards (like the capture-mode picker)."""

    def __init__(self, master, options, value):
        super().__init__(master, bg=PANEL)
        self.value = value
        self.cards = {}
        for i, (key, title, sub) in enumerate(options):
            card = tk.Frame(self, bg=CARD, highlightthickness=1, highlightbackground=LINE, cursor="hand2")
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            self.columnconfigure(i, weight=1, uniform="c")
            dot = tk.Canvas(card, width=14, height=14, bg=CARD, highlightthickness=0)
            dot.grid(row=0, column=0, padx=(12, 8), pady=(12, 0), sticky="n")
            t = tk.Label(card, text=title, font=FONT_B, bg=CARD, fg=TEXT, anchor="w")
            t.grid(row=0, column=1, sticky="w", pady=(10, 0), padx=(0, 12))
            s = tk.Label(card, text=sub, font=FONT_S, bg=CARD, fg=MUTED, anchor="w", justify="left", wraplength=210)
            s.grid(row=1, column=1, sticky="w", pady=(0, 10), padx=(0, 12))
            for w in (card, dot, t, s):
                w.bind("<Button-1>", lambda e, k=key: self.select(k))
            self.cards[key] = (card, dot, t, s)
        self.select(value)

    def select(self, key):
        self.value = key
        for k, (card, dot, t, s) in self.cards.items():
            on = k == key
            bg = "#2b333d" if on else CARD
            card.configure(bg=bg, highlightbackground=GOLD if on else LINE)
            for w in (dot, t, s):
                w.configure(bg=bg)
            dot.delete("all")
            dot.create_oval(1, 1, 13, 13, outline=GOLD if on else MUTED, width=2)
            if on:
                dot.create_oval(4, 4, 10, 10, fill=GOLD, outline="")

    def get(self):
        return self.value


class SettingsWindow:
    def __init__(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        config.ensure_env()
        config.reload()
        self.s = config.settings()

        self.root = root = tk.Tk()
        root.title(t("s.title"))
        root.configure(bg=BG)
        root.geometry("720x780")
        root.minsize(600, 500)
        try:
            from PIL import ImageTk
            self._icon = ImageTk.PhotoImage(make_icon("waiting", 64))
            root.iconphoto(True, self._icon)
        except Exception:
            pass
        self._style()

        # scrollable body
        outer = tk.Frame(root, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.body = tk.Frame(canvas, bg=BG)
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        root.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._build()

        bar = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text="", font=FONT, bg=PANEL, fg=MUTED)
        self.status.pack(side="left", padx=16)
        self._button(bar, t("s.save"), self.save, primary=True).pack(side="right", padx=(6, 16), pady=10)
        self._button(bar, t("s.cancel"), root.destroy).pack(side="right", pady=10)

    # ------------------------------------------------------------ widgets
    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground=BG, background=CARD, foreground=TEXT, arrowcolor=TEXT,
                     bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", BG)], foreground=[("readonly", TEXT)],
               selectbackground=[("readonly", BG)], selectforeground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", GOLD_DARK)
        self.root.option_add("*TCombobox*Listbox.font", FONT)
        st.configure("Vertical.TScrollbar", background=CARD, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)

    def _button(self, master, text, cmd, primary=False):
        return tk.Button(master, text=text, command=cmd, font=FONT_B if primary else FONT, relief="flat",
                         bg=GOLD if primary else CARD, fg="#111" if primary else TEXT,
                         activebackground=GOLD_DARK if primary else LINE, activeforeground=TEXT,
                         padx=18, pady=5, cursor="hand2", bd=0)

    def _entry(self, master, value, width=34, show=None):
        e = tk.Entry(master, font=FONT, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat", width=width,
                     highlightthickness=1, highlightbackground=LINE, highlightcolor=GOLD, show=show or "")
        e.insert(0, value)
        return e

    def _section(self, title, sub=None):
        f = tk.Frame(self.body, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        f.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(f, text=title, font=FONT_H, bg=PANEL, fg=TEXT).pack(anchor="w", padx=18, pady=(14, 0))
        if sub:
            tk.Label(f, text=sub, font=FONT_S, bg=PANEL, fg=MUTED, justify="left", wraplength=620).pack(anchor="w", padx=18)
        inner = tk.Frame(f, bg=PANEL)
        inner.pack(fill="x", padx=18, pady=(8, 14))
        inner.columnconfigure(0, weight=1)
        return inner

    def _row(self, sec, label, widget_fn, sub=None):
        r = sec.grid_size()[1]
        box = tk.Frame(sec, bg=PANEL)
        box.grid(row=r, column=0, sticky="we", pady=6)
        tk.Label(box, text=label, font=FONT, bg=PANEL, fg=TEXT).pack(anchor="w")
        if sub:
            tk.Label(box, text=sub, font=FONT_S, bg=PANEL, fg=MUTED, justify="left", wraplength=320).pack(anchor="w")
        w = widget_fn(sec)
        w.grid(row=r, column=1, sticky="e", pady=6, padx=(12, 0))
        return w

    def _combo(self, values, current, width=22):
        def make(master):
            cb = ttk.Combobox(master, values=values, state="readonly", width=width, font=FONT)
            cb.set(current)
            return cb
        return make

    # ------------------------------------------------------------ layout
    def _build(self):
        s = self.s
        tk.Label(self.body, text="Ascend InQ", font=("Yu Gothic UI", 20, "bold"), bg=BG, fg=GOLD).pack(anchor="w", padx=22, pady=(18, 0))
        tk.Label(self.body, text=t("s.heading"), font=FONT, bg=BG, fg=MUTED).pack(anchor="w", padx=22)

        # data source
        sec = self._section(t("s.data"), t("s.data_sub"))
        self.source = ChoiceCards(sec, [
            ("client", t("s.src_client"), t("s.src_client_sub")),
            ("api", t("s.src_api"), t("s.src_api_sub")),
        ], s["source"])
        self.source.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 6))
        for key, (card, dot, tt, sub) in self.source.cards.items():
            for w in (card, dot, tt, sub):
                w.bind("<Button-1>", lambda e, k=key: (self.source.select(k), self._show_api()), add="+")

        import os
        key = os.getenv("RIOT_API_KEY", "")
        key = "" if "xxxx" in key else key
        rid = config.riot_id()
        rid = "" if rid == "Name#JP1" else rid
        self.api_box = tk.Frame(sec, bg=PANEL)
        self.api_box.grid(row=1, column=0, columnspan=2, sticky="we")
        self.api_box.columnconfigure(0, weight=1)
        api = self.api_box

        def key_widget(master):
            f = tk.Frame(master, bg=PANEL)
            self.key = self._entry(f, key, width=30, show="•")
            self.key.pack(side="left")
            show = tk.Label(f, text=t("s.show"), font=FONT_S, bg=PANEL, fg=GOLD, cursor="hand2")
            show.pack(side="left", padx=(8, 0))
            show.bind("<Button-1>", lambda e: self.key.configure(show="" if self.key.cget("show") else "•"))
            return f
        self._row(api, t("s.api_key"), key_widget, t("s.api_key_sub"))
        link = tk.Label(api, text=t("s.get_key"), font=FONT_S, bg=PANEL, fg=GOLD, cursor="hand2")
        link.grid(row=api.grid_size()[1], column=0, sticky="w")
        link.bind("<Button-1>", lambda e: webbrowser.open("https://developer.riotgames.com/"))
        self.rid = self._row(api, "Riot ID", lambda m: self._entry(m, rid, width=30), t("s.riot_id_sub"))
        self.server_keys = list(config.SERVERS)
        labels = [label for label, _ in config.SERVERS.values()]
        cur = config.platform() if config.platform() in config.SERVERS else "jp1"
        self.server = self._row(api, t("s.server"), self._combo(labels, config.SERVERS[cur][0], 26))
        self._show_api()

        # recording
        sec = self._section(t("s.rec"), t("s.rec_sub"))
        self.capture = ChoiceCards(sec, [
            ("match", t("s.cap_match"), t("s.cap_match_sub")),
            ("off", t("s.cap_off"), t("s.cap_off_sub")),
        ], s["capture"])
        self.capture.grid(row=sec.grid_size()[1], column=0, columnspan=2, sticky="we", pady=(0, 6))

        def dir_widget(master):
            f = tk.Frame(master, bg=PANEL)
            self.save_dir = self._entry(f, s["save_dir"] or str(config.ROOT / "recordings"), width=30)
            self.save_dir.pack(side="left")
            self._button(f, t("s.browse"), self.pick_dir).pack(side="left", padx=(6, 0))
            return f
        self._row(sec, t("s.folder"), dir_widget)
        self.keep_values = [10, 20, 30, 50, 100, 0]
        keep_labels = [str(v) if v else t("s.unlimited") for v in self.keep_values]
        cur_keep = s["keep"] if s["keep"] in self.keep_values else 30
        self.keep = self._row(sec, t("s.keep"), self._combo(keep_labels, keep_labels[self.keep_values.index(cur_keep)], 10),
                              t("s.keep_sub"))
        self.quality_keys = list(config.QUALITY)
        q_labels = [t("q." + k) for k in self.quality_keys]
        cur_q = s["quality"] if s["quality"] in self.quality_keys else "standard"
        self.quality = self._row(sec, t("s.quality"), self._combo(q_labels, q_labels[self.quality_keys.index(cur_q)], 10),
                                 t("s.quality_sub"))
        self.fps = self._row(sec, t("s.fps"), self._combo(["30", "60"], str(s["fps"]), 10))
        try:
            n = max(1, ctypes.windll.user32.GetSystemMetrics(80))
        except Exception:
            n = 1
        monitors = [t("s.monitor_n", n=i + 1) + (t("s.main") if i == 0 else "") for i in range(n)]
        self.monitor = self._row(sec, t("s.monitor"), self._combo(monitors, monitors[min(int(s["monitor"]), n - 1)], 16))
        self.cursor = self._row(sec, t("s.cursor"), lambda m: Toggle(m, s["cursor"]))

        # after game
        sec = self._section(t("s.after"))
        self.auto_review = self._row(sec, t("s.auto_review"), lambda m: Toggle(m, s["auto_review"]), t("s.auto_review_sub"))
        self.open_viewer = self._row(sec, t("s.open_viewer"), lambda m: Toggle(m, s["open_viewer"]), t("s.open_viewer_sub"))

        # general
        sec = self._section(t("s.general"))
        self.lang_keys = ["auto", "ja", "en"]
        lang_labels = [t("s.lang_auto"), "日本語", "English"]
        cur_l = s.get("language", "auto") if s.get("language", "auto") in self.lang_keys else "auto"
        self.language = self._row(sec, t("s.language"), self._combo(lang_labels, lang_labels[self.lang_keys.index(cur_l)], 22))
        self.autostart = self._row(sec, t("s.autostart"), lambda m: Toggle(m, autostart.is_enabled()), t("s.autostart_sub"))
        self.notify = self._row(sec, t("s.notify"), lambda m: Toggle(m, s["notify"]), t("s.notify_sub"))
        tk.Frame(self.body, bg=BG, height=20).pack()

    # ------------------------------------------------------------ actions
    def _show_api(self):
        if self.source.get() == "api":
            self.api_box.grid()
        else:
            self.api_box.grid_remove()

    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_dir.get() or str(config.ROOT))
        if d:
            self.save_dir.delete(0, "end")
            self.save_dir.insert(0, d.replace("/", "\\"))

    def save(self):
        rid = self.rid.get().strip()
        if self.source.get() == "api" and (not rid or "#" not in rid):
            self.status.configure(text=t("s.err_riot_id"), fg="#ff7b7b")
            return
        platform = self.server_keys[max(0, self.server.current())]
        env = {"RIOT_ID": rid, "PLATFORM": platform, "REGION": config.SERVERS[platform][1]}
        key = self.key.get().strip()
        if key:
            env["RIOT_API_KEY"] = key
        config.write_env(env)

        save_dir = self.save_dir.get().strip()
        default_dir = str(config.ROOT / "recordings")
        s = dict(self.s)
        s.update({
            "source": self.source.get(),
            "capture": self.capture.get(),
            "save_dir": "" if save_dir in ("", default_dir) else save_dir,
            "keep": self.keep_values[max(0, self.keep.current())],
            "quality": self.quality_keys[max(0, self.quality.current())],
            "fps": int(self.fps.get()),
            "monitor": max(0, self.monitor.current()),
            "cursor": self.cursor.get(),
            "auto_review": self.auto_review.get(),
            "open_viewer": self.open_viewer.get(),
            "notify": self.notify.get(),
            "language": self.lang_keys[max(0, self.language.current())],
        })
        config.save_settings(s)
        try:
            autostart.set_enabled(self.autostart.get())
        except OSError as e:
            self.status.configure(text=t("s.err_autostart", e=e), fg="#ff7b7b")
            return
        self.status.configure(text=t("s.saved"), fg=GOLD)
        self.root.after(600, self.root.destroy)

    def run(self):
        self.root.mainloop()


def open_window():
    if sys.platform == "win32":
        ctypes.windll.kernel32.CreateMutexW(None, False, "AscendInQ_Settings")
        if ctypes.windll.kernel32.GetLastError() == 183:
            return  # already open
    SettingsWindow().run()
