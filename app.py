#!/usr/bin/env python3
"""Windows UI for Camera Shutter Count (USB shutter readout)."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk

from shutter_count import camera_usb_paths, camera_wpd_paths, read_shutter_result

BG = "#16181d"
CARD = "#22252c"
FG = "#f4f4f5"
MUTED = "#a1a1aa"
ACCENT = "#f97316"
OK = "#4ade80"
ERR = "#f87171"
FONT = "Segoe UI"
DONATE_URL = "https://github.com/sponsors/Lowlogik"
REPO_URL = "https://github.com/Lowlogik/camera-shutter-count"
HOVER = "#fb923c"
DISABLED_BTN = "#9a642e"
HELP_NO_CAMERA = (
    "Close other camera software and Photos first. Use a data cable and a charged battery. "
    "Some bodies do not expose the count over USB."
)


def _resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


class RoundedButton(tk.Canvas):
    def __init__(self, master: tk.Widget, text: str, command, *, height: int = 56, radius: int = 16) -> None:
        super().__init__(
            master,
            height=height,
            highlightthickness=0,
            bd=0,
            bg=BG,
            cursor="hand2",
        )
        self._text = text
        self._command = command
        self._state = "normal"
        self._hovered = False
        self._radius = radius
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if isinstance(cnf, str) and not kwargs:
            return super().configure(cnf)
        opts = dict(cnf or {}, **kwargs)
        text = opts.pop("text", None)
        state = opts.pop("state", None)
        result = super().configure(**opts) if opts else None
        if text is not None:
            self._text = text
        if state is not None:
            self._state = state
            super().configure(cursor="arrow" if state == "disabled" else "hand2")
        if text is not None or state is not None:
            self._redraw()
        return result

    config = configure

    def _fill(self) -> str:
        if self._state == "disabled":
            return DISABLED_BTN
        if self._hovered:
            return HOVER
        return ACCENT

    def _redraw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 2)
        height = max(self.winfo_height(), 2)
        r = min(self._radius, width // 2, height // 2)
        x1, y1, x2, y2 = 1, 1, width - 2, height - 2
        points = (
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        )
        self.create_polygon(points, smooth=True, splinesteps=12, fill=self._fill(), outline="")
        self.create_text(
            width / 2,
            height / 2,
            text=self._text,
            fill="#111111",
            font=(FONT, 15, "bold"),
        )

    def _on_enter(self, _event) -> None:
        self._hovered = True
        self._redraw()

    def _on_leave(self, _event) -> None:
        self._hovered = False
        self._redraw()

    def _on_click(self, _event) -> None:
        if self._state == "disabled":
            return
        self._command()


class ShutterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Camera Shutter Count")
        self.configure(bg=BG)
        self.geometry("480x600")
        self.minsize(480, 600)
        self.resizable(False, False)
        self._busy = False
        icon = _resource_path("icon.ico")
        if icon.exists():
            try:
                self.iconbitmap(icon)
            except tk.TclError:
                pass
        self._build()
        self.after(200, self._refresh_presence)
        self.after(400, self._read_if_present)

    def _build(self) -> None:
        tk.Label(self, text="Camera Shutter Count", bg=BG, fg=FG, font=(FONT, 16, "bold")).pack(
            anchor="w", padx=24, pady=(22, 2)
        )
        tk.Label(
            self,
            text="USB readout. Tested on Rebel T7.\nWant another camera? Open an issue.",
            bg=BG,
            fg=MUTED,
            font=(FONT, 10),
            justify="left",
            wraplength=420,
        ).pack(anchor="w", fill="x", padx=24, pady=(0, 12))

        self.presence = tk.Label(self, text="Looking for camera…", bg=BG, fg=MUTED, font=(FONT, 10))
        self.presence.pack(anchor="w", padx=24, pady=4)
        self.help = tk.Label(
            self,
            text=HELP_NO_CAMERA,
            bg=BG,
            fg=ERR,
            font=(FONT, 9),
            wraplength=400,
            justify="left",
        )
        self.help.pack(anchor="w", fill="x", padx=24, pady=(0, 8))

        card = tk.Frame(self, bg=CARD)
        card.pack(fill="x", padx=24, pady=12)

        tk.Label(card, text="SHUTTER COUNT", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(
            anchor="w", padx=18, pady=(16, 0)
        )
        self.count_var = tk.StringVar(value="—")
        tk.Label(card, textvariable=self.count_var, bg=CARD, fg=FG, font=(FONT, 36, "bold")).pack(
            anchor="w", padx=18
        )
        self.life_var = tk.StringVar(value="Connect a camera over USB")
        tk.Label(
            card,
            textvariable=self.life_var,
            bg=CARD,
            fg=MUTED,
            font=(FONT, 10),
            wraplength=380,
            justify="left",
        ).pack(anchor="w", fill="x", padx=18, pady=(0, 8))

        self.meta = tk.Label(
            card, text="", bg=CARD, fg=FG, font=(FONT, 10), justify="left", anchor="w", wraplength=380
        )
        self.meta.pack(fill="x", padx=18, pady=(0, 16))

        self.read_btn = RoundedButton(self, text="Read shutter count", command=self._on_read)
        self.read_btn.pack(fill="x", padx=24, pady=(12, 10))

        self.status = tk.Message(
            self,
            text="",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            width=400,
            justify="center",
            aspect=500,
        )
        self.status.pack(fill="x", padx=32, pady=(4, 8))

        links = tk.Frame(self, bg=BG)
        links.pack(pady=(8, 16))
        self._link(links, "Sponsor on GitHub", DONATE_URL).pack(side="left")
        tk.Label(links, text="  ·  ", bg=BG, fg=MUTED).pack(side="left")
        self._link(links, "Source", REPO_URL).pack(side="left")
        self.bind("<Configure>", self._on_resize)

    def _link(self, parent: tk.Widget, text: str, url: str) -> tk.Label:
        label = tk.Label(parent, text=text, bg=BG, fg=ACCENT, font=(FONT, 10, "underline"), cursor="hand2")
        label.bind("<Button-1>", lambda _e, target=url: webbrowser.open(target))
        return label

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        width = max(240, event.width - 80)
        self.status.configure(width=width)
        self.help.configure(wraplength=width)

    def _ui_error(self, message: str) -> tuple[str, str]:
        lower = message.lower()
        if any(token in lower for token in ("no camera", "checklist", "no ptp", "not see a camera")):
            return (
                "No camera on USB",
                "Turn the camera on, use a data cable, and close Photos.",
            )
        if "did not report a shutter count" in lower:
            return (
                "This body did not report a shutter count",
                "Some cameras do not expose the count over USB.",
            )
        if "did not answer as a ptp" in lower:
            return (
                "USB camera found, readout failed",
                "Unplug, wait a few seconds, plug back in, then retry.",
            )
        first = message.strip().split("\n", 1)[0].strip()
        if len(first) > 80:
            first = first[:77] + "..."
        return (first, "Check the cable and try again.")

    def _set_status(self, text: str, color: str = MUTED) -> None:
        self.status.configure(text=text, fg=color)

    def _camera_present(self) -> bool:
        try:
            return bool(camera_usb_paths() or camera_wpd_paths())
        except Exception:
            return False

    def _refresh_presence(self) -> None:
        if self._camera_present():
            self.presence.configure(text="Camera detected on USB", fg=OK)
            self.help.pack_forget()
        else:
            self.presence.configure(text="No camera on USB", fg=ERR)
            if not self.help.winfo_ismapped():
                self.help.pack(anchor="w", fill="x", padx=24, pady=(0, 8), after=self.presence)
            self.help.configure(text=HELP_NO_CAMERA, fg=ERR)
        self.after(1500, self._refresh_presence)

    def _read_if_present(self) -> None:
        if self._camera_present() and not self._busy:
            self._on_read()

    def _on_read(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.read_btn.configure(state="disabled", text="Reading…")
        self._set_status("Talking to the camera…")
        threading.Thread(target=self._read_worker, daemon=True).start()

    def _read_worker(self) -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
            try:
                result = read_shutter_result()
            finally:
                comtypes.CoUninitialize()
        except Exception as exc:
            self.after(0, lambda msg=str(exc): self._show_error(msg))
            return
        self.after(0, lambda data=result: self._show_result(data))

    def _show_result(self, result: dict) -> None:
        self._busy = False
        self.read_btn.configure(state="normal", text="Read shutter count")
        self.count_var.set(f"{result['count']:,}")
        rated = result.get("rated")
        used = result.get("used_pct")
        if rated and used is not None:
            self.life_var.set(f"{used:.1f}% of {rated:,} rated actuations")
        else:
            self.life_var.set("Rated shutter life unknown for this model")
        lines = [result["model"]]
        if result.get("serial"):
            lines.append(f"Serial  {result['serial']}")
        if result.get("firmware"):
            lines.append(f"Firmware  {result['firmware']}")
        self.meta.configure(text="\n".join(lines))
        self._set_status("Read OK.", OK)

    def _show_error(self, message: str) -> None:
        self._busy = False
        self.read_btn.configure(state="normal", text="Read shutter count")
        card, footer = self._ui_error(message)
        self.count_var.set("—")
        self.life_var.set(card)
        self.meta.configure(text="")
        if card == "No camera on USB":
            self._set_status("", MUTED)
        else:
            self._set_status(footer, ERR)


def main() -> None:
    app = ShutterApp()
    style = ttk.Style(app)
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()
