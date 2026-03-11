import sys
import os
import re
import time
import json
import zlib
import struct
import random
import socket
import secrets
import threading
from datetime import datetime

# ── Guard: make sure tkinter is available ──────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, font as tkfont
except ImportError:
    print("ERROR: tkinter is not available. Please reinstall Python and make sure")
    print("'tcl/tk and IDLE' is checked during installation.")
    input("Press Enter to exit...")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  LOADING SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class LoadingScreen(tk.Tk):
    STEPS = [
        "Importing tkinter...",
        "Importing socket...",
        "Importing threading...",
        "Importing zlib (compression)...",
        "Importing secrets (encryption)...",
        "Importing json...",
        "Importing struct...",
        "Building colour palette...",
        "Initialising toggle widgets...",
        "Preparing settings panel...",
        "Loading transfer history...",
        "Building main UI...",
        "All systems ready ✓",
    ]

    def __init__(self):
        super().__init__()
        self.title("Packet Sender — Loading")
        self.resizable(False, False)
        self.configure(bg="#F6C1D1")
        self.overrideredirect(True)   # borderless window

        W, H = 420, 260
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        self._build()
        self._step = 0
        self._done = False
        self.after(120, self._tick)

    def _build(self):
        base = "Helvetica"
        for f in tkfont.families():
            if f in ("Nunito", "Quicksand", "Comfortaa"):
                base = f
                break

        outer = tk.Frame(self, bg="#F6C1D1", padx=32, pady=28)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="[ PACKET SENDER ]",
                 font=(base, 18, "bold"), fg="#FF5FA2", bg="#F6C1D1"
                 ).pack(anchor="w")

        tk.Label(outer, text="Initialising...",
                 font=(base, 9), fg="#6B5A63", bg="#F6C1D1"
                 ).pack(anchor="w", pady=(2, 14))

        # Progress bar
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Load.Horizontal.TProgressbar",
                         troughcolor="#F1B8CB", background="#FF5FA2",
                         thickness=10, borderwidth=0)
        self.bar = ttk.Progressbar(outer, style="Load.Horizontal.TProgressbar",
                                    mode="determinate", maximum=100)
        self.bar.pack(fill="x", pady=(0, 10))

        self.pct_lbl = tk.Label(outer, text="0%",
                                 font=(base, 9, "bold"), fg="#FF5FA2", bg="#F6C1D1")
        self.pct_lbl.pack(anchor="e")

        self.step_lbl = tk.Label(outer, text="",
                                  font=("Courier New", 9), fg="#6B5A63", bg="#F6C1D1",
                                  anchor="w", justify="left")
        self.step_lbl.pack(anchor="w", pady=(8, 0))

    def _tick(self):
        if self._step >= len(self.STEPS):
            self._done = True
            self.destroy()
            return
        label = self.STEPS[self._step]
        pct   = int((self._step / len(self.STEPS)) * 100)
        self.bar["value"] = pct
        self.pct_lbl.config(text=f"{pct}%")
        self.step_lbl.config(text=f"  > {label}")
        self._step += 1
        delay = 80 if self._step < len(self.STEPS) else 300
        self.after(delay, self._tick)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def xor_encrypt(data: bytes, key: bytes) -> bytes:
    kl = len(key)
    return bytes(b ^ key[i % kl] for i, b in enumerate(data))

def generate_key(n=32) -> bytes:
    return secrets.token_bytes(n)

stop_event = threading.Event()
kill_event = threading.Event()
sent   = 0
errors = 0
lock   = threading.Lock()
HISTORY_FILE = os.path.join(os.path.expanduser("~"), "Desktop", "transfer_history.json")

def is_valid_ip(ip):
    if not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", ip):
        return False
    return all(0 <= int(x) <= 255 for x in ip.split("."))

def is_valid_port(s):
    try:
        return 1 <= int(str(s).strip()) <= 9999
    except:
        return False

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE) as f:
                return json.load(f)
    except:
        pass
    return []

def save_history(entry):
    try:
        h = load_history()
        h.append(entry)
        with open(HISTORY_FILE, "w") as f:
            json.dump(h[-100:], f, indent=2)
    except:
        pass

def send_chunk(ip, port, packet):
    global sent, errors
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 131072)
        s.sendto(packet, (ip, port))
        s.close()
        with lock:
            sent += 1
    except:
        with lock:
            errors += 1


# ══════════════════════════════════════════════════════════════════════════════
#  ANIMATED TOGGLE
# ══════════════════════════════════════════════════════════════════════════════
class AnimatedToggle(tk.Canvas):
    def __init__(self, parent, variable, bg="#FDE8EF", **kw):
        self.W, self.H = 44, 24
        super().__init__(parent, width=self.W, height=self.H,
                         bg=bg, highlightthickness=0, cursor="hand2", **kw)
        self._var  = variable
        self._pos  = 1.0 if variable.get() else 0.0
        self._anim = None
        self._draw()
        self.bind("<ButtonRelease-1>", lambda e: self._var.set(not self._var.get()))
        variable.trace_add("write", self._sync)

    def _sync(self, *_):
        self._animate(1.0 if self._var.get() else 0.0)

    def _animate(self, target):
        if self._anim:
            try: self.after_cancel(self._anim)
            except: pass
        def step():
            diff = target - self._pos
            if abs(diff) < 0.04:
                self._pos = target
                self._draw()
                return
            self._pos += diff * 0.22
            self._draw()
            self._anim = self.after(14, step)
        step()

    def _draw(self):
        self.delete("all")
        t   = max(0.0, min(1.0, self._pos))
        col = self._lerp("#D4A8B8", "#FF5FA2", t)
        r   = self.H // 2
        self.create_oval(0, 0, self.H, self.H, fill=col, outline="")
        self.create_oval(self.W-self.H, 0, self.W, self.H, fill=col, outline="")
        self.create_rectangle(r, 0, self.W-r, self.H, fill=col, outline="")
        pad = 3
        kx  = pad + t * (self.W - self.H)
        self.create_oval(kx, pad, kx+self.H-pad*2, self.H-pad, fill="white", outline="")

    @staticmethod
    def _lerp(a, b, t):
        ar,ag,ab_ = int(a[1:3],16),int(a[3:5],16),int(a[5:7],16)
        br,bg_,bb = int(b[1:3],16),int(b[3:5],16),int(b[5:7],16)
        return "#{:02x}{:02x}{:02x}".format(
            int(ar+(br-ar)*t), int(ag+(bg_-ag)*t), int(ab_+(bb-ab_)*t))


# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS PANEL
# ══════════════════════════════════════════════════════════════════════════════
class SettingsPanel:
    """Stores settings vars. Opens a popup window when open() is called."""
    OPTS = [
        ("strip_meta",    "Strip identifying metadata",     True),
        ("random_timing", "Randomize packet timing & size", False),
        ("random_pad",    "Random padding on each packet",  False),
        ("enc_headers",   "Encrypted headers",              True),
        ("random_order",  "Random send order",              False),
    ]

    def __init__(self):
        self.vars = {k: tk.BooleanVar(value=d) for k, _, d in self.OPTS}
        self.loop_var = tk.BooleanVar(value=False)
        self._win = None

    def open(self, parent):
        # If already open, just bring it to front
        if self._win and tk.Toplevel.winfo_exists(self._win):
            self._win.lift()
            self._win.focus_force()
            return

        bg   = "#FDE8EF"
        base = "Helvetica"

        win = tk.Toplevel(parent)
        win.title("Settings")
        win.configure(bg=bg)
        win.resizable(False, False)
        win.grab_set()   # modal
        self._win = win

        # Centre over parent
        parent.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width()  // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        W, H = 360, 280
        win.geometry(f"{W}x{H}+{px - W//2}+{py - H//2}")

        # Header
        hdr = tk.Frame(win, bg="#FF5FA2", padx=20, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Privacy & Security", font=(base,13,"bold"),
                 fg="white", bg="#FF5FA2").pack(anchor="w")
        tk.Label(hdr, text="These settings apply to every transfer",
                 font=(base,8), fg="#FFD0E8", bg="#FF5FA2").pack(anchor="w")

        # Options
        body = tk.Frame(win, bg=bg, padx=20, pady=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        for key, label, _ in self.OPTS:
            v   = self.vars[key]
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x", pady=6)
            row.columnconfigure(0, weight=1)
            tk.Label(row, text=label, font=(base,10),
                     fg="#2B2B2F", bg=bg, anchor="w").grid(row=0, column=0, sticky="w")
            AnimatedToggle(row, v, bg=bg).grid(row=0, column=1, sticky="e")

        # Loop mode (separate section)
        sep = tk.Frame(body, bg="#FF8FC4", height=1)
        sep.pack(fill="x", pady=(6, 10))

        loop_row = tk.Frame(body, bg=bg)
        loop_row.pack(fill="x", pady=2)
        loop_row.columnconfigure(0, weight=1)
        tk.Label(loop_row, text="Loop mode  (sends file on repeat)", font=(base,10,"bold"),
                 fg="#FF5FA2", bg=bg, anchor="w").grid(row=0, column=0, sticky="w")
        AnimatedToggle(loop_row, self.loop_var, bg=bg).grid(row=0, column=1, sticky="e")
        tk.Label(body, text="⚠  Will keep sending until you press Stop",
                 font=(base, 8), fg="#9C7A86", bg=bg, anchor="w").pack(anchor="w", pady=(2,0))

        # Close button
        tk.Button(win, text="Done", font=(base,11,"bold"),
                  bg="#FF5FA2", fg="white",
                  activebackground="#e04d8e", activeforeground="white",
                  relief="flat", bd=0, cursor="hand2",
                  command=win.destroy).pack(fill="x", padx=20, pady=(0,16), ipady=8)

    def get(self):
        d = {k: v.get() for k, v in self.vars.items()}
        d["loop"] = self.loop_var.get()
        return d


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
C = {
    "bg":"#F6C1D1","card":"#FAD7E2","input_bg":"#FFF4F7",
    "text":"#2B2B2F","text2":"#6B5A63","text_dis":"#9C7A86",
    "accent":"#FF5FA2","border_id":"#FF8FC4","border_fo":"#FF5FA2",
    "btn_start":"#FF5FA2","btn_stop":"#FF4D6D","btn_kill":"#7a0000",
    "btn_browse":"#E8B9D0","prog_track":"#F1B8CB","prog_fill":"#FF5FA2",
    "status_ok":"#D63C87","status_err":"#FF4D6D","white":"#FFFFFF",
}

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Packet Sender")
        self.configure(bg=C["bg"])
        self.minsize(460, 680)

        avail = list(tkfont.families())
        base  = next((f for f in ["Nunito","Quicksand","Comfortaa"] if f in avail), "Helvetica")
        self.F = {
            "title": (base,16,"bold"), "label": (base,10,"bold"),
            "body":  (base,11),        "small": (base,9),
            "btn":   (base,11,"bold"), "mono":  ("Courier New",9),
        }

        self._sending      = False
        self._file_path    = None
        self._send_thread  = None
        self._pps_last     = 0
        self._pps_time     = time.perf_counter()
        self._total_chunks = 0

        self._build_ui()
        self._tick()

    def _build_ui(self):
        outer = tk.Frame(self, bg=C["bg"], padx=24, pady=20)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        r = 0

        # Title + settings btn
        hdr = tk.Frame(outer, bg=C["bg"])
        hdr.grid(row=r, column=0, sticky="ew", pady=(0,12))
        hdr.columnconfigure(0, weight=1)
        tk.Label(hdr, text="[ PACKET SENDER ]", font=self.F["title"],
                 fg=C["accent"], bg=C["bg"]).grid(row=0, column=0, sticky="w")
        self._arrow = tk.StringVar(value="⚙  Settings")
        tk.Button(hdr, textvariable=self._arrow, font=self.F["small"],
                  bg=C["btn_browse"], fg=C["text"], activebackground="#DFA2C3",
                  relief="flat", bd=0, padx=10, cursor="hand2",
                  command=self._toggle_settings
                  ).grid(row=0, column=1, sticky="e", ipady=4)
        r += 1

        # Settings panel (popup, no widget in main window)
        self.settings_panel = SettingsPanel()
        r  # no grid row needed

        # Kill switch
        tk.Button(outer, text="☠  KILL SWITCH — TERMINATE EVERYTHING",
                  font=self.F["btn"], bg=C["btn_kill"], fg=C["white"],
                  activebackground="#4a0000", relief="flat", bd=0,
                  padx=10, cursor="hand2", command=self._kill
                  ).grid(row=r, column=0, sticky="ew", ipady=11, pady=(0,12))
        r += 1

        # Speed test
        self.speedtest_btn = tk.Button(outer, text="⚡  Run Network Speed Test",
                                        font=self.F["small"], bg=C["btn_browse"], fg=C["text"],
                                        activebackground="#DFA2C3", relief="flat", bd=0,
                                        padx=10, cursor="hand2", command=self._run_speed_test)
        self.speedtest_btn.grid(row=r, column=0, sticky="ew", ipady=6, pady=(0,2))
        r += 1
        self.speed_lbl = tk.Label(outer, text="", font=self.F["small"],
                                   fg=C["text2"], bg=C["bg"])
        self.speed_lbl.grid(row=r, column=0, sticky="w", pady=(0,10))
        r += 1

        # IP
        tk.Label(outer, text="TARGET IP", font=self.F["label"],
                 fg=C["text2"], bg=C["bg"]).grid(row=r, column=0, sticky="w")
        r += 1
        self.ip_border = tk.Frame(outer, bg=C["border_id"], padx=2, pady=2)
        self.ip_border.grid(row=r, column=0, sticky="ew", pady=(2,0))
        self.ip_border.columnconfigure(0, weight=1)
        self.ip_var = tk.StringVar()
        self.ip_var.trace_add("write", self._validate)
        ip_e = tk.Entry(self.ip_border, textvariable=self.ip_var, font=self.F["body"],
                        bg=C["input_bg"], fg=C["text"], insertbackground=C["accent"],
                        relief="flat", bd=0)
        ip_e.grid(row=0, column=0, sticky="ew", ipady=8, padx=8)
        ip_e.bind("<FocusIn>",  lambda e: self.ip_border.config(bg=C["border_fo"]))
        ip_e.bind("<FocusOut>", lambda e: self._validate())
        r += 1
        self.ip_msg = tk.Label(outer, text="", font=self.F["small"],
                                bg=C["bg"], fg=C["status_err"])
        self.ip_msg.grid(row=r, column=0, sticky="w", pady=(2,8))
        r += 1

        # Port
        tk.Label(outer, text="PORT  (1 – 9999)", font=self.F["label"],
                 fg=C["text2"], bg=C["bg"]).grid(row=r, column=0, sticky="w")
        r += 1
        self.port_border = tk.Frame(outer, bg=C["border_id"], padx=2, pady=2)
        self.port_border.grid(row=r, column=0, sticky="ew", pady=(2,0))
        self.port_border.columnconfigure(0, weight=1)
        self.port_var = tk.StringVar(value="53")
        self.port_var.trace_add("write", self._validate)
        port_e = tk.Entry(self.port_border, textvariable=self.port_var, font=self.F["body"],
                          bg=C["input_bg"], fg=C["text"], insertbackground=C["accent"],
                          relief="flat", bd=0)
        port_e.grid(row=0, column=0, sticky="ew", ipady=8, padx=8)
        port_e.bind("<FocusIn>",  lambda e: self.port_border.config(bg=C["border_fo"]))
        port_e.bind("<FocusOut>", lambda e: self._validate())
        r += 1
        self.port_msg = tk.Label(outer, text="", font=self.F["small"],
                                  bg=C["bg"], fg=C["status_err"])
        self.port_msg.grid(row=r, column=0, sticky="w", pady=(2,8))
        r += 1

        # File
        tk.Label(outer, text="FILE", font=self.F["label"],
                 fg=C["text2"], bg=C["bg"]).grid(row=r, column=0, sticky="w")
        r += 1
        fc = tk.Frame(outer, bg=C["card"], padx=10, pady=8)
        fc.grid(row=r, column=0, sticky="ew", pady=(4,10))
        fc.columnconfigure(0, weight=1)
        self.file_lbl = tk.Label(fc, text="No file selected", font=self.F["small"],
                                  fg=C["text_dis"], bg=C["card"], anchor="w")
        self.file_lbl.grid(row=0, column=0, sticky="ew")
        tk.Button(fc, text="Browse", font=self.F["small"],
                  bg=C["btn_browse"], fg=C["text"], activebackground="#DFA2C3",
                  relief="flat", bd=0, padx=14, cursor="hand2",
                  command=self._browse).grid(row=0, column=1, padx=(10,0), ipady=4)
        r += 1

        # Core toggles
        tog_row = tk.Frame(outer, bg=C["bg"])
        tog_row.grid(row=r, column=0, sticky="ew", pady=(0,10))
        self.compress_var = tk.BooleanVar(value=True)
        self.encrypt_var  = tk.BooleanVar(value=True)
        for lbl, var in [("Compression", self.compress_var), ("Encryption", self.encrypt_var)]:
            f = tk.Frame(tog_row, bg=C["bg"])
            f.pack(side="left", padx=(0,20))
            tk.Label(f, text=lbl, font=self.F["small"],
                     fg=C["text"], bg=C["bg"]).pack(side="left", padx=(0,6))
            AnimatedToggle(f, var, bg=C["bg"]).pack(side="left")
        r += 1

        # Start / Stop
        bf = tk.Frame(outer, bg=C["bg"])
        bf.grid(row=r, column=0, sticky="ew", pady=(0,10))
        bf.columnconfigure(0, weight=1)
        bf.columnconfigure(1, weight=1)
        self.start_btn = tk.Button(bf, text="▶  START SENDING", font=self.F["btn"],
                                    bg=C["btn_start"], fg=C["white"],
                                    activebackground="#e04d8e", relief="flat", bd=0,
                                    padx=10, cursor="hand2", command=self._start,
                                    state="disabled")
        self.start_btn.grid(row=0, column=0, sticky="ew", ipady=10, padx=(0,6))
        self.stop_btn = tk.Button(bf, text="■  STOP", font=self.F["btn"],
                                   bg=C["btn_stop"], fg=C["white"],
                                   activebackground="#E63B59", relief="flat", bd=0,
                                   padx=10, cursor="hand2", command=self._stop,
                                   state="disabled")
        self.stop_btn.grid(row=0, column=1, sticky="ew", ipady=10, padx=(6,0))
        r += 1

        # Stats bar
        sf = tk.Frame(outer, bg=C["card"], padx=10, pady=6)
        sf.grid(row=r, column=0, sticky="ew", pady=(0,8))
        sf.columnconfigure((0,1,2), weight=1)
        self.lbl_pps  = tk.Label(sf, text="PPS: —",  font=self.F["small"], fg=C["text2"], bg=C["card"])
        self.lbl_eta  = tk.Label(sf, text="ETA: —",  font=self.F["small"], fg=C["text2"], bg=C["card"])
        self.lbl_sent = tk.Label(sf, text="Sent: 0", font=self.F["small"], fg=C["text2"], bg=C["card"])
        self.lbl_pps.grid(row=0, column=0, sticky="w")
        self.lbl_eta.grid(row=0, column=1)
        self.lbl_sent.grid(row=0, column=2, sticky="e")
        r += 1

        # Progress
        tk.Label(outer, text="PROGRESS", font=self.F["label"],
                 fg=C["text2"], bg=C["bg"]).grid(row=r, column=0, sticky="w")
        r += 1
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("HK.Horizontal.TProgressbar",
                         troughcolor=C["prog_track"], background=C["prog_fill"],
                         thickness=16, borderwidth=0)
        self.progress = ttk.Progressbar(outer, style="HK.Horizontal.TProgressbar",
                                         mode="determinate")
        self.progress.grid(row=r, column=0, sticky="ew", pady=(4,10))
        r += 1

        # Log header
        lh = tk.Frame(outer, bg=C["bg"])
        lh.grid(row=r, column=0, sticky="ew")
        lh.columnconfigure(0, weight=1)
        tk.Label(lh, text="LOG", font=self.F["label"],
                 fg=C["text2"], bg=C["bg"]).grid(row=0, column=0, sticky="w")
        tk.Button(lh, text="View History", font=self.F["small"],
                  bg=C["btn_browse"], fg=C["text"], activebackground="#DFA2C3",
                  relief="flat", bd=0, padx=8, cursor="hand2",
                  command=self._show_history).grid(row=0, column=1, sticky="e", ipady=2)
        r += 1

        lf = tk.Frame(outer, bg=C["card"], padx=2, pady=2)
        lf.grid(row=r, column=0, sticky="nsew", pady=(4,0))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        outer.rowconfigure(r, weight=1)

        self.log_box = tk.Text(lf, font=self.F["mono"], bg=C["card"], fg=C["status_ok"],
                                relief="flat", bd=0, state="disabled",
                                cursor="arrow", wrap="word", padx=8, pady=6)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.log_box.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_box.configure(yscrollcommand=sb.set)

        self._log("Ready. Enter an IP, set a port, and select a file.")

    # ── settings ───────────────────────────────────────────────────────────────
    def _toggle_settings(self):
        self.settings_panel.open(self)

    # ── live tick ──────────────────────────────────────────────────────────────
    def _tick(self):
        try:
            if self._sending and self._total_chunks > 0:
                now     = time.perf_counter()
                elapsed = now - self._pps_time
                if elapsed >= 1.0:
                    cur  = sent
                    pps  = int((cur - self._pps_last) / elapsed)
                    self._pps_last = cur
                    self._pps_time = now
                    rem  = self._total_chunks - cur
                    eta  = f"{int(rem/pps)}s" if pps > 0 else "—"
                    self.lbl_pps.config(text=f"PPS: {pps:,}")
                    self.lbl_eta.config(text=f"ETA: {eta}")
                    self.lbl_sent.config(text=f"Sent: {cur:,}")
        except Exception:
            pass
        self.after(500, self._tick)

    # ── kill ───────────────────────────────────────────────────────────────────
    def _kill(self):
        kill_event.set()
        stop_event.set()
        os.kill(os.getpid(), 9)

    # ── speed test ─────────────────────────────────────────────────────────────
    def _run_speed_test(self):
        self.speed_lbl.config(text="Testing...")
        self.speedtest_btn.config(state="disabled")
        def _test():
            try:
                payload = b"X" * 1024
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 131072)
                count = 500
                t0 = time.perf_counter()
                for _ in range(count):
                    try: s.sendto(payload, ("8.8.8.8", 9999))
                    except: pass
                elapsed = time.perf_counter() - t0
                s.close()
                pps  = int(count / elapsed)
                mbps = round(pps * 1024 / 1048576, 2)
                res  = f"~{pps:,} PPS  |  ~{mbps} MB/s estimated"
            except Exception as e:
                res = f"Speed test failed: {e}"
            self.after(0, lambda: self.speed_lbl.config(text=res))
            self.after(0, lambda: self.speedtest_btn.config(state="normal"))
        threading.Thread(target=_test, daemon=True).start()

    # ── validation ─────────────────────────────────────────────────────────────
    def _validate(self, *_):
        ip = self.ip_var.get().strip()
        ps = self.port_var.get().strip()
        if ip and not is_valid_ip(ip):
            self.ip_msg.config(text="⚠  Invalid IP address")
            self.ip_border.config(bg=C["status_err"])
        else:
            self.ip_msg.config(text="")
            self.ip_border.config(bg=C["border_fo"] if ip else C["border_id"])
        if ps and not is_valid_port(ps):
            self.port_msg.config(text="⚠  Port must be between 1 and 9999")
            self.port_border.config(bg=C["status_err"])
        else:
            self.port_msg.config(text="")
            self.port_border.config(bg=C["border_fo"] if ps else C["border_id"])
        self._update_btn()

    def _browse(self):
        path = filedialog.askopenfilename()
        if path:
            self._file_path = path
            self.file_lbl.config(text=os.path.basename(path), fg=C["text"])
            self._update_btn()

    def _update_btn(self):
        ok = (is_valid_ip(self.ip_var.get().strip()) and
              is_valid_port(self.port_var.get().strip()) and
              self._file_path is not None and
              not self._sending)
        self.start_btn.config(state="normal" if ok else "disabled")

    def _log(self, msg):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ── send ───────────────────────────────────────────────────────────────────
    def _start(self):
        global sent, errors
        sent = errors = 0
        stop_event.clear()
        kill_event.clear()
        self._sending      = True
        self._pps_last     = 0
        self._pps_time     = time.perf_counter()
        self._total_chunks = 0
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress["value"] = 0

        ip   = self.ip_var.get().strip()
        port = int(self.port_var.get().strip())
        priv = self.settings_panel.get()
        uc   = self.compress_var.get()
        ue   = self.encrypt_var.get()

        loop = priv.get("loop", False)
        self._log(f"Sending → {ip}:{port}" + ("  [LOOP MODE]" if loop else ""))
        self._send_thread = threading.Thread(
            target=self._worker, args=(ip, port, uc, ue, priv), daemon=True)
        self._send_thread.start()

    def _stop(self):
        stop_event.set()
        self._log("Stopping...")
        self.stop_btn.config(state="disabled")

    def _worker(self, ip, port, uc, ue, priv):
        try:
            loop      = priv.get("loop", False)
            run_count = 0
            fname = os.path.basename(self._file_path)
            with open(self._file_path, "rb") as f:
                raw = f.read()

            data = zlib.compress(raw, level=6) if uc else raw
            key  = generate_key(32) if ue else b"\x00"

            chunk_size = 58000
            num        = (len(data) + chunk_size - 1) // chunk_size
            self._total_chunks = num
            t0 = time.perf_counter()

            self.after(0, lambda: self._log(
                f"File: {fname}  |  {len(raw)/1024:.1f} KB  |  {num} chunks" +
                ("  |  LOOP ON" if loop else "")))

            while True:
                run_count += 1
                if loop:
                    self.after(0, lambda c=run_count: self._log(f"↻ Loop #{c}"))
                self.after(0, lambda: self.progress.configure(value=0))

                packets = []
                for idx in range(num):
                    if stop_event.is_set(): break
                    chunk = data[idx*chunk_size:(idx+1)*chunk_size]
                    if priv.get("random_pad"):
                        chunk += secrets.token_bytes(random.randint(0, 64))
                    payload   = xor_encrypt(chunk, key) if ue else chunk
                    fb        = (b"data" if priv.get("strip_meta")
                                 else fname.encode("utf-8"))
                    if priv.get("enc_headers"):
                        fb = xor_encrypt(fb, key)
                    header = struct.pack(">4s I I H H", b"PKTS", idx, num, len(fb), len(key))
                    packets.append(header + fb + key + payload)

                if priv.get("random_order"):
                    random.shuffle(packets)

                threads = []
                for idx, pkt in enumerate(packets):
                    if stop_event.is_set() or kill_event.is_set(): break
                    if priv.get("random_timing"):
                        time.sleep(random.uniform(0.0, 0.002))
                    t = threading.Thread(target=send_chunk, args=(ip, port, pkt), daemon=True)
                    t.start()
                    threads.append(t)
                    if idx % 50 == 0:
                        pct = idx / num * 100
                        self.after(0, lambda v=pct: self.progress.configure(value=v))

                for t in threads: t.join()

                if kill_event.is_set() or stop_event.is_set():
                    break

                self.after(0, lambda: self.progress.configure(value=100))

                if not loop:
                    break
                # loop — reset for next iteration
                stop_event.clear()

            if kill_event.is_set(): return

            elapsed = time.perf_counter() - t0
            mb      = len(raw) / 1048576
            self.after(0, lambda: self.progress.configure(value=100))
            self.after(0, lambda: self.lbl_eta.config(text="ETA: Done ✓"))
            self.after(0, lambda: self._log(
                f"✓ Done {elapsed:.2f}s  |  Sent: {sent}  |  Errors: {errors}  |  {mb/elapsed:.2f} MB/s"))

            save_history({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "file": fname, "target": f"{ip}:{port}",
                "size_kb": round(len(raw)/1024,2), "chunks": num,
                "sent": sent, "errors": errors,
                "elapsed": round(elapsed,2), "mbps": round(mb/elapsed,2),
                "encrypted": ue, "compressed": uc, "privacy": priv,
            })
        except Exception as e:
            self.after(0, lambda: self._log(f"✗ Error: {e}"))
        finally:
            self._sending = False
            stop_event.set()
            self.after(0, self._done)

    def _done(self):
        self.stop_btn.config(state="disabled")
        self._update_btn()

    # ── history ────────────────────────────────────────────────────────────────
    def _show_history(self):
        history = load_history()
        win = tk.Toplevel(self)
        win.title("Transfer History")
        win.configure(bg=C["bg"])
        win.minsize(560, 300)
        tk.Label(win, text="Transfer History", font=self.F["title"],
                 fg=C["accent"], bg=C["bg"]).pack(anchor="w", padx=16, pady=(16,8))
        fr = tk.Frame(win, bg=C["card"], padx=2, pady=2)
        fr.pack(fill="both", expand=True, padx=16, pady=(0,16))
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(0, weight=1)
        box = tk.Text(fr, font=self.F["mono"], bg=C["card"], fg=C["text"],
                      relief="flat", bd=0, padx=8, pady=6, wrap="none")
        box.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(fr, orient="vertical", command=box.yview)
        sb.grid(row=0, column=1, sticky="ns")
        box.configure(yscrollcommand=sb.set)
        if not history:
            box.insert("end", "No transfers recorded yet.")
        else:
            for h in reversed(history):
                enc = "🔒" if h.get("encrypted")  else "  "
                cmp = "📦" if h.get("compressed") else "  "
                prv = "🕵" if any(h.get("privacy",{}).values()) else "  "
                box.insert("end",
                    f"{h['time']}  {enc}{cmp}{prv}  {h['file']}  →  {h['target']}"
                    f"  |  {h['size_kb']} KB  |  {h['sent']} chunks"
                    f"  |  {h['elapsed']}s  |  {h['mbps']} MB/s\n")
        box.config(state="disabled")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        splash = LoadingScreen()
        splash.mainloop()
        app = App()
        app.mainloop()
    except Exception as e:
        # If anything goes wrong show a visible error instead of silent crash
        try:
            root = tk.Tk()
            root.withdraw()
            from tkinter import messagebox
            messagebox.showerror("Startup Error", str(e))
            root.destroy()
        except:
            print(f"FATAL ERROR: {e}")
            input("Press Enter to exit...")
        sys.exit(1)