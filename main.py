from __future__ import annotations

import os
import sys
import tempfile
import threading
import ctypes
import math
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    BaseTk = TkinterDnD.Tk
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    BaseTk = tk.Tk
    DND_AVAILABLE = False

from engine import RenderOptions, VideoEngine, is_video_file, layout_heights, segment_count
from i18n import tr
from version import APP_VERSION

APP_TITLE = "TikTok Split Maker"
APP_DIR = Path(__file__).resolve().parent
ASSETS = APP_DIR / "assets"

# Palette inspired by the generated concept.
BG = "#0b111c"
PANEL = "#111a28"
PANEL_2 = "#151f2f"
PANEL_3 = "#0e1725"
BORDER = "#26354b"
TEXT = "#f4f7fb"
MUTED = "#9caac0"
CYAN = "#19d3ff"
CYAN_DARK = "#0d7f9e"
MAGENTA = "#ef3bc5"
PURPLE = "#9966ff"
SUCCESS = "#4bd48b"
DANGER = "#ff667c"


def resource_path(relative: str) -> Path:
    # PyInstaller support.
    base = Path(getattr(sys, "_MEIPASS", APP_DIR))
    return base / relative


def short_path(path: str, max_chars: int = 65) -> str:
    if len(path) <= max_chars:
        return path
    return "…" + path[-(max_chars - 1):]


def format_duration(seconds: float, *, include_seconds: bool = True) -> str:
    seconds = max(0, int(round(seconds or 0)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    if include_seconds:
        return f"{minutes}:{secs:02d}"
    return f"{minutes} мин"


def format_eta(seconds: float, lang: str = "ru") -> str:
    if not math.isfinite(seconds) or seconds < 0:
        return "—"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} сек" if lang == "ru" else f"{seconds} sec"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius=18, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def _colorref(hex_color: str) -> int:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i:i+2], 16) for i in (0, 2, 4))
    return r | (g << 8) | (b << 16)


def apply_windows_dark_titlebar(root: tk.Tk) -> None:
    """Apply a real dark Windows 11 title bar instead of the default white caption."""
    if os.name != "nt":
        return
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = root.winfo_id()
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        enabled = ctypes.c_int(1)
        # 20 on modern Windows 10/11, 19 on a few older builds.
        if dwm(hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled)) != 0:
            dwm(hwnd, 19, ctypes.byref(enabled), ctypes.sizeof(enabled))
        caption = ctypes.c_int(_colorref(PANEL_3))
        border = ctypes.c_int(_colorref(BORDER))
        text = ctypes.c_int(_colorref(TEXT))
        # Windows 11 DWM attributes: border/caption/text color.
        dwm(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
        dwm(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        dwm(hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))
    except Exception:
        # Cosmetic only. Never block the app if DWM rejects an attribute.
        pass


class HoverButton(tk.Button):
    def __init__(self, master, *, bg, hover_bg, fg=TEXT, **kwargs):
        self.normal_bg = bg
        self.hover_bg = hover_bg
        font = kwargs.pop("font", ("Segoe UI", 10, "bold"))
        super().__init__(
            master,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            highlightthickness=0,
            font=font,
            **kwargs,
        )
        self.bind("<Enter>", lambda _e: self.configure(bg=self.hover_bg))
        self.bind("<Leave>", lambda _e: self.configure(bg=self.normal_bg))


class DropZone(tk.Canvas):
    def __init__(self, master, title: str, accent: str, browse_command, drop_command, tr_func=None, height=105):
        super().__init__(master, bg=PANEL, height=height, highlightthickness=0, bd=0, cursor="hand2")
        self.title = title
        self.accent = accent
        self.browse_command = browse_command
        self.drop_command = drop_command
        self.tr = tr_func or (lambda key, **kwargs: key)
        self.file_path = ""
        self.bind("<Button-1>", lambda _e: self.browse_command())
        self.bind("<Configure>", lambda _e: self.redraw())
        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DropEnter>>", self._on_enter)
            self.dnd_bind("<<DropLeave>>", self._on_leave)

    def set_path(self, path: str):
        self.file_path = path
        self.redraw()

    def _on_drop(self, event):
        self.configure(bg=PANEL)
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data.strip("{}")]
        if paths:
            self.drop_command(paths[0])
        return event.action if hasattr(event, "action") else None

    def _on_enter(self, event):
        self.configure(bg=PANEL_2)
        return event.action if hasattr(event, "action") else None

    def _on_leave(self, event):
        self.configure(bg=PANEL)
        return event.action if hasattr(event, "action") else None

    def redraw(self):
        self.delete("all")
        w = max(20, self.winfo_width())
        h = max(20, self.winfo_height())
        self.create_rectangle(6, 6, w - 6, h - 6, outline=self.accent, width=2, dash=(7, 5))
        if self.file_path:
            name = Path(self.file_path).name
            self.create_text(24, h / 2 - 11, text="✓", fill=SUCCESS, font=("Segoe UI Symbol", 18, "bold"), anchor="w")
            self.create_text(58, h / 2 - 11, text=name, fill=TEXT, font=("Segoe UI", 11, "bold"), anchor="w")
            self.create_text(58, h / 2 + 14, text=short_path(self.file_path), fill=MUTED, font=("Segoe UI", 8), anchor="w")
            self.create_text(w - 22, h / 2, text="↻", fill=self.accent, font=("Segoe UI Symbol", 16, "bold"), anchor="e")
        else:
            icon = "＋"
            self.create_text(w / 2 - 135, h / 2 - 8, text=icon, fill=self.accent, font=("Segoe UI Symbol", 25, "bold"))
            drop_text = self.tr("drag_here") if DND_AVAILABLE else self.tr("click_choose_video")
            self.create_text(w / 2 + 12, h / 2 - 9, text=drop_text, fill=TEXT, font=("Segoe UI", 11, "bold"), anchor="center")
            sub = self.tr("or_click") if DND_AVAILABLE else self.tr("dnd_dependency")
            self.create_text(w / 2 + 12, h / 2 + 16, text=sub, fill=MUTED, font=("Segoe UI", 8), anchor="center")


class ProgressCanvas(tk.Canvas):
    def __init__(self, master, height=8):
        super().__init__(master, bg=PANEL_3, height=height, highlightthickness=0, bd=0)
        self.value = 0.0
        self.bind("<Configure>", lambda _e: self.redraw())

    def set(self, value: float):
        self.value = min(1.0, max(0.0, value))
        self.redraw()

    def redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        self.create_rectangle(0, 0, w, h, fill="#223047", outline="")
        fill_w = int(w * self.value)
        if fill_w > 0:
            self.create_rectangle(0, 0, fill_w, h, fill=CYAN, outline="")



class DarkDropdown(tk.Frame):
    """Fully custom dark dropdown, independent of ttk popdown styling."""
    def __init__(self, master, variable, values, command=None, **kwargs):
        super().__init__(master, bg=PANEL_3, highlightbackground=BORDER, highlightthickness=1, bd=0, **kwargs)
        self.variable = variable
        self.values = list(values)
        self.command = command
        self.popup = None

        self.grid_columnconfigure(0, weight=1)
        self.label = tk.Label(self, textvariable=self.variable, fg=TEXT, bg=PANEL_3,
                              font=("Segoe UI", 10), anchor="w", padx=10, pady=8, cursor="hand2")
        self.label.grid(row=0, column=0, sticky="nsew")
        self.arrow = tk.Label(self, text="▾", fg=MUTED, bg=PANEL_3,
                              font=("Segoe UI", 10, "bold"), padx=8, cursor="hand2")
        self.arrow.grid(row=0, column=1, sticky="ns")

        for w in (self, self.label, self.arrow):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>", self._hover_on)
            w.bind("<Leave>", self._hover_off)

    def _hover_on(self, _event=None):
        if not self.popup:
            self.configure(highlightbackground=CYAN_DARK)
            self.label.configure(bg=PANEL_2)
            self.arrow.configure(bg=PANEL_2, fg=TEXT)

    def _hover_off(self, _event=None):
        if not self.popup:
            self.configure(highlightbackground=BORDER)
            self.label.configure(bg=PANEL_3)
            self.arrow.configure(bg=PANEL_3, fg=MUTED)

    def _toggle(self, _event=None):
        if self.popup and self.popup.winfo_exists():
            self._close_popup()
        else:
            self._open_popup()
        return "break"

    def _open_popup(self):
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        width = max(self.winfo_width(), 180)

        popup = tk.Toplevel(self)
        self.popup = popup
        popup.overrideredirect(True)
        popup.configure(bg=BORDER)
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass

        inner = tk.Frame(popup, bg=PANEL_3, bd=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        selected = self.variable.get()
        for value in self.values:
            bg = CYAN_DARK if value == selected else PANEL_3
            item = tk.Label(inner, text=value, fg=TEXT, bg=bg, anchor="w",
                            font=("Segoe UI", 10), padx=10, pady=7, cursor="hand2")
            item.pack(fill="x")
            item.bind("<Enter>", lambda e: e.widget.configure(bg=PANEL_2))
            item.bind("<Leave>", lambda e, v=value: e.widget.configure(bg=CYAN_DARK if v == self.variable.get() else PANEL_3))
            item.bind("<Button-1>", lambda e, v=value: self._select(v))

        popup.update_idletasks()
        height = popup.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        if x + width > sw:
            x = max(0, sw - width - 4)
        if y + height > sh:
            y = max(0, self.winfo_rooty() - height - 2)
        popup.geometry(f"{width}x{height}+{x}+{y}")

        self.configure(highlightbackground=CYAN)
        self.label.configure(bg=PANEL_2)
        self.arrow.configure(bg=PANEL_2, fg=TEXT, text="▴")
        popup.bind("<Escape>", lambda _e: self._close_popup())
        popup.bind("<FocusOut>", self._on_focus_out)
        popup.after_idle(popup.focus_force)

    def _on_focus_out(self, _event=None):
        if self.popup and self.popup.winfo_exists():
            self.after(80, self._close_if_focus_lost)

    def _close_if_focus_lost(self):
        if self.popup and self.popup.winfo_exists():
            try:
                focused = self.popup.focus_get()
                if focused is None or focused.winfo_toplevel() != self.popup:
                    self._close_popup()
            except tk.TclError:
                self._close_popup()

    def _select(self, value):
        self.variable.set(value)
        self._close_popup()
        if self.command:
            self.command()

    def _close_popup(self):
        if self.popup:
            try:
                if self.popup.winfo_exists():
                    self.popup.destroy()
            except tk.TclError:
                pass
        self.popup = None
        self.configure(highlightbackground=BORDER)
        self.label.configure(bg=PANEL_3)
        self.arrow.configure(bg=PANEL_3, fg=MUTED, text="▾")

class ModeToggle(tk.Frame):
    """Two-state segmented toggle used for Single / Multi mode."""
    def __init__(self, master, variable: tk.StringVar, command, tr_func=None):
        super().__init__(master, bg="#09111d", highlightbackground=BORDER, highlightthickness=1, bd=0)
        self.variable = variable
        self.command = command
        self.tr = tr_func or (lambda key, **kwargs: key)
        self.enabled = True
        self.buttons: dict[str, tk.Label] = {}
        for col, (value, key) in enumerate((("single", "mode_single"), ("multi", "mode_multi"))):
            text = self.tr(key)
            lbl = tk.Label(
                self, text=text, font=("Segoe UI", 9, "bold"), padx=16, pady=8,
                cursor="hand2", bd=0, relief="flat"
            )
            lbl.grid(row=0, column=col, sticky="nsew")
            lbl.bind("<Button-1>", lambda _e, v=value: self._choose(v))
            self.buttons[value] = lbl
        self._paint()

    def _choose(self, value: str):
        if not self.enabled or value == self.variable.get():
            return "break"
        self.variable.set(value)
        self._paint()
        self.command(value)
        return "break"

    def _paint(self):
        selected = self.variable.get()
        for value, lbl in self.buttons.items():
            if value == selected:
                lbl.configure(bg=CYAN_DARK, fg=TEXT)
            else:
                lbl.configure(bg=PANEL_3, fg=MUTED if self.enabled else "#66758a")

    def refresh_language(self):
        self.buttons["single"].configure(text=self.tr("mode_single"))
        self.buttons["multi"].configure(text=self.tr("mode_multi"))
        self._paint()

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        for lbl in self.buttons.values():
            lbl.configure(cursor="hand2" if self.enabled else "arrow")
        self._paint()


class LanguageToggle(tk.Frame):
    """Compact US/RU flag selector with a clear active state."""
    def __init__(self, master, variable: tk.StringVar, command):
        super().__init__(master, bg=PANEL_3, highlightbackground=BORDER, highlightthickness=1, bd=0)
        self.variable = variable
        self.command = command
        self.buttons: dict[str, tk.Label] = {}
        self.images: dict[str, ImageTk.PhotoImage] = {}
        for col, (lang, asset, tooltip) in enumerate((
            ("en", "assets/flag_us.png", "English"),
            ("ru", "assets/flag_ru.png", "Русский"),
        )):
            try:
                image = Image.open(resource_path(asset)).resize((27, 18), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.images[lang] = photo
                lbl = tk.Label(
                    self, image=photo, text=("EN" if lang == "en" else "RU"), compound="left",
                    font=("Segoe UI", 8, "bold"), padx=7, pady=6, cursor="hand2", bd=0, relief="flat"
                )
            except Exception:
                lbl = tk.Label(self, text=("EN" if lang == "en" else "RU"), font=("Segoe UI", 8, "bold"),
                               padx=10, pady=6, cursor="hand2", bd=0, relief="flat")
            lbl.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 1, 0))
            lbl.bind("<Button-1>", lambda _e, v=lang: self._choose(v))
            lbl.bind("<Enter>", lambda e: e.widget.configure(bg=PANEL_2) if self.variable.get() != self._lang_for(e.widget) else None)
            lbl.bind("<Leave>", lambda _e: self._paint())
            lbl._language_code = lang
            lbl._tooltip = tooltip
            self.buttons[lang] = lbl
        self._paint()

    @staticmethod
    def _lang_for(widget):
        return getattr(widget, "_language_code", "")

    def _choose(self, lang: str):
        if lang == self.variable.get():
            return "break"
        self.variable.set(lang)
        self._paint()
        self.command(lang)
        return "break"

    def _paint(self):
        selected = self.variable.get()
        for lang, lbl in self.buttons.items():
            active = lang == selected
            lbl.configure(
                bg=CYAN_DARK if active else PANEL_3,
                highlightbackground=CYAN if active else PANEL_3,
                highlightthickness=1 if active else 0,
                fg=TEXT if active else MUTED,
            )



class App(BaseTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(1000, 760)
        self.configure(bg=BG)

        try:
            ico = resource_path("assets/icon.ico")
            if os.name == "nt" and ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

        self.engine = VideoEngine(resource_path("."))
        self.language = tk.StringVar(value="en")
        self.mode = tk.StringVar(value="single")
        self.main_video = tk.StringVar()
        self.bottom_video = tk.StringVar()
        self.output_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.segment_seconds = tk.StringVar(value="65")
        self.ratio = tk.StringVar(value="70/30")
        self.quality = tk.StringVar(value="High")
        self.encoder = tk.StringVar(value="Auto (RTX/NVENC)")
        self.status = tk.StringVar(value=tr("en", "status_ready"))
        self.percent = tk.StringVar(value="0%")

        self.main_duration = 0.0
        self.bottom_duration = 0.0
        self._main_probe_generation = 0
        self._bottom_probe_generation = 0
        self._render_thread = None
        self._render_active = False
        self._cancel_requested = threading.Event()
        self._batch_started_at = 0.0
        self._eta_smoothed: float | None = None
        self._speed_smoothed: float | None = None
        self._nvenc_state: bool | None = None
        self._preview_generation = 0
        self._preview_sources: list[Image.Image | None] = [None, None]
        self._preview_rendered: ImageTk.PhotoImage | None = None
        self._temp_dir = Path(tempfile.mkdtemp(prefix="tsm_preview_"))

        self._configure_ttk()
        self._build_ui()
        self.after(10, lambda: apply_windows_dark_titlebar(self))
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self.update_preview)
        if not DND_AVAILABLE:
            self.after(600, self._warn_dnd_dependency)

    def _configure_ttk(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # ttk.Combobox uses a separate Tcl Listbox for its popup. Windows would
        # otherwise paint that list bright white even though the field is dark.

        style.configure(
            "Dark.TCombobox",
            fieldbackground=PANEL_3,
            background=PANEL_3,
            foreground=TEXT,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            selectbackground=PANEL_3,
            selectforeground=TEXT,
            insertcolor=TEXT,
            padding=8,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", PANEL_3), ("active", PANEL_2)],
            background=[("readonly", PANEL_3), ("active", PANEL_2)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", PANEL_3)],
            selectforeground=[("readonly", TEXT)],
            arrowcolor=[("active", TEXT), ("readonly", MUTED)],
        )

    def _card(self, master):
        return tk.Frame(master, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, bd=0)

    def t(self, key: str, **kwargs) -> str:
        return tr(self.language.get(), key, **kwargs)

    def _video_types(self):
        return [
            (self.t("video_filter"), "*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.wmv *.ts"),
            (self.t("all_files"), "*.*"),
        ]

    def _set_status(self, key: str, **kwargs):
        self.status.set(self.t(key, **kwargs))

    def _set_detail(self, key: str, **kwargs):
        self.status_detail.configure(text=self.t(key, **kwargs))

    def _on_language_changed(self, _lang: str):
        self.mode_toggle.refresh_language()
        mode = self.mode.get()
        self.header_subtitle.configure(text=self.t("app_subtitle_multi" if mode == "multi" else "app_subtitle_single"))
        self.main_title_label.configure(text=self.t("main_video"))
        self.main_subtitle_label.configure(text=self.t("main_video_sub"))
        self.bottom_title_label.configure(text=self.t("bottom_video"))
        self.bottom_subtitle_label.configure(text=self.t("bottom_video_sub"))
        self.output_title_label.configure(text=self.t("output_folder" if mode == "multi" else "output_file"))
        self.output_subtitle_label.configure(text=self.t("output_folder_sub" if mode == "multi" else "output_file_sub"))
        self.output_button.configure(text=self.t("browse"))
        self.preview_title_label.configure(text=self.t("preview"))
        self.settings_title_label.configure(text=self.t("settings"))
        for widget, key in zip(getattr(self, "setting_labels", []), ("block_size", "quality", "encoder")):
            widget.configure(text=self.t(key))
        self.segment_duration_label.configure(text=self.t("segment_duration"))
        self.seconds_label.configure(text=self.t("seconds_short"))
        self.cancel_btn.configure(text=self.t("cancel"))
        if hasattr(self, "about_btn"):
            self.about_btn.configure(text="ⓘ  " + self.t("about"))
        self.main_zone.redraw()
        self.bottom_zone.redraw()
        self._refresh_output_label()
        self._refresh_batch_summary()
        self._refresh_render_button()
        self.draw_preview()
        if self._nvenc_state is None:
            self.accel_label.configure(text=self.t("nvenc_checking"), fg=MUTED)
        elif self._nvenc_state:
            self.accel_label.configure(text=self.t("nvenc_ready"), fg=SUCCESS)
        else:
            self.accel_label.configure(text=self.t("nvenc_unavailable"), fg=MUTED)
        if not self._render_active:
            self._set_status("status_ready")
            self._set_detail("status_batch_setup" if mode == "multi" else "status_add_videos")

    def _show_about(self):
        messagebox.showinfo(
            self.t("about_title"),
            self.t("about_body", version=APP_VERSION),
            parent=self,
        )

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = tk.Frame(self, bg=PANEL_3, height=84)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        try:
            self.header_icon = tk.PhotoImage(file=str(resource_path("assets/icon.png"))).subsample(8, 8)
            tk.Label(header, image=self.header_icon, bg=PANEL_3).grid(row=0, column=0, rowspan=2, padx=(18, 14), pady=9)
        except Exception:
            tk.Label(header, text="▶", fg=CYAN, bg=PANEL_3, font=("Segoe UI Symbol", 28, "bold")).grid(row=0, column=0, rowspan=2, padx=20)

        tk.Label(header, text="TikTok Split Maker", fg=TEXT, bg=PANEL_3, font=("Segoe UI", 21, "bold")).grid(row=0, column=1, sticky="sw", pady=(16, 0))
        self.header_subtitle = tk.Label(
            header, text=self.t("app_subtitle_single"),
            fg=MUTED, bg=PANEL_3, font=("Segoe UI", 10)
        )
        self.header_subtitle.grid(row=1, column=1, sticky="nw", pady=(2, 14))

        self.language_toggle = LanguageToggle(header, self.language, self._on_language_changed)
        self.language_toggle.grid(row=0, column=2, rowspan=2, sticky="e", padx=(10, 6), pady=23)

        self.mode_toggle = ModeToggle(header, self.mode, self._on_mode_changed, tr_func=self.t)
        self.mode_toggle.grid(row=0, column=3, rowspan=2, sticky="e", padx=(6, 8), pady=22)

        header_right = tk.Frame(header, bg=PANEL_3)
        header_right.grid(row=0, column=4, rowspan=2, sticky="e", padx=(6, 14), pady=10)
        self.accel_label = tk.Label(header_right, text=self.t("nvenc_checking"), fg=MUTED, bg=PANEL_3, font=("Segoe UI", 9, "bold"))
        self.accel_label.pack(anchor="e", pady=(4, 4))
        self.about_btn = HoverButton(
            header_right, text="ⓘ  " + self.t("about"), command=self._show_about,
            bg=PANEL_3, hover_bg=PANEL_2, fg=MUTED, font=("Segoe UI", 8, "bold"), padx=7, pady=3
        )
        self.about_btn.pack(anchor="e")
        threading.Thread(target=self._check_accel, daemon=True).start()

        # Main content
        content = tk.Frame(self, bg=BG)
        content.grid(row=1, column=0, sticky="nsew", padx=18)
        content.grid_columnconfigure(0, weight=7)
        content.grid_columnconfigure(1, weight=4)
        content.grid_rowconfigure(0, weight=1)

        left = tk.Frame(content, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_columnconfigure(0, weight=1)
        for r in range(3):
            left.grid_rowconfigure(r, weight=1)

        right = tk.Frame(content, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=0, minsize=285)

        self._build_input_card(left, 0, "1", self.t("main_video"), self.t("main_video_sub"), CYAN, "main")
        self._build_input_card(left, 1, "2", self.t("bottom_video"), self.t("bottom_video_sub"), MAGENTA, "bottom")
        self._build_output_card(left, 2)
        self._build_preview_card(right)
        self._build_settings_card(right)

        # Bottom bar
        bottom = tk.Frame(self, bg=PANEL_3, height=92)
        bottom.grid(row=2, column=0, sticky="ew", padx=18, pady=(10, 16))
        bottom.grid_propagate(False)
        bottom.grid_columnconfigure(1, weight=1)

        status_box = tk.Frame(bottom, bg=PANEL_3)
        status_box.grid(row=0, column=0, rowspan=2, sticky="w", padx=(18, 18), pady=12)
        tk.Label(status_box, textvariable=self.status, fg=TEXT, bg=PANEL_3, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.status_detail = tk.Label(status_box, text=self.t("status_add_videos"), fg=MUTED, bg=PANEL_3, font=("Segoe UI", 8))
        self.status_detail.pack(anchor="w", pady=(3, 0))

        progress_box = tk.Frame(bottom, bg=PANEL_3)
        progress_box.grid(row=0, column=1, rowspan=2, sticky="ew", padx=8, pady=20)
        progress_box.grid_columnconfigure(0, weight=1)
        self.progress = ProgressCanvas(progress_box, height=8)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        tk.Label(progress_box, textvariable=self.percent, fg=MUTED, bg=PANEL_3, font=("Segoe UI", 9, "bold"), width=5).grid(row=0, column=1)

        self.cancel_btn = HoverButton(bottom, text=self.t("cancel"), command=self.cancel_render, bg="#26354b", hover_bg="#334660", width=10)
        self.cancel_btn.grid(row=0, column=2, rowspan=2, padx=(16, 8), pady=20, sticky="ns")
        self.cancel_btn.configure(state="disabled")

        self.render_btn = HoverButton(bottom, text=self.t("create_video"), command=self.start_render, bg="#0fbde9", hover_bg="#32d4f7", width=19, font=("Segoe UI", 11, "bold"))
        self.render_btn.grid(row=0, column=3, rowspan=2, padx=(8, 18), pady=16, sticky="ns")

    def _build_input_card(self, parent, row, number, title, subtitle, accent, kind):
        card = self._card(parent)
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 10) if row < 2 else 0)
        card.grid_columnconfigure(1, weight=1)

        badge = tk.Canvas(card, width=44, height=44, bg=PANEL, highlightthickness=0)
        badge.grid(row=0, column=0, rowspan=2, padx=(18, 10), pady=(14, 6), sticky="n")
        badge.create_oval(5, 5, 39, 39, outline=accent, width=2)
        badge.create_text(22, 22, text=number, fill=accent, font=("Segoe UI", 12, "bold"))

        title_label = tk.Label(card, text=title, fg=TEXT, bg=PANEL, font=("Segoe UI", 12, "bold"))
        title_label.grid(row=0, column=1, sticky="sw", pady=(14, 0))
        subtitle_label = tk.Label(card, text=subtitle, fg=MUTED, bg=PANEL, font=("Segoe UI", 9))
        subtitle_label.grid(row=1, column=1, sticky="nw", pady=(1, 5))
        if kind == "main":
            self.main_title_label, self.main_subtitle_label = title_label, subtitle_label
        else:
            self.bottom_title_label, self.bottom_subtitle_label = title_label, subtitle_label

        if kind == "main":
            browse = self.pick_main
            dropped = self.drop_main
        else:
            browse = self.pick_bottom
            dropped = self.drop_bottom
        zone = DropZone(card, title, accent, browse, dropped, tr_func=self.t, height=106)
        zone.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 16))
        if kind == "main":
            self.main_zone = zone
        else:
            self.bottom_zone = zone

    def _build_output_card(self, parent, row):
        card = self._card(parent)
        self.output_card = card
        card.grid(row=row, column=0, sticky="nsew")
        card.grid_columnconfigure(1, weight=1)

        badge = tk.Canvas(card, width=44, height=44, bg=PANEL, highlightthickness=0)
        badge.grid(row=0, column=0, rowspan=2, padx=(18, 10), pady=(14, 6), sticky="n")
        badge.create_oval(5, 5, 39, 39, outline=PURPLE, width=2)
        badge.create_text(22, 22, text="3", fill=PURPLE, font=("Segoe UI", 12, "bold"))
        self.output_title_label = tk.Label(card, text=self.t("output_file"), fg=TEXT, bg=PANEL, font=("Segoe UI", 12, "bold"))
        self.output_title_label.grid(row=0, column=1, sticky="sw", pady=(14, 0))
        self.output_subtitle_label = tk.Label(card, text=self.t("output_file_sub"), fg=MUTED, bg=PANEL, font=("Segoe UI", 9))
        self.output_subtitle_label.grid(row=1, column=1, sticky="nw", pady=(1, 8))

        self.output_frame = tk.Frame(card, bg=PANEL_3, highlightbackground=PURPLE, highlightthickness=1)
        self.output_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(5, 16))
        self.output_frame.grid_columnconfigure(0, weight=1)
        self.output_label = tk.Label(
            self.output_frame, text=self.t("output_auto"),
            fg=MUTED, bg=PANEL_3, font=("Segoe UI", 9), anchor="w"
        )
        self.output_label.grid(row=0, column=0, sticky="ew", padx=14, pady=16)
        self.output_button = HoverButton(
            self.output_frame, text=self.t("browse"), command=self.pick_output,
            bg="#26354b", hover_bg="#334660", width=10
        )
        self.output_button.grid(row=0, column=1, padx=10, pady=8)

        if DND_AVAILABLE:
            for w in (self.output_frame, self.output_label):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._drop_output)

    def _build_preview_card(self, parent):
        card = self._card(parent)
        card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        self.preview_title_label = tk.Label(card, text=self.t("preview"), fg=TEXT, bg=PANEL, font=("Segoe UI", 11, "bold"))
        self.preview_title_label.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))
        self.preview = tk.Canvas(card, bg=PANEL, highlightthickness=0)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.preview.bind("<Configure>", lambda _e: self.draw_preview())

    def _build_settings_card(self, parent):
        card = self._card(parent)
        self.settings_card = card
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(1, weight=1)
        self.settings_title_label = tk.Label(card, text=self.t("settings"), fg=TEXT, bg=PANEL, font=("Segoe UI", 11, "bold"))
        self.settings_title_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8))
        self._setting_row(card, 1, self.t("block_size"), self.ratio, ["70/30", "65/35", "60/40"])
        self._setting_row(card, 2, self.t("quality"), self.quality, ["High", "Very high", "Small file"])
        self._setting_row(card, 3, self.t("encoder"), self.encoder, ["Auto (RTX/NVENC)", "NVIDIA NVENC", "CPU (x264)"])

        self.batch_duration_row = tk.Frame(card, bg=PANEL)
        self.batch_duration_row.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(6, 4))
        self.batch_duration_row.grid_columnconfigure(1, weight=1)
        self.segment_duration_label = tk.Label(self.batch_duration_row, text=self.t("segment_duration"), fg=MUTED, bg=PANEL, font=("Segoe UI", 9))
        self.segment_duration_label.grid(row=0, column=0, sticky="w", padx=(0, 12))
        vcmd = (self.register(self._validate_segment_input), "%P")
        self.segment_entry = tk.Entry(
            self.batch_duration_row, textvariable=self.segment_seconds, validate="key", validatecommand=vcmd,
            bg=PANEL_3, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0,
            highlightbackground=BORDER, highlightcolor=CYAN_DARK, highlightthickness=1,
            font=("Segoe UI", 10), justify="left"
        )
        self.segment_entry.grid(row=0, column=1, sticky="ew", ipady=7)
        self.seconds_label = tk.Label(self.batch_duration_row, text=self.t("seconds_short"), fg=MUTED, bg=PANEL, font=("Segoe UI", 9))
        self.seconds_label.grid(row=0, column=2, padx=(8, 0))

        self.batch_summary = tk.Label(
            card, text=self.t("batch_pick_main"),
            fg=MUTED, bg=PANEL, font=("Segoe UI", 8), anchor="w", justify="left"
        )
        self.batch_summary.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 12))
        self.batch_duration_row.grid_remove()
        self.batch_summary.grid_remove()
        self.segment_seconds.trace_add("write", lambda *_args: self._on_segment_changed())

    def _setting_row(self, parent, row, label, variable, values):
        label_widget = tk.Label(parent, text=label, fg=MUTED, bg=PANEL, font=("Segoe UI", 9))
        label_widget.grid(row=row, column=0, sticky="w", padx=(16, 10), pady=7)
        combo = DarkDropdown(parent, variable=variable, values=values, command=self.update_preview)
        combo.grid(row=row, column=1, sticky="ew", padx=(4, 16), pady=7)
        if not hasattr(self, "setting_labels"):
            self.setting_labels = []
        self.setting_labels.append(label_widget)

    def _validate_segment_input(self, proposed: str) -> bool:
        if proposed == "":
            return True
        return proposed.isdigit() and len(proposed) <= 3 and int(proposed) <= 300

    def _segment_value(self) -> int | None:
        raw = self.segment_seconds.get().strip()
        if not raw.isdigit():
            return None
        value = int(raw)
        return value if 5 <= value <= 300 else None

    def _on_segment_changed(self):
        self._refresh_batch_summary()
        self._refresh_render_button()

    def _on_mode_changed(self, mode: str):
        if self._render_active:
            return
        if mode == "multi":
            self.header_subtitle.configure(text=self.t("app_subtitle_multi"))
            self.output_title_label.configure(text=self.t("output_folder"))
            self.output_subtitle_label.configure(text=self.t("output_folder_sub"))
            self.batch_duration_row.grid()
            self.batch_summary.grid()
        else:
            self.header_subtitle.configure(text=self.t("app_subtitle_single"))
            self.output_title_label.configure(text=self.t("output_file"))
            self.output_subtitle_label.configure(text=self.t("output_file_sub"))
            self.batch_duration_row.grid_remove()
            self.batch_summary.grid_remove()
        self._refresh_output_label()
        self._refresh_batch_summary()
        self._refresh_render_button()
        self._set_status("status_ready")
        self._set_detail("status_batch_setup" if mode == "multi" else "status_add_videos")

    def _refresh_output_label(self):
        if self.mode.get() == "multi":
            path = self.output_dir.get().strip()
            if path:
                self.output_label.configure(text=short_path(path), fg=TEXT)
            else:
                self.output_label.configure(text=self.t("output_choose_folder"), fg=MUTED)
        else:
            path = self.output_file.get().strip()
            if path:
                self.output_label.configure(text=short_path(path), fg=TEXT)
            else:
                self.output_label.configure(text=self.t("output_auto"), fg=MUTED)

    def _refresh_batch_summary(self):
        if not hasattr(self, "batch_summary"):
            return
        seg = self._segment_value()
        if seg is None:
            self.batch_summary.configure(text=self.t("duration_invalid"), fg=DANGER)
            return
        if self.main_duration <= 0:
            self.batch_summary.configure(text=self.t("duration_pick_main", seg=seg), fg=MUTED)
            return
        count = segment_count(self.main_duration, seg)
        last = self.main_duration - (count - 1) * seg if count else 0
        extra = self.t("batch_last", duration=format_duration(last)) if count and last < seg - 0.01 else ""
        self.batch_summary.configure(
            text=self.t("batch_summary", duration=format_duration(self.main_duration), seg=seg, count=count, extra=extra),
            fg=SUCCESS if count else MUTED,
        )

    def _refresh_render_button(self):
        if not hasattr(self, "render_btn"):
            return
        if self.mode.get() == "single":
            self.render_btn.configure(text=self.t("create_video"))
            return
        seg = self._segment_value()
        count = segment_count(self.main_duration, seg) if seg else 0
        if count:
            self.render_btn.configure(text=self.t("create_n_videos", count=count))
        else:
            self.render_btn.configure(text=self.t("create_batch"))

    def _warn_dnd_dependency(self):
        self._set_detail("dnd_disabled")

    def _check_accel(self):
        if not self.engine.ffmpeg:
            self._nvenc_state = False
            self.after(0, lambda: self.accel_label.configure(text=self.t("ffmpeg_missing_badge"), fg=DANGER))
            return
        ok = self.engine.nvenc_works()
        self._nvenc_state = ok
        self.after(0, lambda: self.accel_label.configure(text=self.t("nvenc_ready" if ok else "nvenc_unavailable"), fg=(SUCCESS if ok else MUTED)))

    def _validate_video(self, path: str) -> bool:
        if not path or not Path(path).is_file():
            messagebox.showerror(self.t("file_not_found_title"), self.t("file_not_found"), parent=self)
            return False
        if not is_video_file(path):
            ext = Path(path).suffix or self.t("no_extension")
            messagebox.showerror(self.t("not_video_title"), self.t("not_video", ext=ext), parent=self)
            return False
        return True

    def pick_main(self):
        path = filedialog.askopenfilename(title=self.t("pick_main_title"), filetypes=self._video_types())
        if path:
            self.set_main(path)

    def pick_bottom(self):
        path = filedialog.askopenfilename(title=self.t("pick_bottom_title"), filetypes=self._video_types())
        if path:
            self.set_bottom(path)

    def pick_output(self):
        if self.mode.get() == "multi":
            initial_dir = self.output_dir.get().strip()
            if not initial_dir and self.main_video.get():
                initial_dir = str(Path(self.main_video.get()).parent)
            path = filedialog.askdirectory(
                title=self.t("pick_output_folder"),
                initialdir=initial_dir if initial_dir and Path(initial_dir).exists() else None,
            )
            if path:
                self.output_dir.set(os.path.normpath(path))
                self._refresh_output_label()
            return

        initial = self.output_file.get() or "tiktok_output.mp4"
        path = filedialog.asksaveasfilename(
            title=self.t("pick_output_file"),
            initialfile=Path(initial).name,
            initialdir=str(Path(initial).parent) if Path(initial).parent.exists() else None,
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4")],
        )
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.output_file.set(path)
            self._refresh_output_label()

    def drop_main(self, path):
        self.set_main(path)

    def drop_bottom(self, path):
        self.set_bottom(path)

    def _drop_output(self, event):
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data.strip("{}")]
        if not paths:
            return
        p = Path(paths[0])

        if self.mode.get() == "multi":
            folder = p if p.is_dir() else p.parent
            if folder.exists() and folder.is_dir():
                self.output_dir.set(str(folder))
                self._refresh_output_label()
            return

        if p.is_dir():
            name = Path(self.main_video.get()).stem + "_tiktok.mp4" if self.main_video.get() else "tiktok_output.mp4"
            out = p / name
        else:
            out = p if p.suffix.lower() == ".mp4" else p.with_suffix(".mp4")
        self.output_file.set(str(out))
        self._refresh_output_label()

    def set_main(self, path: str):
        path = os.path.normpath(path)
        if not self._validate_video(path):
            return
        self.main_video.set(path)
        self.main_zone.set_path(path)
        if not self.output_file.get():
            p = Path(path)
            self.output_file.set(str(p.with_name(p.stem + "_tiktok.mp4")))
        self._refresh_output_label()

        self.main_duration = 0.0
        self._main_probe_generation += 1
        generation = self._main_probe_generation
        self._refresh_batch_summary()
        self._refresh_render_button()
        self._set_status("main_added")
        self._set_detail("probing_duration", name=Path(path).name)
        threading.Thread(target=self._probe_main_duration, args=(generation, path), daemon=True).start()
        self.update_preview()

    def _probe_main_duration(self, generation: int, path: str):
        duration = self.engine.get_duration(path)
        self.after(0, lambda: self._apply_main_duration(generation, path, duration))

    def _apply_main_duration(self, generation: int, path: str, duration: float):
        if generation != self._main_probe_generation or self.main_video.get() != path:
            return
        self.main_duration = duration
        self._refresh_batch_summary()
        self._refresh_render_button()
        if duration > 0:
            self._set_detail("duration_ok", name=Path(path).name, duration=format_duration(duration))
        else:
            self._set_detail("duration_unknown", name=Path(path).name)

    def set_bottom(self, path: str):
        path = os.path.normpath(path)
        if not self._validate_video(path):
            return
        self.bottom_video.set(path)
        self.bottom_zone.set_path(path)
        self.bottom_duration = 0.0
        self._bottom_probe_generation += 1
        generation = self._bottom_probe_generation
        self._set_status("bottom_added")
        self._set_detail("probing_duration", name=Path(path).name)
        threading.Thread(target=self._probe_bottom_duration, args=(generation, path), daemon=True).start()
        self.update_preview()

    def _probe_bottom_duration(self, generation: int, path: str):
        duration = self.engine.get_duration(path)
        self.after(0, lambda: self._apply_bottom_duration(generation, path, duration))

    def _apply_bottom_duration(self, generation: int, path: str, duration: float):
        if generation != self._bottom_probe_generation or self.bottom_video.get() != path:
            return
        self.bottom_duration = duration
        if duration > 0:
            self._set_detail("bottom_duration_ok", name=Path(path).name, duration=format_duration(duration))
        else:
            self._set_detail("duration_unknown", name=Path(path).name)

    def update_preview(self):
        self._preview_generation += 1
        generation = self._preview_generation
        main = self.main_video.get()
        bottom = self.bottom_video.get()
        ratio = self.ratio.get()
        self.draw_preview()
        if not self.engine.ffmpeg or (not main and not bottom):
            return
        threading.Thread(target=self._generate_preview, args=(generation, main, bottom, ratio), daemon=True).start()

    def _generate_preview(self, generation, main, bottom, ratio):
        # Generate reasonably large source frames. draw_preview() resizes them to
        # the exact live preview rectangle, so there is no size mismatch/overflow.
        top_h, bottom_h = layout_heights(ratio)
        source_w = 540
        total_h = 960
        top_px = max(40, round(total_h * top_h / 1920))
        bottom_px = total_h - top_px
        paths = []
        for key, src, h in (("main", main, top_px), ("bottom", bottom, bottom_px)):
            if not src:
                paths.append(None)
                continue
            dest = self._temp_dir / f"{generation}_{key}.png"
            ok = self.engine.make_preview_png(src, str(dest), source_w, h)
            paths.append(str(dest) if ok else None)
        self.after(0, lambda: self._apply_preview(generation, paths))

    def _apply_preview(self, generation, paths):
        if generation != self._preview_generation:
            return
        imgs: list[Image.Image | None] = []
        for p in paths:
            if p and Path(p).exists():
                try:
                    with Image.open(p) as im:
                        imgs.append(im.convert("RGB").copy())
                except Exception:
                    imgs.append(None)
            else:
                imgs.append(None)
        while len(imgs) < 2:
            imgs.append(None)
        self._preview_sources = imgs[:2]
        self.draw_preview()

    def draw_preview(self):
        c = self.preview
        c.delete("all")
        w = max(320, c.winfo_width())
        h = max(420, c.winfo_height())

        # Leave room for the measurement labels and center the 9:16 frame in the
        # usable preview area. Integer coordinates prevent 1px drift on HiDPI.
        usable_w = max(180, w - 90)
        usable_h = max(260, h - 52)
        phone_h = int(min(usable_h, usable_w * 1920 / 1080, 430))
        phone_w = int(round(phone_h * 1080 / 1920))
        phone_h = int(round(phone_w * 1920 / 1080))
        x1 = int(round((w - phone_w) / 2 - 12))
        y1 = int(round((h - phone_h) / 2 - 4))
        x2 = x1 + phone_w
        y2 = y1 + phone_h

        top_h, _bottom_h = layout_heights(self.ratio.get())
        split_px = int(round(phone_h * top_h / 1920))
        split_px = max(1, min(phone_h - 1, split_px))

        # Build the full preview as one image, then apply one rounded mask. This
        # guarantees both videos are centered inside the frame and cannot stick
        # out at the sides. It also fixes the formerly sharp outer video corners.
        composite = Image.new("RGB", (phone_w, phone_h), "#17283d")
        top_src = self._preview_sources[0] if self._preview_sources else None
        bottom_src = self._preview_sources[1] if len(self._preview_sources) > 1 else None

        if top_src is not None:
            top_img = top_src.resize((phone_w, split_px), Image.Resampling.LANCZOS)
            composite.paste(top_img, (0, 0))
        else:
            top_fill = Image.new("RGB", (phone_w, split_px), "#17283d")
            composite.paste(top_fill, (0, 0))

        bottom_px = phone_h - split_px
        if bottom_src is not None:
            bottom_img = bottom_src.resize((phone_w, bottom_px), Image.Resampling.LANCZOS)
            composite.paste(bottom_img, (0, split_px))
        else:
            bottom_fill = Image.new("RGB", (phone_w, bottom_px), "#291d3d")
            composite.paste(bottom_fill, (0, split_px))

        radius = max(10, min(18, phone_w // 12))
        mask = Image.new("L", (phone_w, phone_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, phone_w - 1, phone_h - 1), radius=radius, fill=255)
        rgba = composite.convert("RGBA")
        rgba.putalpha(mask)
        self._preview_rendered = ImageTk.PhotoImage(rgba)

        # Dark outer bezel + neon outline, then the clipped image exactly centered.
        round_rect(c, x1 - 7, y1 - 7, x2 + 7, y2 + 7, radius=22, fill="#09111d", outline=CYAN, width=2)
        c.create_image(x1, y1, image=self._preview_rendered, anchor="nw")
        split_y = y1 + split_px
        c.create_line(x1 + 2, split_y, x2 - 2, split_y, fill=MAGENTA, width=2)

        if top_src is None:
            c.create_text((x1 + x2) / 2, y1 + split_px / 2, text=self.t("preview_main"), fill="#6f829b", font=("Segoe UI", 11, "bold"), justify="center")
        if bottom_src is None:
            c.create_text((x1 + x2) / 2, split_y + bottom_px / 2, text=self.t("preview_bottom"), fill="#8a6f9f", font=("Segoe UI", 9, "bold"), justify="center")

        c.create_text((x1 + x2) / 2, y2 + 15, text="1080 px", fill=MUTED, font=("Segoe UI", 8))
        c.create_text(x2 + 25, (y1 + y2) / 2, text="1920 px", fill=MUTED, font=("Segoe UI", 8), angle=90)

    def _set_progress_threadsafe(self, value: float):
        self.after(0, lambda v=value: self._set_progress(v))

    def _set_progress(self, value: float):
        self.progress.set(value)
        self.percent.set(f"{round(value * 100):d}%")

    def _localize_engine_status(self, text: str) -> str:
        if text == "NVENC не запустился на этом файле. Повторяем через CPU…":
            return self.t("engine_nvenc_fallback")
        if text.startswith("Рендер: "):
            return self.t("engine_render", encoder=text.split(":", 1)[1].strip())
        return text

    def _localize_engine_error(self, text: str) -> str:
        if self.language.get() == "ru":
            return text
        replacements = {
            "FFmpeg не найден.": "FFmpeg is unavailable.",
            "FFmpeg не найден": "FFmpeg is unavailable",
            "NVIDIA NVENC не смог инициализироваться.": "NVIDIA NVENC could not initialize.",
            "h264_nvenc отсутствует в этой сборке FFmpeg": "h264_nvenc is missing from this FFmpeg build",
            "FFmpeg завершился с ошибкой.": self.t("ffmpeg_failed"),
        }
        result = text
        for ru, en in replacements.items():
            result = result.replace(ru, en)
        prefix = "Некорректное соотношение блоков: "
        if result.startswith(prefix):
            return self.t("engine_bad_ratio", ratio=result[len(prefix):])
        if result == "Длительность сегмента должна быть больше нуля":
            return self.t("engine_segment_positive")
        return result

    def _set_status_threadsafe(self, text: str):
        self.after(0, lambda t=text: self.status.set(self._localize_engine_status(t)))

    def _set_status_detail_threadsafe(self, text: str):
        self.after(0, lambda t=text: self.status_detail.configure(text=t))

    def _set_render_state(self, active: bool):
        self._render_active = active
        self.mode_toggle.set_enabled(not active)
        self.render_btn.configure(state="disabled" if active else "normal")
        self.cancel_btn.configure(state="normal" if active else "disabled")
        if not active:
            self._refresh_render_button()

    def start_render(self):
        if self._render_active or (self._render_thread and self._render_thread.is_alive()):
            return

        main = self.main_video.get().strip()
        bottom = self.bottom_video.get().strip()
        if not self.engine.binaries_ok():
            messagebox.showerror(self.t("ffmpeg_missing_title"), self.t("ffmpeg_missing"), parent=self)
            return
        if not self._validate_video(main):
            return
        if not self._validate_video(bottom):
            return

        opts = RenderOptions(self.ratio.get(), self.quality.get(), self.encoder.get())
        self._cancel_requested.clear()
        if self.mode.get() == "multi":
            self._start_batch_render(main, bottom, opts)
        else:
            self._start_single_render(main, bottom, opts)

    # ------------------------- Single mode (v4.4 behavior) -------------------------
    def _start_single_render(self, main: str, bottom: str, opts: RenderOptions):
        output = self.output_file.get().strip()
        if not output:
            messagebox.showerror(self.t("save_where_title"), self.t("save_file_missing"), parent=self)
            return
        out = Path(output)
        if out.suffix.lower() != ".mp4":
            out = out.with_suffix(".mp4")
            output = str(out)
            self.output_file.set(output)
            self._refresh_output_label()
        if os.path.abspath(output) in {os.path.abspath(main), os.path.abspath(bottom)}:
            messagebox.showerror(self.t("overwrite_source_title"), self.t("overwrite_source"), parent=self)
            return
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror(self.t("folder_unavailable"), str(exc), parent=self)
            return

        self._set_render_state(True)
        self._set_progress(0.0)
        self._set_status("preparing")
        self.status_detail.configure(text=Path(output).name)
        self._render_thread = threading.Thread(
            target=self._single_render_worker, args=(main, bottom, output, opts), daemon=True
        )
        self._render_thread.start()

    def _single_render_worker(self, main, bottom, output, opts):
        ok, encoder, error = self.engine.render(
            main,
            bottom,
            output,
            opts,
            on_progress=self._set_progress_threadsafe,
            on_status=self._set_status_threadsafe,
        )
        self.after(0, lambda: self._single_render_finished(ok, encoder, error, output))

    def _single_render_finished(self, ok, encoder, error, output):
        self._set_render_state(False)
        if self._cancel_requested.is_set() and not ok:
            self._set_status("render_cancelled")
            self._set_detail("partial_deleted")
            return
        if ok:
            self._set_progress(1.0)
            self._set_status("done_encoder", encoder=encoder)
            size_mb = Path(output).stat().st_size / (1024 * 1024) if Path(output).exists() else 0
            self.status_detail.configure(text=f"{Path(output).name} • {size_mb:.1f} MB")
            messagebox.showinfo(self.t("saved_title"), self.t("saved_single", output=output, encoder=encoder, size=size_mb), parent=self)
        else:
            self._set_status("render_error")
            self._set_detail("ffmpeg_error_detail")
            messagebox.showerror(self.t("ffmpeg_error_title"), self._localize_engine_error(error[-4500:] if error else self.t("unknown_error")), parent=self)

    # ------------------------------ Batch / Multi mode -----------------------------
    def _start_batch_render(self, main: str, bottom: str, opts: RenderOptions):
        seg = self._segment_value()
        if seg is None:
            messagebox.showerror(self.t("segment_title"), self.t("segment_error"), parent=self)
            return

        out_dir_text = self.output_dir.get().strip()
        if not out_dir_text:
            messagebox.showerror(self.t("save_where_title"), self.t("save_folder_missing"), parent=self)
            return
        out_dir = Path(out_dir_text)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror(self.t("folder_unavailable"), str(exc), parent=self)
            return
        if not out_dir.is_dir():
            messagebox.showerror(self.t("folder_unavailable"), self.t("not_a_folder"), parent=self)
            return

        self._set_render_state(True)
        self._set_progress(0.0)
        self.percent.set("0%")
        self._set_status("preparing_batch")
        self._set_detail("checking_batch")
        self._render_thread = threading.Thread(
            target=self._batch_prepare_worker,
            args=(main, bottom, out_dir, seg, opts),
            daemon=True,
        )
        self._render_thread.start()

    def _batch_prepare_worker(self, main: str, bottom: str, out_dir: Path, seg: int, opts: RenderOptions):
        main_duration = self.main_duration if self.main_duration > 0 else self.engine.get_duration(main)
        bottom_duration = self.bottom_duration if self.bottom_duration > 0 else self.engine.get_duration(bottom)
        if self._cancel_requested.is_set():
            self.after(0, lambda: self._batch_cancelled(0, out_dir))
            return
        use_nvenc, encoder_label, encoder_error = self.engine.resolve_encoder(opts)
        self.after(
            0,
            lambda: self._batch_prepare_ready(
                main, bottom, out_dir, seg, opts, main_duration, bottom_duration,
                use_nvenc, encoder_label, encoder_error
            ),
        )

    def _batch_prepare_ready(
        self, main: str, bottom: str, out_dir: Path, seg: int, opts: RenderOptions,
        main_duration: float, bottom_duration: float, use_nvenc: bool,
        encoder_label: str, encoder_error: str,
    ):
        if self._cancel_requested.is_set():
            self._batch_cancelled(0, out_dir)
            return
        if main_duration <= 0:
            self._batch_prepare_failed(self.t("main_duration_error"))
            return
        if bottom_duration <= 0:
            self._batch_prepare_failed(self.t("bottom_duration_error"))
            return
        if encoder_error:
            self._batch_prepare_failed(encoder_error)
            return

        self.main_duration = main_duration
        self.bottom_duration = bottom_duration
        self._refresh_batch_summary()
        self._refresh_render_button()

        count = segment_count(main_duration, seg)
        if count <= 0:
            self._batch_prepare_failed(self.t("count_error"))
            return
        digits = max(3, len(str(count)))
        stem = Path(main).stem
        outputs = [out_dir / f"{stem}_{i:0{digits}d}.mp4" for i in range(1, count + 1)]
        existing = [p for p in outputs if p.exists()]
        if existing:
            answer = messagebox.askyesno(
                self.t("existing_title"),
                self.t("existing_prompt", existing=len(existing), count=count),
                parent=self,
            )
            if not answer:
                self._set_status("not_started")
                self._set_detail("existing_kept")
                self._set_render_state(False)
                return

        self._batch_started_at = time.monotonic()
        self._eta_smoothed = None
        self._speed_smoothed = None
        self.status.set(self.t("batch_status", index=1, count=count, percent=0, eta=self.t("eta_calculating"), speed="—x", encoder=encoder_label))
        self.status_detail.configure(text=self.t("bottom_timeline", filename=outputs[0].name))
        self._render_thread = threading.Thread(
            target=self._batch_render_worker,
            args=(main, bottom, out_dir, seg, opts, main_duration, bottom_duration, use_nvenc, encoder_label, outputs),
            daemon=True,
        )
        self._render_thread.start()

    def _batch_prepare_failed(self, error: str):
        self._set_render_state(False)
        self._set_status("batch_prepare_failed")
        self._set_detail("check_inputs")
        messagebox.showerror(self.t("prepare_error_title"), self._localize_engine_error(error[-4500:]), parent=self)

    def _batch_render_worker(
        self, main: str, bottom: str, out_dir: Path, seg: int, opts: RenderOptions,
        main_duration: float, bottom_duration: float, use_nvenc: bool, encoder_label: str,
        outputs: list[Path],
    ):
        count = len(outputs)
        completed = 0
        for index, output in enumerate(outputs):
            if self._cancel_requested.is_set():
                self.after(0, lambda c=completed: self._batch_cancelled(c, out_dir))
                return

            main_start = index * seg
            clip_duration = min(float(seg), max(0.0, main_duration - main_start))
            if clip_duration <= 0.001:
                break
            # Continuous bottom timeline: each clip starts exactly where the global
            # timeline says it should. stream_loop then wraps through 0 seamlessly.
            bottom_start = main_start % bottom_duration

            def metrics(progress: float, speed: float, *, idx=index, start=main_start, dur=clip_duration, name=output.name):
                self._batch_metrics(idx, count, start, dur, progress, speed, main_duration, encoder_label, name)

            ok, error = self.engine.render_segment(
                main=main,
                bottom=bottom,
                output=str(output),
                options=opts,
                use_nvenc=use_nvenc,
                main_start=main_start,
                segment_duration=clip_duration,
                bottom_start=bottom_start,
                on_metrics=metrics,
            )
            if not ok:
                if self._cancel_requested.is_set():
                    self.after(0, lambda c=completed: self._batch_cancelled(c, out_dir))
                else:
                    self.after(
                        0,
                        lambda i=index, n=output.name, e=error: self._batch_failed(i, count, n, e),
                    )
                return
            completed += 1

        elapsed = max(0.0, time.monotonic() - self._batch_started_at)
        self.after(0, lambda: self._batch_finished(completed, out_dir, encoder_label, elapsed))

    def _batch_metrics(
        self, index: int, count: int, main_start: float, clip_duration: float,
        clip_progress: float, speed: float, total_duration: float, encoder_label: str, filename: str,
    ):
        processed = min(total_duration, main_start + clip_duration * max(0.0, min(1.0, clip_progress)))
        overall = processed / total_duration if total_duration > 0 else 0.0
        elapsed = max(0.0, time.monotonic() - self._batch_started_at)

        eta_text = self.t("eta_calculating")
        if elapsed >= 1.0 and overall >= 0.002:
            raw_eta = max(0.0, elapsed * (1.0 - overall) / overall)
            if self._eta_smoothed is None:
                self._eta_smoothed = raw_eta
            else:
                # EWMA keeps ETA useful instead of jumping on every segment boundary.
                self._eta_smoothed = self._eta_smoothed * 0.78 + raw_eta * 0.22
            eta_text = self.t("eta_remaining", eta=format_eta(self._eta_smoothed, self.language.get()))

        if speed > 0:
            if self._speed_smoothed is None:
                self._speed_smoothed = speed
            else:
                self._speed_smoothed = self._speed_smoothed * 0.7 + speed * 0.3
        speed_text = f"{self._speed_smoothed:.1f}x" if self._speed_smoothed and self._speed_smoothed > 0 else "—x"
        overall_pct = round(overall * 100)
        current_pct = round(max(0.0, min(1.0, clip_progress)) * 100)
        status = self.t("batch_status", index=index + 1, count=count, percent=overall_pct, eta=eta_text, speed=speed_text, encoder=encoder_label)
        detail = self.t("batch_detail", filename=filename, percent=current_pct, elapsed=format_eta(elapsed, self.language.get()))
        self.after(0, lambda: self._apply_batch_metrics(overall, status, detail))

    def _apply_batch_metrics(self, overall: float, status: str, detail: str):
        if not self._render_active:
            return
        self._set_progress(overall)
        self.status.set(status)
        self.status_detail.configure(text=detail)

    def _batch_finished(self, completed: int, out_dir: Path, encoder_label: str, elapsed: float):
        self._set_render_state(False)
        self._set_progress(1.0)
        self.status.set(self.t("batch_done_status", count=completed, encoder=encoder_label))
        self.status_detail.configure(text=self.t("batch_done_detail", folder=out_dir, elapsed=format_eta(elapsed, self.language.get())))
        messagebox.showinfo(
            self.t("saved_title"),
            self.t("batch_done_message", count=completed, folder=out_dir, encoder=encoder_label, elapsed=format_eta(elapsed, self.language.get())),
            parent=self,
        )

    def _batch_cancelled(self, completed: int, out_dir: Path):
        self._set_render_state(False)
        self._set_status("batch_cancelled")
        self.status_detail.configure(text=self.t("batch_cancelled_detail", count=completed, folder=out_dir))
        # Completed clips are intentionally kept; render_segment removes the current partial file.

    def _batch_failed(self, index: int, count: int, filename: str, error: str):
        self._set_render_state(False)
        self.status.set(self.t("clip_error_status", index=index + 1, count=count))
        self.status_detail.configure(text=self.t("queue_stopped", filename=filename))
        messagebox.showerror(
            self.t("clip_error_title", filename=filename),
            self._localize_engine_error(error[-4300:] if error else self.t("ffmpeg_failed")),
            parent=self,
        )

    def cancel_render(self):
        if not self._render_active:
            return
        self._cancel_requested.set()
        self._set_status("stopping")
        self._set_detail("stopping_detail")
        self.engine.cancel()

    def on_close(self):
        try:
            self.engine.cancel()
        except Exception:
            pass
        try:
            for p in self._temp_dir.glob("*"):
                p.unlink(missing_ok=True)
            self._temp_dir.rmdir()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
