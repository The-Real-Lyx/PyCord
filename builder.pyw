#!/usr/bin/env python3
"""
PyCord Builder (GUI)
--------------------
Modern, fully dark-themed GUI with:
  - Animated particle background drawn directly on the canvas
  - Custom title bar (no native white chrome)
  - All widgets placed on the canvas so particles show through the gaps
  - Dark-themed dialogs (no white messagebox)

The build runs in a background thread so the GUI stays responsive.

Fixes / Features:
  - Dialogs are always centered in the middle of the screen
  - Log area is bigger by default and can be resized
  - Particles are strictly kept BEHIND all UI elements
  - Layout is recalculated after the window has its real size, so the
    right-side widgets (Quit button, etc.) are never cut off – no need
    to move the window manually anymore
  - Minimum size is enforced in both width and height
"""

from __future__ import annotations

import ctypes
import math
import os
import queue
import random
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    W,
    X,
    Y,
    BooleanVar,
    StringVar,
    Text,
    Tk,
    Toplevel,
    filedialog,
)
from tkinter import ttk
from tkinter import Canvas as _TkCanvas
from tkinter import Frame as _TkFrame
from tkinter import Label as _TkLabel
from tkinter import Button as _TkButton


# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #
APP_NAME = "PyCord"
ENTRY_SCRIPT = "PyCord.py"
DATA_FILE = "Data.txt"
TITLE = "PyCord Builder"
WINDOW_W = 820
WINDOW_H = 900
MIN_W = 760
MIN_H = 820

# Particle tuning
PARTICLE_COUNT = 45
PARTICLE_MAX_SPEED = 0.45
PARTICLE_MIN_RADIUS = 1.0
PARTICLE_MAX_RADIUS = 2.6
PARTICLE_LINK_DIST = 140
PARTICLE_MARGIN = 4

# Animation tuning
ANIM_DELAY_FAST = 30
ANIM_DELAY_SLOW = 45
ANIM_LINE_THRESHOLD = 400

ENABLE_PARTICLES = True


# --------------------------------------------------------------------------- #
#  Color palette
# --------------------------------------------------------------------------- #
class Palette:
    BG          = "#0f1115"
    TITLEBAR    = "#0a0c10"
    SURFACE     = "#171a21"
    SURFACE_2   = "#1e2229"
    BORDER      = "#2a2f38"
    TEXT        = "#e6e8eb"
    TEXT_MUTED  = "#8b939e"
    ACCENT      = "#5865f2"
    ACCENT_HOV  = "#4752c4"
    SUCCESS     = "#3ba55d"
    ERROR       = "#ed4245"
    WARNING     = "#faa61a"
    LOG_BG      = "#0b0d10"

    PARTICLE_A  = "#5865f2"
    PARTICLE_B  = "#7289da"
    LINE_COLOR  = "#5865f2"


# --------------------------------------------------------------------------- #
#  Admin helpers
# --------------------------------------------------------------------------- #
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )


# --------------------------------------------------------------------------- #
#  Core build logic
# --------------------------------------------------------------------------- #
class BuildError(Exception):
    pass


class Builder:
    def __init__(self, base_dir: Path, log):
        self.base_dir = base_dir
        self.log = log

    def _run(self, cmd: list[str], **kwargs) -> int:
        self.log(f"  > {' '.join(str(c) for c in cmd)}")
        return subprocess.run(cmd, **kwargs).returncode

    def _pip_show(self, package: str) -> bool:
        return subprocess.run(
            [sys.executable, "-m", "pip", "show", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0

    def _pip_uninstall(self, package: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _safe_rmtree(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _safe_unlink(self, path: Path) -> None:
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    def check_pathlib(self) -> None:
        self.log("Checking for incompatible 'pathlib' package...")
        if self._pip_show("pathlib"):
            self.log("   Removing outdated 'pathlib' package...")
            self._pip_uninstall("pathlib")
            self.log("   [OK] 'pathlib' removed.")
        else:
            self.log("   [OK] No conflicts found.")
        self.log("")

    def check_entry_script(self) -> Path:
        script = self.base_dir / ENTRY_SCRIPT
        if not script.is_file():
            raise BuildError(
                f"{ENTRY_SCRIPT} was not found!\nExpected at: {script}"
            )
        self.log(f"[OK] {ENTRY_SCRIPT} found.\n")
        return script

    def write_data_file(self, token: str, server: str) -> Path:
        data_file = self.base_dir / DATA_FILE
        self.log("Writing Data.txt ...")
        data_file.write_text(
            f"Token={token}\nServer={server}\n", encoding="utf-8"
        )
        if not data_file.is_file():
            raise BuildError("Data.txt could not be created!")
        self.log("[OK] Data.txt created.\n")
        return data_file

    def clean_old_artifacts(self) -> None:
        self.log("Cleaning up old build files...")
        self._safe_rmtree(self.base_dir / "build")
        self._safe_rmtree(self.base_dir / "dist")
        self._safe_unlink(self.base_dir / f"{APP_NAME}.spec")
        self.log("[OK] Cleanup complete.\n")

    def build(self, entry_script, data_file, logo) -> Path:
        self.log("Building EXE with PyInstaller...\n")
        cmd: list[str] = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--onefile", "--noconsole",
            "--name", APP_NAME,
            "--add-data", f"{data_file};.",
        ]
        if logo:
            cmd += ["--icon", logo]
        cmd.append(str(entry_script))

        self.log(f"Command: {' '.join(cmd)}\n")
        rc = self._run(cmd, cwd=self.base_dir)
        if rc != 0:
            raise BuildError(f"PyInstaller failed (exit code {rc}).")

        self.log("")
        self.log("[OK] Build complete.\n")

        exe = self.base_dir / "dist" / f"{APP_NAME}.exe"
        if not exe.is_file():
            raise BuildError("The built EXE was not found in dist/!")
        return exe

    def copy_to_desktop(self, exe: Path, out_dir: Path) -> Path:
        self.log("Copying EXE to Desktop...")
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{APP_NAME}.exe"
        self._safe_unlink(target)
        shutil.copy2(exe, target)
        if not target.is_file():
            raise BuildError("EXE could not be copied to the Desktop!")
        self.log(f"[OK] {APP_NAME}.exe is now on the Desktop.\n")
        return target

    def cleanup(self) -> None:
        self._safe_rmtree(self.base_dir / "build")
        self._safe_rmtree(self.base_dir / "dist")
        self._safe_unlink(self.base_dir / f"{APP_NAME}.spec")


# --------------------------------------------------------------------------- #
#  Particle
# --------------------------------------------------------------------------- #
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "radius", "color")

    def __init__(self, x, y, vx, vy, radius, color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = radius
        self.color = color


# --------------------------------------------------------------------------- #
#  Custom title bar
# --------------------------------------------------------------------------- #
class TitleBar(_TkFrame):
    def __init__(self, master, root: Tk, title: str):
        super().__init__(master, bg=Palette.TITLEBAR, height=38)
        self.pack_propagate(False)
        self.root = root
        self._drag_offset = (0, 0)
        self._maximized = False
        self._restore_geo = None

        left = _TkFrame(self, bg=Palette.TITLEBAR)
        left.pack(side=LEFT, fill=Y, padx=(14, 0))

        _TkLabel(
            left, text="◆", bg=Palette.TITLEBAR, fg=Palette.ACCENT,
            font=("Segoe UI", 12),
        ).pack(side=LEFT, pady=8)

        _TkLabel(
            left, text=title, bg=Palette.TITLEBAR, fg=Palette.TEXT,
            font=("Segoe UI", 9),
        ).pack(side=LEFT, padx=(8, 0))

        right = _TkFrame(self, bg=Palette.TITLEBAR)
        right.pack(side=RIGHT, fill=Y)

        self._btn_close = self._mk_btn(right, "✕", self._on_close, hover="#c42b1c")
        self._btn_close.pack(side=RIGHT, fill=Y)

        self._btn_max = self._mk_btn(right, "□", self._on_max)
        self._btn_max.pack(side=RIGHT, fill=Y)

        self._btn_min = self._mk_btn(right, "—", self._on_min)
        self._btn_min.pack(side=RIGHT, fill=Y)

        drag_widgets = [self, left] + list(left.winfo_children())
        for w in drag_widgets:
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<Double-Button-1>", lambda e: self._on_max())

    def _mk_btn(self, parent, text, command, hover=None):
        btn = _TkButton(
            parent, text=text, command=command,
            bg=Palette.TITLEBAR, fg=Palette.TEXT_MUTED,
            activebackground=hover or Palette.SURFACE_2,
            activeforeground="#ffffff",
            font=("Segoe UI", 10),
            relief="flat", bd=0, width=4, cursor="hand2",
            highlightthickness=0,
        )
        btn.bind("<Enter>", lambda e, b=btn, h=hover: b.configure(
            bg=h or Palette.SURFACE_2,
            fg="#ffffff" if h else Palette.TEXT,
        ))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(
            bg=Palette.TITLEBAR, fg=Palette.TEXT_MUTED,
        ))
        return btn

    def _start_drag(self, e):
        self._drag_offset = (e.x_root - self.root.winfo_x(),
                             e.y_root - self.root.winfo_y())

    def _on_drag(self, e):
        if self._maximized:
            return
        x = e.x_root - self._drag_offset[0]
        y = e.y_root - self._drag_offset[1]
        self.root.geometry(f"+{x}+{y}")

    def _on_min(self):
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.after(10, self._reenable_override)

    def _reenable_override(self):
        if self.root.state() == "normal":
            self.root.overrideredirect(True)
        else:
            self.root.bind(
                "<Map>", lambda e: self.root.overrideredirect(True), add="+"
            )

    def _on_max(self):
        if self._maximized:
            if self._restore_geo:
                self.root.geometry(self._restore_geo)
            self._maximized = False
        else:
            self._restore_geo = self.root.geometry()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh - 40}+0+0")
            self._maximized = True

    def _on_close(self):
        self.root.event_generate("<<TitleBarClose>>")


# --------------------------------------------------------------------------- #
#  Dark dialog  (always centered on the screen)
# --------------------------------------------------------------------------- #
class DarkDialog(Toplevel):
    def __init__(
        self, parent, title: str, message: str,
        kind: str = "info", buttons: tuple[str, ...] = ("OK",),
    ):
        super().__init__(parent)
        self.result: str | None = None

        # IMPORTANT: do NOT enable overrideredirect yet. Windows ignores
        # geometry() on an unmapped overrideredirect window and places
        # it at (0,0) - top-left. So build the window normally first.
        self.withdraw()  # hide until we've positioned it
        self.transient(parent)
        self.configure(bg=Palette.BORDER)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        border = _TkFrame(self, bg=Palette.BORDER, padx=1, pady=1)
        border.pack(fill=BOTH, expand=True)

        wrap = _TkFrame(border, bg=Palette.SURFACE, padx=24, pady=20)
        wrap.pack(fill=BOTH, expand=True)

        if kind == "error":
            icon_text, icon_color = "✖", Palette.ERROR
        elif kind == "question":
            icon_text, icon_color = "?", Palette.ACCENT
        else:
            icon_text, icon_color = "ℹ", Palette.SUCCESS

        _TkLabel(
            wrap, text=icon_text, bg=Palette.SURFACE, fg=icon_color,
            font=("Segoe UI Semibold", 22),
        ).pack(anchor=W)

        _TkLabel(
            wrap, text=title, bg=Palette.SURFACE, fg=Palette.TEXT,
            font=("Segoe UI Semibold", 11),
            justify="left", anchor=W, wraplength=440,
        ).pack(anchor=W, pady=(8, 4))

        _TkLabel(
            wrap, text=message, bg=Palette.SURFACE, fg=Palette.TEXT_MUTED,
            font=("Segoe UI", 10),
            justify="left", anchor=W, wraplength=440,
        ).pack(anchor=W)

        btn_row = _TkFrame(wrap, bg=Palette.SURFACE)
        btn_row.pack(fill=X, pady=(20, 0))

        for i, label in enumerate(reversed(buttons)):
            is_primary = (i == 0)
            b = _TkButton(
                btn_row, text=label,
                command=lambda lbl=label: self._choose(lbl),
                bg=Palette.ACCENT if is_primary else Palette.SURFACE_2,
                fg="#ffffff" if is_primary else Palette.TEXT,
                activebackground=(
                    Palette.ACCENT_HOV if is_primary else Palette.BORDER
                ),
                activeforeground="#ffffff" if is_primary else Palette.TEXT,
                font=("Segoe UI Semibold", 9) if is_primary else ("Segoe UI", 9),
                relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                highlightthickness=0,
            )
            b.pack(side=RIGHT, padx=(8, 0))

        self._d_off = (0, 0)
        self.bind("<ButtonPress-1>", self._start_drag)
        self.bind("<B1-Motion>", self._on_drag)
        wrap.bind("<ButtonPress-1>", self._start_drag)
        wrap.bind("<B1-Motion>", self._on_drag)

        self.bind("<Escape>", lambda e: self._choose(buttons[-1]))
        if buttons:
            self.bind("<Return>", lambda e: self._choose(buttons[0]))

        # Compute size, center on screen, THEN show
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        x = max(0, min(sw - w, x))
        y = max(0, min(sh - h, y))

        # Set geometry BEFORE deiconify / overrideredirect
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Now enable the borderless look and show it
        self.overrideredirect(True)
        self.deiconify()

        # Force the position once more (Windows sometimes shifts
        # overrideredirect windows after the first map)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.lift()
        self.focus_force()
        self.grab_set()

        # And once more after the event loop has processed the map
        self.after(0, lambda: self._force_position(x, y))
        self.after(30, lambda: self._force_position(x, y))

    def _force_position(self, x: int, y: int) -> None:
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            self.geometry(f"{w}x{h}+{x}+{y}")
            self.lift()
        except Exception:
            pass

    def _start_drag(self, e):
        self._d_off = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _on_drag(self, e):
        x = e.x_root - self._d_off[0]
        y = e.y_root - self._d_off[1]
        self.geometry(f"+{x}+{y}")

    def _choose(self, value: str) -> None:
        self.result = value
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _bring_to_front(self):
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
        except Exception:
            pass

    def _center_on_screen(self) -> None:
        """Center the dialog on the primary screen. This is reliable and
        does not depend on the parent window's (possibly unreliable)
        geometry."""
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        x = (sw - w) // 2
        y = (sh - h) // 2

        # Keep inside the screen
        x = max(0, min(sw - w, x))
        y = max(0, min(sh - h, y))

        self.geometry(f"{w}x{h}+{x}+{y}")

    def _start_drag(self, e):
        self._d_off = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _on_drag(self, e):
        x = e.x_root - self._d_off[0]
        y = e.y_root - self._d_off[1]
        self.geometry(f"+{x}+{y}")

    def _choose(self, value: str) -> None:
        self.result = value
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def dark_info(parent, title, message):
    dlg = DarkDialog(parent, title, message, "info", ("OK",))
    parent.wait_window(dlg)


def dark_error(parent, title, message):
    dlg = DarkDialog(parent, title, message, "error", ("OK",))
    parent.wait_window(dlg)


def dark_ask(parent, title, message) -> bool:
    dlg = DarkDialog(parent, title, message, "question", ("Yes", "No"))
    parent.wait_window(dlg)
    return dlg.result == "Yes"


# --------------------------------------------------------------------------- #
#  Card drawing helper
# --------------------------------------------------------------------------- #
def make_card(parent_canvas, x, y, w, h, title):
    tag = ("ui", "card")

    parent_canvas.create_rectangle(
        x + 2, y + 4, x + w + 2, y + h + 4,
        fill="#000000", outline="", stipple="gray25",
        tags=tag,
    )
    parent_canvas.create_rectangle(
        x, y, x + w, y + h,
        fill=Palette.SURFACE, outline=Palette.BORDER,
        tags=tag,
    )
    parent_canvas.create_line(
        x + 16, y + 42, x + w - 16, y + 42,
        fill=Palette.BORDER,
        tags=tag,
    )
    parent_canvas.create_text(
        x + 16, y + 22, text=title, anchor="w",
        fill=Palette.TEXT, font=("Segoe UI Semibold", 10),
        tags=tag,
    )


# --------------------------------------------------------------------------- #
#  Main GUI
# --------------------------------------------------------------------------- #
class BuilderGUI:
    CONFIG_CARD_H = 340
    LOG_MIN_H = 260
    STATUS_H = 42

    def __init__(self, root: Tk):
        self.root = root
        self.base_dir = Path(__file__).resolve().parent
        self.out_dir = Path(os.environ["USERPROFILE"]) / "Desktop"

        self.token_var = StringVar()
        self.server_var = StringVar()
        self.logo_var = StringVar()
        self.show_token_var = BooleanVar(value=False)
        self.status_var = StringVar(value="Ready.")
        self.building = False

        self.particles: list[Particle] = []
        self._dot_ids: list[int] = []
        self._line_pool: list[int] = []
        self._running = True
        self._last_canvas_size = (0, 0)
        self._fade_cache: dict[tuple[str, int], str] = {}
        self._last_resize: tuple[int, int] | None = None
        self._relayout_jobs: list[str] = []

        self.msg_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._setup_window()
        self._setup_styles()
        self._build_ui()

        # Force the window manager to actually realize the window.
        self.root.update_idletasks()
        self.root.update()

        # Windows doesn't hand out the final geometry for overrideredirect
        # windows immediately. Schedule several follow-up layout passes
        # over the next second so the first paint is always correct –
        # without needing to move the window manually.
        for delay in (10, 40, 90, 160, 260, 400, 650, 1000):
            self._relayout_jobs.append(
                self.root.after(delay, self._relayout)
            )

        if ENABLE_PARTICLES:
            self._spawn_particles()
            self._animate()
        self._poll_queue()

    # -- Window chrome ------------------------------------------------------ #
    def _setup_window(self) -> None:
        self.root.title(TITLE)
        self.root.overrideredirect(True)
        self.root.configure(bg=Palette.BORDER)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - WINDOW_W) // 2
        y = max(20, (sh - WINDOW_H) // 2 - 20)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")

        try:
            self.root.minsize(MIN_W, MIN_H)
        except Exception:
            pass

        self.root.bind("<Alt-F4>", lambda e: self._on_quit())

    # -- Styles ------------------------------------------------------------- #
    def _setup_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Dark.TEntry",
            fieldbackground=Palette.SURFACE_2,
            foreground=Palette.TEXT,
            insertcolor=Palette.TEXT,
            bordercolor=Palette.BORDER,
            lightcolor=Palette.BORDER,
            darkcolor=Palette.BORDER,
            borderwidth=1, relief="flat", padding=8,
        )
        style.map(
            "Dark.TEntry",
            bordercolor=[("focus", Palette.ACCENT)],
            lightcolor=[("focus", Palette.ACCENT)],
            darkcolor=[("focus", Palette.ACCENT)],
        )

        style.configure(
            "Dark.Vertical.TScrollbar",
            background=Palette.SURFACE_2,
            troughcolor=Palette.LOG_BG,
            bordercolor=Palette.LOG_BG,
            arrowcolor=Palette.TEXT_MUTED,
            borderwidth=0,
        )
        style.map(
            "Dark.Vertical.TScrollbar",
            background=[("active", Palette.BORDER)],
        )

    # -- UI ---------------------------------------------------------------- #
    def _build_ui(self) -> None:
        border = _TkFrame(self.root, bg=Palette.BORDER)
        border.pack(fill=BOTH, expand=True, padx=1, pady=1)

        inner = _TkFrame(border, bg=Palette.BG)
        inner.pack(fill=BOTH, expand=True)

        self.titlebar = TitleBar(inner, self.root, TITLE)
        self.titlebar.pack(fill=X)
        self.root.bind("<<TitleBarClose>>", lambda e: self._on_quit())

        self.canvas = _TkCanvas(
            inner, bg=Palette.BG, highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill=BOTH, expand=True)

        self._layout_content()

        # React to both the root window and the canvas resizing.
        self.root.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Configure>", self._on_resize)

        # When the window is first mapped, do an extra relayout pass.
        self.root.bind(
            "<Map>",
            lambda e: self.root.after(20, self._relayout),
            add="+",
        )

    def _relayout(self) -> None:
        """Re-run layout once the window/canvas has its real size."""
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            # Canvas not realized yet – try again shortly.
            self.root.after(50, self._relayout)
            return

        cur = (w, h)
        if self._last_resize == cur:
            return
        self._last_resize = cur

        self._layout_content()
        self._set_building(self.building, silent=True)

    def _layout_content(self) -> None:
        c = self.canvas
        c.delete("ui")

        W = self.canvas.winfo_width() or WINDOW_W
        H = self.canvas.winfo_height() or (WINDOW_H - 38)
        pad = 22
        gap = 14

        # Header text
        c.create_text(
            pad, 20, text="PyCord Builder", anchor="w",
            fill=Palette.TEXT, font=("Segoe UI Semibold", 18),
            tags="ui",
        )
        c.create_text(
            pad, 46, anchor="w", tags="ui",
            text=f"Package your Discord bot into a standalone Windows executable   ·   {self.base_dir}",
            fill=Palette.TEXT_MUTED, font=("Segoe UI", 9),
        )

        # Config card
        config_y = 74
        config_h = self.CONFIG_CARD_H
        make_card(c, pad, config_y, W - 2 * pad, config_h, "Configuration")
        self._place_config_widgets(pad + 16, config_y + 56, W - 2 * pad - 32)

        # Action row
        action_y = config_y + config_h + gap
        self._place_action_widgets(pad, action_y, W - 2 * pad)

        # Log card
        log_y = action_y + 52 + gap
        log_h = H - log_y - self.STATUS_H
        if log_h < self.LOG_MIN_H:
            log_h = self.LOG_MIN_H
        make_card(c, pad, log_y, W - 2 * pad, log_h, "Build Output")
        self._place_log_widgets(
            pad + 16, log_y + 56, W - 2 * pad - 32, log_h - 72
        )

        # Status bar
        status_y = H - 26
        c.create_text(
            pad, status_y, text="●", anchor="w",
            fill=self._status_dot_color(), font=("Segoe UI", 9),
            tags=("ui", "status_dot"),
        )
        c.create_text(
            pad + 16, status_y, text=self.status_var.get(), anchor="w",
            fill=Palette.TEXT_MUTED, font=("Segoe UI", 9),
            tags=("ui", "status_text"),
        )

    # -- Widget placement helpers ------------------------------------------ #
    def _place_config_widgets(self, x, y, width):
        self._mk_label(x, y, "Discord Bot Token")
        self.token_entry = ttk.Entry(
            self.canvas, textvariable=self.token_var, show="*",
            style="Dark.TEntry",
        )
        self.canvas.create_window(
            x, y + 22, anchor="nw", window=self.token_entry,
            width=width - 100, height=34, tags="ui",
        )

        self.show_chk = _TkButton(
            self.canvas, text="⬜  show",
            command=self._toggle_token_visibility,
            bg=Palette.SURFACE, fg=Palette.TEXT_MUTED,
            activebackground=Palette.SURFACE, activeforeground=Palette.TEXT,
            font=("Segoe UI", 9), relief="flat", bd=0,
            cursor="hand2", highlightthickness=0,
        )
        self.canvas.create_window(
            x + width - 90, y + 22, anchor="nw",
            window=self.show_chk, width=90, height=34, tags="ui",
        )

        self._mk_label(x, y + 74, "Server ID (Guild ID)")
        self.server_entry = ttk.Entry(
            self.canvas, textvariable=self.server_var, style="Dark.TEntry",
        )
        self.canvas.create_window(
            x, y + 96, anchor="nw", window=self.server_entry,
            width=width, height=34, tags="ui",
        )

        self._mk_label(x, y + 148, "Logo (optional, .ico recommended)")
        self.logo_entry = ttk.Entry(
            self.canvas, textvariable=self.logo_var, style="Dark.TEntry",
        )
        self.canvas.create_window(
            x, y + 170, anchor="nw", window=self.logo_entry,
            width=width - 110, height=34, tags="ui",
        )

        self.browse_btn = self._mk_button(
            x + width - 100, y + 170, 100, 34,
            "Browse…", self._pick_logo, primary=False,
        )

        self.canvas.create_text(
            x, y + 218, anchor="w", tags="ui",
            text=f"Output:  {self.out_dir / (APP_NAME + '.exe')}",
            fill=Palette.TEXT_MUTED, font=("Segoe UI", 8),
        )

    def _place_action_widgets(self, x, y, width):
        self.build_btn = self._mk_button(
            x, y, 170, 42, "▶   Start Build",
            self._on_build, primary=True,
        )
        # Quit button anchored to the right edge of the content area
        quit_x = x + width - 100
        self.quit_btn = self._mk_button(
            quit_x, y, 100, 42, "Quit",
            self._on_quit, primary=False,
        )

    def _place_log_widgets(self, x, y, width, height):
        if height < 40:
            height = 40
        self.log_text = Text(
            self.canvas,
            wrap="word", font=("Cascadia Mono", 9),
            bg=Palette.LOG_BG, fg=Palette.TEXT,
            insertbackground=Palette.TEXT,
            relief="flat", borderwidth=0, padx=14, pady=12,
            highlightthickness=0,
            selectbackground=Palette.ACCENT, selectforeground="#ffffff",
        )
        self.canvas.create_window(
            x, y, anchor="nw", window=self.log_text,
            width=width - 16, height=height, tags="ui",
        )

        self.log_scroll = ttk.Scrollbar(
            self.canvas, command=self.log_text.yview,
            style="Dark.Vertical.TScrollbar",
        )
        self.canvas.create_window(
            x + width - 14, y, anchor="nw", window=self.log_scroll,
            width=14, height=height, tags="ui",
        )
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        self.log_text.configure(state="disabled")

        self.log_text.tag_configure("ok", foreground=Palette.SUCCESS)
        self.log_text.tag_configure("warn", foreground=Palette.WARNING)
        self.log_text.tag_configure("err", foreground=Palette.ERROR)
        self.log_text.tag_configure("muted", foreground=Palette.TEXT_MUTED)
        self.log_text.tag_configure(
            "title", foreground=Palette.TEXT,
            font=("Cascadia Mono", 9, "bold"),
        )

    # -- Small helpers ------------------------------------------------------ #
    def _mk_label(self, x, y, text):
        self.canvas.create_text(
            x, y, text=text, anchor="w", tags="ui",
            fill=Palette.TEXT_MUTED, font=("Segoe UI", 9),
        )

    def _mk_button(self, x, y, w, h, text, command, primary=True):
        bg = Palette.ACCENT if primary else Palette.SURFACE_2
        fg = "#ffffff" if primary else Palette.TEXT
        active_bg = Palette.ACCENT_HOV if primary else Palette.BORDER

        btn = _TkButton(
            self.canvas, text=text, command=command,
            bg=bg, fg=fg,
            activebackground=active_bg,
            activeforeground="#ffffff" if primary else Palette.TEXT,
            font=("Segoe UI Semibold", 10) if primary else ("Segoe UI", 10),
            relief="flat", bd=0, cursor="hand2", highlightthickness=0,
        )
        btn.bind("<Enter>", lambda e, b=btn, ab=active_bg: b.configure(bg=ab))
        btn.bind("<Leave>", lambda e, b=btn, nb=bg: b.configure(bg=nb))

        self.canvas.create_window(
            x, y, anchor="nw", window=btn, width=w, height=h, tags="ui",
        )
        return btn

    def _status_dot_color(self) -> str:
        if self.building:
            return Palette.WARNING
        return Palette.SUCCESS

    # -- Status / log ------------------------------------------------------- #
    def _update_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        try:
            self.canvas.itemconfigure("status_text", text=text)
            self.canvas.itemconfigure("status_dot", fill=color)
        except Exception:
            pass

    # -- Particles ---------------------------------------------------------- #
    def _canvas_size(self) -> tuple[int, int]:
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1:
            w = WINDOW_W
        if h <= 1:
            h = WINDOW_H - 38
        return w, h

    def _spawn_particles(self) -> None:
        W, H = self._canvas_size()
        self.particles.clear()

        cols = int(math.sqrt(PARTICLE_COUNT * W / max(1, H))) + 1
        rows = int(math.ceil(PARTICLE_COUNT / cols))

        cell_w = W / cols
        cell_h = H / rows
        margin = PARTICLE_MARGIN + PARTICLE_MAX_RADIUS

        spawned = 0
        for r in range(rows):
            for c in range(cols):
                if spawned >= PARTICLE_COUNT:
                    break
                x = (c + random.random()) * cell_w
                y = (r + random.random()) * cell_h
                x = max(margin, min(W - margin, x))
                y = max(margin, min(H - margin, y))

                vx = random.uniform(-PARTICLE_MAX_SPEED, PARTICLE_MAX_SPEED)
                vy = random.uniform(-PARTICLE_MAX_SPEED, PARTICLE_MAX_SPEED)
                radius = random.uniform(
                    PARTICLE_MIN_RADIUS, PARTICLE_MAX_RADIUS
                )
                color = random.choice(
                    [Palette.PARTICLE_A, Palette.PARTICLE_B]
                )
                self.particles.append(Particle(x, y, vx, vy, radius, color))
                spawned += 1

        for did in self._dot_ids:
            self.canvas.delete(did)
        self._dot_ids.clear()
        for p in self.particles:
            did = self.canvas.create_oval(
                p.x - p.radius, p.y - p.radius,
                p.x + p.radius, p.y + p.radius,
                fill=p.color, outline="", tags="bg",
            )
            self._dot_ids.append(did)

        for lid in self._line_pool:
            self.canvas.delete(lid)
        self._line_pool.clear()

        self._last_canvas_size = (W, H)
        self.canvas.tag_lower("bg")

    def _clamp_particle(self, p: Particle, W: int, H: int) -> None:
        m = PARTICLE_MARGIN
        if p.x < m:
            p.x = m
            p.vx = abs(p.vx)
        elif p.x > W - m:
            p.x = W - m
            p.vx = -abs(p.vx)

        if p.y < m:
            p.y = m
            p.vy = abs(p.vy)
        elif p.y > H - m:
            p.y = H - m
            p.vy = -abs(p.vy)

    def _animate(self) -> None:
        if not self._running:
            return

        W, H = self._canvas_size()

        last_w, last_h = self._last_canvas_size
        if abs(W - last_w) > 30 or abs(H - last_h) > 30:
            if last_w > 0 and last_h > 0:
                sx = W / last_w
                sy = H / last_h
                for p in self.particles:
                    p.x *= sx
                    p.y *= sy
            else:
                self._spawn_particles()
            self._last_canvas_size = (W, H)

        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            self._clamp_particle(p, W, H)

        for p, did in zip(self.particles, self._dot_ids):
            r = p.radius
            self.canvas.coords(did, p.x - r, p.y - r, p.x + r, p.y + r)

        n = len(self.particles)
        max_d = PARTICLE_LINK_DIST
        max_d_sq = max_d * max_d
        line_idx = 0

        for i in range(n):
            pi = self.particles[i]
            pxi, pyi = pi.x, pi.y
            for j in range(i + 1, n):
                pj = self.particles[j]
                dx = pxi - pj.x
                dy = pyi - pj.y
                dsq = dx * dx + dy * dy
                if dsq < max_d_sq:
                    dist = math.sqrt(dsq)
                    alpha = 1.0 - (dist / max_d)
                    color = self._fade(Palette.LINE_COLOR, alpha * 0.35)

                    if line_idx < len(self._line_pool):
                        lid = self._line_pool[line_idx]
                        self.canvas.coords(lid, pxi, pyi, pj.x, pj.y)
                        self.canvas.itemconfigure(lid, fill=color, state="normal")
                    else:
                        lid = self.canvas.create_line(
                            pxi, pyi, pj.x, pj.y,
                            fill=color, width=1, tags="bg",
                        )
                        self._line_pool.append(lid)

                    line_idx += 1

        for k in range(line_idx, len(self._line_pool)):
            self.canvas.itemconfigure(self._line_pool[k], state="hidden")

        # Keep particles strictly behind all UI elements
        self.canvas.tag_lower("bg")
        # And make sure the UI is above them
        self.canvas.tag_raise("ui")

        delay = ANIM_DELAY_SLOW if line_idx > ANIM_LINE_THRESHOLD else ANIM_DELAY_FAST
        self.root.after(delay, self._animate)

    def _fade(self, hex_color: str, factor: float) -> str:
        factor = max(0.0, min(1.0, factor))
        key = (hex_color, int(factor * 100))
        val = self._fade_cache.get(key)
        if val is not None:
            return val

        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        br = int(Palette.BG[1:3], 16)
        bg_ = int(Palette.BG[3:5], 16)
        bb = int(Palette.BG[5:7], 16)
        nr = int(br + (r - br) * factor)
        ng = int(bg_ + (g - bg_) * factor)
        nb = int(bb + (b - bb) * factor)
        val = f"#{nr:02x}{ng:02x}{nb:02x}"
        self._fade_cache[key] = val
        return val

    # -- Resize ------------------------------------------------------------- #
    def _on_resize(self, event) -> None:
        # React to both the root window and the canvas.
        if event.widget not in (self.root, self.canvas):
            return

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return

        # Enforce minimum size (overrideredirect ignores minsize on Windows)
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        if root_w < MIN_W or root_h < MIN_H:
            new_w = max(root_w, MIN_W)
            new_h = max(root_h, MIN_H)
            self.root.geometry(f"{new_w}x{new_h}")
            return

        new_size = (w, h)
        if self._last_resize == new_size:
            return
        self._last_resize = new_size

        self._layout_content()
        self._set_building(self.building, silent=True)

    # -- Actions ------------------------------------------------------------ #
    def _toggle_token_visibility(self) -> None:
        self.show_token_var.set(not self.show_token_var.get())
        self.token_entry.configure(
            show="" if self.show_token_var.get() else "*"
        )
        self.show_chk.configure(
            text="✅  show" if self.show_token_var.get() else "⬜  show"
        )

    def _pick_logo(self) -> None:
        path = filedialog.askopenfilename(
            title="Select logo",
            parent=self.root,
            filetypes=[
                ("Icon files", "*.ico"),
                ("Images", "*.png *.jpg *.jpeg *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.logo_var.set(path)

    def _on_quit(self) -> None:
        if self.building:
            if not dark_ask(
                self.root, "Build in progress",
                "A build is currently running. Quit anyway?",
            ):
                return
        self._running = False
        self.root.destroy()

    def _on_build(self) -> None:
        if self.building:
            return

        token = self.token_var.get().strip()
        server = self.server_var.get().strip()
        logo = self.logo_var.get().strip()

        if not token:
            dark_error(self.root, "Error", "Bot token must not be empty.")
            return
        if not server:
            dark_error(self.root, "Error", "Server ID must not be empty.")
            return
        if logo and not Path(logo).is_file():
            dark_error(self.root, "Error", f"Logo not found:\n{logo}")
            return

        summary = (
            f"Token:      {'*' * min(len(token), 12)}…\n"
            f"Server ID:  {server}\n"
            f"Logo:       {logo or '(none)'}\n"
            f"Target:     {self.out_dir / (APP_NAME + '.exe')}\n\n"
            f"Start build now?"
        )
        if not dark_ask(self.root, "Confirm build", summary):
            return

        self._set_building(True)
        self._clear_log()
        self._log("=" * 52, "muted")
        self._log("  PyCord EXE Builder", "title")
        self._log("=" * 52, "muted")
        self._log("")

        threading.Thread(
            target=self._worker,
            args=(token, server, logo or None),
            daemon=True,
        ).start()

    def _worker(self, token, server, logo):
        try:
            builder = Builder(self.base_dir, self._queue_log)
            builder.check_pathlib()
            entry_script = builder.check_entry_script()
            data_file = builder.write_data_file(token, server)
            builder.clean_old_artifacts()
            exe = builder.build(entry_script, data_file, logo)
            target = builder.copy_to_desktop(exe, self.out_dir)
            builder.cleanup()
            self.msg_queue.put(("done", str(target)))
        except BuildError as e:
            self.msg_queue.put(("error", str(e)))
        except Exception as e:
            self.msg_queue.put(("error", f"Unexpected error: {e}"))

    def _queue_log(self, text: str) -> None:
        self.msg_queue.put(("log", text))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "error":
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _log(self, text: str, tag: str | None = None) -> None:
        self.log_text.configure(state="normal")
        if tag is None:
            if "[OK]" in text:
                tag = "ok"
            elif "WARNING" in text or "WARN" in text:
                tag = "warn"
            elif "ERROR" in text or "failed" in text.lower():
                tag = "err"
            elif text.startswith("  >"):
                tag = "muted"
        if tag:
            self.log_text.insert(END, text + "\n", tag)
        else:
            self.log_text.insert(END, text + "\n")
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", END)
        self.log_text.configure(state="disabled")

    def _set_building(self, building: bool, silent: bool = False) -> None:
        self.building = building
        state = "disabled" if building else "normal"
        try:
            self.build_btn.configure(state=state)
        except Exception:
            pass
        if not silent:
            if building:
                self._update_status("Building… please wait.", Palette.WARNING)
            else:
                self._update_status("Ready.", Palette.SUCCESS)

    def _on_done(self, target: str) -> None:
        self._set_building(False)
        self._log("")
        self._log("=" * 52, "muted")
        self._log("  DONE!", "ok")
        self._log("=" * 52, "muted")
        self._log(f"  {target}", "ok")
        self._update_status("Finished.", Palette.SUCCESS)
        dark_info(
            self.root, "Finished",
            f"Build completed successfully!\n\nThe EXE is located here:\n{target}",
        )

    def _on_error(self, message: str) -> None:
        self._set_building(False)
        self._log("")
        self._log(f"ERROR: {message}", "err")
        self._update_status("Error.", Palette.ERROR)
        dark_error(self.root, "Error", message)


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
def main() -> int:
    if not is_admin():
        relaunch_as_admin()
        return 0

    root = Tk()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    BuilderGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
