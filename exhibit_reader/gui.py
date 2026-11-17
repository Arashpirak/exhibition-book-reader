"""Tkinter operator window for the exhibition reader (ttk only, no extra deps).

Layout, top to bottom: source/output card, collapsible advanced options, one primary action
with progress + time remaining, then the results (searchable, sortable table with a detail
pane and "needs review" highlighting) and the run log.
"""
from __future__ import annotations

import glob
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from tkinter import filedialog, messagebox, ttk

from .models import Settings

SETTINGS_FILE = "settings.json"
# (field, heading, width, stretch)
RESULT_COLUMNS = [
    ("page_no", "Page", 50, False), ("booth", "Booth", 150, False),
    ("name_en", "Name (EN)", 250, True), ("name_cn", "Name (CN)", 190, True),
    ("tel", "Tel", 120, False), ("email", "E-mail", 180, True), ("url", "Website", 150, True),
    ("confidence", "Conf.", 55, False),
]
DETAIL_FIELDS = [
    ("booth", "Booth"), ("name_cn", "Name (CN)"), ("name_en", "Name (EN)"),
    ("address_cn", "Address (CN)"), ("postcode", "Postcode"), ("address_en", "Address (EN)"),
    ("tel", "Tel"), ("fax", "Fax"), ("email", "E-mail"), ("url", "Website"),
    ("category_en", "Category"), ("category_cn", "类别"), ("area", "Area"), ("page_no", "Page"),
    ("source_image", "Photo"), ("confidence", "Confidence"),
]
MAX_ROWS = 5000          # cap rows rendered in the table
REVIEW_BELOW = 0.90      # mean OCR confidence under this is flagged for review

BG, CARD, INK, MUTED, LINE = "#f5f5f7", "#ffffff", "#1d1d1f", "#6e6e73", "#d2d2d7"
ACCENT, ACCENT_DOWN, WARN_BG, WARN_INK, STRIPE = "#0071e3", "#0060c0", "#fff4d6", "#8a5a00", "#fafafc"


def review_reasons(r) -> list[str]:
    """Why an operator should look at this record again (empty list = looks fine)."""
    out = []
    if not r.booth:
        out.append("no booth code")
    if not r.name_cn:
        out.append("no Chinese name")
    if not r.name_en:
        out.append("no English name")
    if not (r.address_cn or r.address_en):
        out.append("no address")
    if r.email and ("@" not in r.email or "." not in r.email.split("@")[-1]):
        out.append("e-mail looks wrong")
    if r.confidence and r.confidence < REVIEW_BELOW:
        out.append(f"low OCR confidence ({r.confidence:.2f})")
    return out


def _fmt_secs(s: float) -> str:
    s = int(max(s, 0))
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"


def _load_settings() -> Settings:
    try:
        from . import settings_store
        return settings_store.load(SETTINGS_FILE)
    except Exception:
        return Settings()


class App:
    def __init__(self, root: tk.Tk, settings: Settings | None = None):
        self.root = root
        root.title("Exhibition Book Reader")
        root.geometry("1120x780")
        root.minsize(900, 640)
        root.configure(bg=BG)
        self.q: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker: threading.Thread | None = None
        self.records: list = []
        self._row_rec: dict[str, object] = {}
        self._sort: tuple[str, bool] | None = None
        self._t0 = 0.0
        self._count_job = None
        self._written: list[str] = []
        self._init_style()
        self._init_vars(settings or _load_settings())
        self._build()
        self._set_running(False)
        self._refresh_count()
        root.bind("<F5>", lambda e: self.start())
        root.bind("<Escape>", lambda e: self.stop())
        root.bind("<Control-f>", lambda e: (self.nb.select(0), self.ent_filter.focus_set()))
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)

    # ---------- setup ----------
    def _init_style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(family="Segoe UI", size=10)
        for name in ("TkTextFont", "TkHeadingFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass
        st.configure(".", background=BG, foreground=INK, bordercolor=LINE, lightcolor=CARD, darkcolor=LINE,
                     focuscolor=ACCENT)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1)
        st.configure("Inner.TFrame", background=CARD)
        st.configure("TLabel", background=BG)
        st.configure("Card.TLabel", background=CARD)
        st.configure("Title.TLabel", font=("Segoe UI Semibold", 17), background=BG)
        st.configure("Hint.TLabel", foreground=MUTED, background=BG)
        st.configure("CardHint.TLabel", foreground=MUTED, background=CARD)
        st.configure("Section.TLabel", font=("Segoe UI Semibold", 10), background=CARD)
        st.configure("Warn.TLabel", foreground=WARN_INK, background=BG)
        st.configure("TCheckbutton", background=CARD)
        st.map("TCheckbutton", background=[("active", CARD)])
        st.configure("Plain.TCheckbutton", background=BG)
        st.map("Plain.TCheckbutton", background=[("active", BG)])
        st.configure("TButton", padding=(12, 5), background=CARD)
        st.map("TButton", background=[("active", "#ececf0"), ("disabled", BG)])
        st.configure("Accent.TButton", padding=(22, 7), font=("Segoe UI Semibold", 10),
                     background=ACCENT, foreground="#ffffff", bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        st.map("Accent.TButton", background=[("disabled", "#a9c9ee"), ("pressed", ACCENT_DOWN), ("active", "#1a82ea")],
               foreground=[("disabled", "#ffffff")], bordercolor=[("disabled", "#a9c9ee")])
        st.configure("Link.TButton", padding=(4, 2), background=BG, foreground=ACCENT, borderwidth=0)
        st.map("Link.TButton", background=[("active", BG)], foreground=[("active", ACCENT_DOWN)])
        st.configure("TEntry", fieldbackground="#ffffff", padding=4)
        st.configure("TCombobox", fieldbackground="#ffffff", padding=3)
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e5e5ea", bordercolor="#e5e5ea",
                     lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(16, 6), background=BG)
        st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", INK), ("!selected", MUTED)])
        row_h = tkfont.Font(font=base).metrics("linespace") + 10
        st.configure("Treeview", rowheight=row_h, background=CARD, fieldbackground=CARD, borderwidth=0)
        st.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), background="#f0f0f3", padding=(6, 5))
        st.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])

    def _init_vars(self, s: Settings):
        self.v = {
            "input_folder": tk.StringVar(value=s.input_folder),
            "file_pattern": tk.StringVar(value=s.file_pattern),
            "output_folder": tk.StringVar(value=s.output_folder),
            "output_basename": tk.StringVar(value=s.output_basename),
            "export_excel": tk.BooleanVar(value=s.export_excel),
            "export_access": tk.BooleanVar(value=s.export_access),
            "ocr_engine": tk.StringVar(value=s.ocr_engine),
            "claude_model": tk.StringVar(value=s.claude_model),
            "min_confidence": tk.StringVar(value=str(s.min_confidence)),
            "header_ratio": tk.StringVar(value=str(s.header_ratio)),
            "footer_ratio": tk.StringVar(value=str(s.footer_ratio)),
            "side_tab_ratio": tk.StringVar(value=str(s.side_tab_ratio)),
            "column_split": tk.StringVar(value=str(s.column_split)),
            "merge_continuations": tk.BooleanVar(value=s.merge_continuations),
            "save_debug_text": tk.BooleanVar(value=s.save_debug_text),
        }
        for k in ("input_folder", "output_folder"):  # show real paths, not "."
            self.v[k].set(os.path.abspath(self.v[k].get() or "."))
        try:
            from .exporters import access_available
            self.access_ok = access_available()
        except Exception:
            self.access_ok = False
        if not self.access_ok:
            self.v["export_access"].set(False)
        try:
            import anthropic  # noqa: F401
            self.claude_ok = True
        except Exception:
            self.claude_ok = False
        if not self.claude_ok:
            self.v["ocr_engine"].set("rapidocr")
        self._base = s  # keeps fields not shown in the UI (keep_raw_text, workers)
        self.v_filter = tk.StringVar()
        self.v_review_only = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready.")
        self.eta = tk.StringVar(value="")
        self.count = tk.StringVar(value="")
        self.summary = tk.StringVar(value="No results yet — choose a folder of catalog photos and press Start.")

    def _build(self):
        outer = ttk.Frame(self.root, padding=(18, 14, 18, 14))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        head = ttk.Frame(outer)
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="Exhibition Book Reader", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="Catalog photos  →  Excel / Access", style="Hint.TLabel").pack(side="left", padx=12,
                                                                                         pady=(6, 0))

        # ---- source / output card
        card = ttk.Frame(outer, style="Card.TFrame", padding=14)
        card.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        card.columnconfigure(1, weight=1)
        L = lambda t, r, c=0, **kw: ttk.Label(card, text=t, style="Card.TLabel").grid(  # noqa: E731
            row=r, column=c, sticky="w", pady=4, **kw)
        L("Photos folder", 0)
        ttk.Entry(card, textvariable=self.v["input_folder"]).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(card, text="Browse…", command=lambda: self._browse("input_folder")).grid(row=0, column=2)
        self.lbl_count = ttk.Label(card, textvariable=self.count, style="CardHint.TLabel", width=22)
        self.lbl_count.grid(row=0, column=3, sticky="w", padx=(12, 0))
        L("Save to", 1)
        ttk.Entry(card, textvariable=self.v["output_folder"]).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(card, text="Browse…", command=lambda: self._browse("output_folder")).grid(row=1, column=2)
        fmt = ttk.Frame(card, style="Inner.TFrame")
        fmt.grid(row=1, column=3, sticky="w", padx=(12, 0))
        ttk.Checkbutton(fmt, text="Excel", variable=self.v["export_excel"]).pack(side="left")
        acc = ttk.Checkbutton(fmt, text="Access" if self.access_ok else "Access (not installed)",
                              variable=self.v["export_access"])
        acc.pack(side="left", padx=(10, 0))
        if not self.access_ok:
            acc.state(["disabled"])
        L("OCR engine", 2)
        eng = ttk.Frame(card, style="Inner.TFrame")
        eng.grid(row=2, column=1, columnspan=3, sticky="w", padx=8)
        self.cb_engine = ttk.Combobox(eng, textvariable=self.v["ocr_engine"],
                                      values=["rapidocr", "claude"] if self.claude_ok else ["rapidocr"],
                                      state="readonly", width=11)
        self.cb_engine.pack(side="left")
        self.cb_engine.bind("<<ComboboxSelected>>", lambda e: self._engine_changed())
        self.cb_model = ttk.Combobox(eng, textvariable=self.v["claude_model"],
                                     values=["claude-haiku-5-5", "claude-sonnet-5-5"], width=20)
        self.lbl_engine = ttk.Label(eng, text="", style="CardHint.TLabel")
        self.lbl_engine.pack(side="left", padx=10)
        self._engine_changed()

        # ---- advanced (collapsed by default)
        self.adv_open = False
        self.adv_btn = ttk.Button(outer, text="▸ Advanced options", style="Link.TButton", command=self._toggle_adv)
        self.adv_btn.grid(row=2, column=0, sticky="nw", pady=(6, 0))
        self.adv_btn.lift()
        self.adv = ttk.Frame(outer, style="Card.TFrame", padding=12)
        specs = [("file_pattern", "File pattern", None), ("output_basename", "Output file name", None),
                 ("min_confidence", "Min OCR confidence", 0.05), ("header_ratio", "Header (top) ratio", 0.01),
                 ("footer_ratio", "Footer ratio", 0.01), ("side_tab_ratio", "Side-tab ratio", 0.01),
                 ("column_split", "Column split (0 = auto)", 0.01)]
        for i, (key, label, inc) in enumerate(specs):
            r, c = divmod(i, 4)
            ttk.Label(self.adv, text=label, style="Card.TLabel").grid(row=r * 2, column=c, sticky="w", padx=(0, 18))
            if inc is None:
                w = ttk.Entry(self.adv, textvariable=self.v[key], width=22)
            else:
                w = ttk.Spinbox(self.adv, textvariable=self.v[key], from_=0.0, to=1.0, increment=inc, width=8)
            w.grid(row=r * 2 + 1, column=c, sticky="w", padx=(0, 18), pady=(2, 8))
        ttk.Checkbutton(self.adv, text="Join records that continue on the next page",
                        variable=self.v["merge_continuations"]).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(self.adv, text="Save OCR text per photo (output/debug)",
                        variable=self.v["save_debug_text"]).grid(row=4, column=2, columnspan=2, sticky="w")
        ttk.Button(self.adv, text="Reset to defaults", command=self.reset_defaults).grid(row=4, column=4, sticky="e")

        # ---- action row
        bar = ttk.Frame(outer)
        bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        bar.columnconfigure(2, weight=1)
        self.btn_start = ttk.Button(bar, text="Start", style="Accent.TButton", command=self.start)
        self.btn_start.grid(row=0, column=0)
        self.btn_stop = ttk.Button(bar, text="Stop", command=self.stop)
        self.btn_stop.grid(row=0, column=1, padx=8)
        ttk.Label(bar, textvariable=self.status, style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(6, 0))
        ttk.Label(bar, textvariable=self.eta, style="Hint.TLabel").grid(row=0, column=3, sticky="e")
        self.progress = ttk.Progressbar(bar, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        # ---- results / log
        nb = ttk.Notebook(outer)
        nb.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
        self.nb = nb
        rf = ttk.Frame(nb, padding=(0, 8, 0, 0))
        nb.add(rf, text="Results")
        rf.rowconfigure(1, weight=1)
        rf.columnconfigure(0, weight=1)

        tools = ttk.Frame(rf)
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(tools, text="Search").pack(side="left")
        self.ent_filter = ttk.Entry(tools, textvariable=self.v_filter, width=30)
        self.ent_filter.pack(side="left", padx=(6, 12))
        ttk.Checkbutton(tools, text="Needs review only", variable=self.v_review_only, style="Plain.TCheckbutton",
                        command=self._refill).pack(side="left")
        self.btn_folder = ttk.Button(tools, text="Open folder", command=self.open_output)
        self.btn_folder.pack(side="right")
        self.btn_excel = ttk.Button(tools, text="Open Excel file", command=self.open_excel, state="disabled")
        self.btn_excel.pack(side="right", padx=8)
        self.v_filter.trace_add("write", lambda *a: self._refill())

        pane = ttk.PanedWindow(rf, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew")
        tf = ttk.Frame(pane)
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tf, columns=[c[0] for c in RESULT_COLUMNS], show="headings", selectmode="browse")
        for key, title, w, stretch in RESULT_COLUMNS:
            self.tree.heading(key, text=title, anchor="w", command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=w, minwidth=40, anchor="w", stretch=stretch)
        self.tree.tag_configure("odd", background=STRIPE)
        self.tree.tag_configure("review", background=WARN_BG)
        ys = ttk.Scrollbar(tf, command=self.tree.yview)
        xs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_detail())
        pane.add(tf, weight=3)

        df = ttk.Frame(pane, padding=(10, 0, 0, 0))
        self.detail = tk.Text(df, width=38, wrap="word", state="disabled", relief="flat", bg=CARD, fg=INK,
                              padx=12, pady=10, font=("Segoe UI", 10), highlightthickness=1,
                              highlightbackground=LINE, spacing1=1, spacing3=3)
        self.detail.tag_configure("k", foreground=MUTED, font=("Segoe UI", 8))
        self.detail.tag_configure("h", font=("Segoe UI Semibold", 12))
        self.detail.tag_configure("warn", foreground=WARN_INK, background=WARN_BG)
        self.detail.tag_configure("raw", font=("Consolas", 9), foreground=MUTED)
        ds = ttk.Scrollbar(df, command=self.detail.yview)
        self.detail.configure(yscrollcommand=ds.set)
        self.detail.pack(side="left", fill="both", expand=True)
        ds.pack(side="right", fill="y")
        pane.add(df, weight=2)
        self._set_detail_hint()

        ttk.Label(rf, textvariable=self.summary, style="Hint.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))

        lf = ttk.Frame(nb, padding=(0, 8, 0, 0))
        nb.add(lf, text="Log")
        self.log = tk.Text(lf, height=8, wrap="word", state="disabled", font=("Consolas", 9), relief="flat",
                           bg=CARD, padx=10, pady=8, highlightthickness=1, highlightbackground=LINE)
        self.log.tag_configure("err", foreground="#c0392b")
        ls = ttk.Scrollbar(lf, command=self.log.yview)
        self.log.configure(yscrollcommand=ls.set)
        self.log.pack(side="left", fill="both", expand=True)
        ls.pack(side="right", fill="y")

        for key in ("input_folder", "file_pattern"):
            self.v[key].trace_add("write", lambda *a: self._schedule_count())

    # ---------- helpers ----------
    def _toggle_adv(self):
        self.adv_open = not self.adv_open
        if self.adv_open:
            self.adv.grid(row=2, column=0, sticky="ew", pady=(34, 0))
            self.adv_btn.configure(text="▾ Advanced options")
        else:
            self.adv.grid_remove()
            self.adv_btn.configure(text="▸ Advanced options")

    def _engine_changed(self):
        claude = self.v["ocr_engine"].get() == "claude"
        if claude:
            self.cb_model.pack(side="left", padx=(8, 0), before=self.lbl_engine)
            ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
            self.lbl_engine.configure(text="Sends photos to the Anthropic API" if ok
                                      else "ANTHROPIC_API_KEY is not set — this engine cannot run")
        else:
            self.cb_model.pack_forget()
            self.lbl_engine.configure(text="Runs fully on this PC, no internet needed")

    def _browse(self, key: str):
        old = self.v[key].get()
        d = filedialog.askdirectory(initialdir=old or ".")
        if not d:
            return
        d = os.path.normpath(d)
        self.v[key].set(d)
        # results follow the photos unless the operator chose another place on purpose
        if key == "input_folder" and os.path.normcase(os.path.abspath(self.v["output_folder"].get())) == \
                os.path.normcase(os.path.join(os.path.abspath(old or "."), "output")):
            self.v["output_folder"].set(os.path.join(d, "output"))

    def _schedule_count(self):
        if self._count_job:
            self.root.after_cancel(self._count_job)
        self._count_job = self.root.after(300, self._refresh_count)

    def _find_images(self) -> list[str]:
        folder = self.v["input_folder"].get() or "."
        found = set()
        for p in (self.v["file_pattern"].get() or "*.jpg").split(";"):
            if p.strip():
                found.update(glob.glob(os.path.join(folder, p.strip())))
        return sorted(found)

    def _refresh_count(self):
        self._count_job = None
        folder = self.v["input_folder"].get() or "."
        if not os.path.isdir(folder):
            self.count.set("Folder not found")
            self.lbl_count.configure(foreground="#c0392b")
            return
        n = len(self._find_images())
        self.count.set(f"{n} photo{'s' if n != 1 else ''} found" if n else "No photos here")
        self.lbl_count.configure(foreground=MUTED if n else WARN_INK)

    def _log(self, msg: str, err: bool = False):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S  ") + msg + "\n", ("err",) if err else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_running(self, running: bool):
        self.btn_start.configure(state="disabled" if running else "normal",
                                 text="Working…" if running else "Start")
        self.btn_stop.configure(state="normal" if running else "disabled")

    def _collect(self) -> Settings:
        d = self._base.to_dict()
        for k, var in self.v.items():
            d[k] = var.get()
        labels = {"min_confidence": "Min OCR confidence", "header_ratio": "Header ratio",
                  "footer_ratio": "Footer ratio", "side_tab_ratio": "Side-tab ratio", "column_split": "Column split"}
        for k, label in labels.items():
            try:
                d[k] = float(str(d[k]).replace(",", "."))
            except ValueError:
                raise ValueError(f"“{label}” must be a number.")
            if not 0.0 <= d[k] <= 1.0:
                raise ValueError(f"“{label}” must be between 0 and 1.")
        return Settings.from_dict(d)

    def _apply(self, s: Settings):
        for k, var in self.v.items():
            var.set(getattr(s, k))
        if not self.access_ok:
            self.v["export_access"].set(False)
        self._base = s
        self._engine_changed()

    # ---------- settings ----------
    def save_settings(self, quiet: bool = False):
        try:
            from . import settings_store
            settings_store.save(self._collect(), SETTINGS_FILE)
            if not quiet:
                self.status.set("Settings saved.")
        except Exception as e:
            if not quiet:
                messagebox.showerror("Cannot save settings", str(e))

    def load_settings(self):
        self._apply(_load_settings())
        self.status.set("Settings loaded.")

    def reset_defaults(self):
        keep = self._collect() if self._safe_collect() else Settings()
        s = Settings(input_folder=keep.input_folder, output_folder=keep.output_folder)
        self._apply(s)
        self.status.set("Advanced options reset to defaults.")

    def _safe_collect(self) -> bool:
        try:
            self._collect()
            return True
        except ValueError:
            return False

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel("Still working", "A run is in progress. Stop it and close?"):
                return
            self.stop_flag.set()
        self.save_settings(quiet=True)
        self.root.destroy()

    # ---------- run ----------
    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            s = self._collect()
        except ValueError as e:
            messagebox.showerror("Check settings", str(e))
            return
        if not os.path.isdir(s.input_folder):
            messagebox.showerror("Check settings", "The photos folder does not exist.")
            return
        if not self._find_images():
            messagebox.showerror("Nothing to read", f"No files matching {s.file_pattern} in the photos folder.")
            return
        if not (s.export_excel or s.export_access):
            messagebox.showerror("Check settings", "Pick at least one output format (Excel or Access).")
            return
        if s.ocr_engine == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
            messagebox.showerror("Check settings", "The Claude engine needs the ANTHROPIC_API_KEY environment "
                                                   "variable. Choose “rapidocr” to run locally.")
            return
        try:
            from . import pipeline
        except Exception as e:
            messagebox.showerror("Not ready", f"The extraction engine could not be loaded.\n\n{e}")
            return
        self.save_settings(quiet=True)
        self.stop_flag.clear()
        self.records, self._written = [], []
        self._refill()
        self.btn_excel.configure(state="disabled")
        self.progress.configure(value=0, maximum=1)
        self._set_running(True)
        self.status.set("Starting…")
        self.eta.set("")
        self.summary.set("Reading photos…")
        self._t0 = time.time()
        self._log(f"Start: {os.path.abspath(s.input_folder)} [{s.file_pattern}] → {s.output_folder}")

        def progress(done, total, msg):
            self.q.put(("progress", done, total, msg))

        def work():
            try:
                recs = pipeline.run(s, progress, self.stop_flag)
                self.q.put(("done", recs, s))
            except Exception:
                self.q.put(("error", traceback.format_exc()))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self):
        if not (self.worker and self.worker.is_alive()) or self.stop_flag.is_set():
            return
        self.stop_flag.set()
        self.btn_stop.configure(state="disabled")
        self.status.set("Stopping after the current photo…")
        self._log("Stop requested.")

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "progress":
                    _, done, total, msg = m
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.status.set(msg)
                    if msg.startswith("Saved: "):
                        self._written = [p.strip() for p in msg[7:].split(", ")]
                    bad = msg.startswith(("ERROR", "Export failed"))
                    self._log(msg, err=bad)
                    if 0 < done < total:
                        el = time.time() - self._t0
                        self.eta.set(f"{done} of {total}  ·  about {_fmt_secs(el / done * (total - done))} left")
                    elif total:
                        self.eta.set(f"{done} of {total}")
                elif m[0] == "done":
                    self._finish(m[1], m[2])
                elif m[0] == "error":
                    self._set_running(False)
                    self.status.set("Failed — see the Log tab.")
                    self.eta.set("")
                    self._log(m[1], err=True)
                    self.nb.select(1)
                    messagebox.showerror("Run failed", m[1].strip().splitlines()[-1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _finish(self, records, s: Settings):
        self._set_running(False)
        self.records = list(records or [])
        self._sort = None
        self._refill()
        stopped = self.stop_flag.is_set()
        took = _fmt_secs(time.time() - self._t0)
        self.status.set(f"{'Stopped' if stopped else 'Done'} — {len(self.records)} exhibitors in {took}.")
        self.eta.set("")
        self._log(self.status.get())
        if any(p.lower().endswith(".xlsx") and os.path.exists(p) for p in self._written):
            self.btn_excel.configure(state="normal")
        if self.records:
            self.nb.select(0)
            kids = self.tree.get_children()
            if kids:
                self.tree.selection_set(kids[0])
        else:
            self.nb.select(1)

    # ---------- results table ----------
    def _visible(self) -> list:
        needle = self.v_filter.get().strip().lower()
        out = []
        for r in self.records:
            if self.v_review_only.get() and not review_reasons(r):
                continue
            if needle and needle not in " ".join(str(getattr(r, f, "")) for f, _ in DETAIL_FIELDS).lower():
                continue
            out.append(r)
        if self._sort:
            key, rev = self._sort
            out.sort(key=lambda r: (str(getattr(r, key, "")).lower() if key != "confidence"
                                    else f"{getattr(r, key, 0):08.3f}"), reverse=rev)
        return out

    def _refill(self):
        self.tree.delete(*self.tree.get_children())
        self._row_rec.clear()
        rows = self._visible()
        for i, r in enumerate(rows[:MAX_ROWS]):
            vals = [getattr(r, c[0], "") for c in RESULT_COLUMNS]
            vals[-1] = f"{r.confidence:.2f}" if r.confidence else ""
            tag = "review" if review_reasons(r) else ("odd" if i % 2 else "even")
            self._row_rec[self.tree.insert("", "end", values=vals, tags=(tag,))] = r
        for key, title, _, _ in RESULT_COLUMNS:
            arrow = ""
            if self._sort and self._sort[0] == key:
                arrow = "  ▼" if self._sort[1] else "  ▲"
            self.tree.heading(key, text=title + arrow)
        if self.records:
            n_rev = sum(1 for r in self.records if review_reasons(r))
            parts = [f"{len(self.records)} exhibitors"]
            if len(rows) != len(self.records):
                parts.append(f"{len(rows)} shown")
            parts.append(f"{n_rev} need review (highlighted)" if n_rev else "none flagged for review")
            if len(rows) > MAX_ROWS:
                parts.append(f"first {MAX_ROWS} listed — all are in the exported file")
            self.summary.set("  ·  ".join(parts))
        self._set_detail_hint()

    def _sort_by(self, key: str):
        self._sort = (key, not self._sort[1]) if self._sort and self._sort[0] == key else (key, False)
        self._refill()

    def _set_detail_hint(self):
        self._write_detail([("Select a row to see every field of that exhibitor and the text it was read from.",
                             "k")])

    def _write_detail(self, chunks):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        for text, tag in chunks:
            self.detail.insert("end", text, (tag,) if tag else ())
        self.detail.configure(state="disabled")

    def _show_detail(self):
        sel = self.tree.selection()
        r = self._row_rec.get(sel[0]) if sel else None
        if r is None:
            return
        chunks = [((r.name_en or r.name_cn or "(no name)") + "\n", "h")]
        if r.domestic_sale:
            chunks.append(("★ also sells in the domestic market\n", "k"))
        why = review_reasons(r)
        if why:
            chunks.append((" Check: " + "; ".join(why) + " \n", "warn"))
        for f, label in DETAIL_FIELDS:
            val = getattr(r, f, "")
            if val in ("", None):
                continue
            if f == "confidence":
                val = f"{val:.2f}"
            chunks += [("\n" + label.upper() + "\n", "k"), (str(val) + "\n", "")]
        if r.raw_text:
            chunks += [("\nTEXT AS READ FROM THE PHOTO\n", "k"), (r.raw_text + "\n", "raw")]
        self._write_detail(chunks)

    # ---------- open results ----------
    def _open(self, p: str):
        try:
            if sys.platform == "win32":
                os.startfile(p)  # noqa: S606
            else:
                import subprocess
                subprocess.Popen(["xdg-open", p])
        except Exception as e:
            messagebox.showerror("Cannot open", str(e))

    def open_output(self):
        p = os.path.abspath(self.v["output_folder"].get() or ".")
        os.makedirs(p, exist_ok=True)
        self._open(p)

    def open_excel(self):
        for p in self._written:
            if p.lower().endswith(".xlsx") and os.path.exists(p):
                self._open(p)
                return


def main():
    if sys.platform == "win32":  # crisp text on high-DPI screens
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                 "packaging"))
    try:
        root.iconbitmap(default=os.path.join(base, "app.ico"))
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
