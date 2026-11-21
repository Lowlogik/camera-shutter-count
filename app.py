#!/usr/bin/env python3
"""Windows UI for Camera Shutter Count (Canon EOS USB readout)."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
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
DONATE_URL = "https://github.com/sponsors/patricktheroux-ops"
REPO_URL = "https://github.com/patricktheroux-ops/camera-shutter-count"


class ShutterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Camera Shutter Count")
        self.configure(bg=BG)
        self.geometry("460x560")
        self.minsize(420, 520)
        self.resizable(False, False)
        self._busy = False
        self._build()
        self.after(200, self._refresh_presence)
        self.after(400, self._read_if_present)

    def _build(self) -> None:
        tk.Label(self, text="Camera Shutter Count", bg=BG, fg=FG, font=(FONT, 16, "bold")).pack(
            anchor="w", padx=24, pady=(22, 2)
        )
        tk.Label(
            self,
            text="USB readout for Canon EOS. Tested on Rebel T7 / EOS 2000D.",
            bg=BG,
            fg=MUTED,
            font=(FONT, 10),
        ).pack(anchor="w", padx=24, pady=(0, 12))

        self.presence = tk.Label(self, text="Looking for camera…", bg=BG, fg=MUTED, font=(FONT, 10))
        self.presence.pack(anchor="w", padx=24, pady=4)

        card = tk.Frame(self, bg=CARD)
        card.pack(fill="x", padx=24, pady=12)

        tk.Label(card, text="SHUTTER COUNT", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(
            anchor="w", padx=18, pady=(16, 0)
        )
        self.count_var = tk.StringVar(value="—")
        tk.Label(card, textvariable=self.count_var, bg=CARD, fg=FG, font=(FONT, 36, "bold")).pack(
            anchor="w", padx=18
        )
        self.life_var = tk.StringVar(value="Connect a Canon EOS body over USB")
        tk.Label(card, textvariable=self.life_var, bg=CARD, fg=MUTED, font=(FONT, 10)).pack(
            anchor="w", padx=18, pady=(0, 8)
        )

        self.meta = tk.Label(card, text="", bg=CARD, fg=FG, font=(FONT, 10), justify="left", anchor="w")
        self.meta.pack(fill="x", padx=18, pady=(0, 16))

        self.read_btn = tk.Button(
            self,
            text="Read shutter count",
            command=self._on_read,
            bg=ACCENT,
            fg="#111",
            activebackground="#fb923c",
            activeforeground="#111",
            relief="flat",
            font=(FONT, 11, "bold"),
            cursor="hand2",
            padx=16,
            pady=10,
        )
        self.read_btn.pack(fill="x", padx=24, pady=(8, 8))

        self.status = tk.Label(
            self, text="", bg=BG, fg=MUTED, font=(FONT, 9), wraplength=400, justify="left", anchor="w"
        )
        self.status.pack(fill="x", padx=24, pady=(4, 8))

        links = tk.Frame(self, bg=BG)
        links.pack(fill="x", padx=24, pady=(8, 4))
        self._link(links, "Sponsor on GitHub", DONATE_URL).pack(side="left")
        tk.Label(links, text="  ·  ", bg=BG, fg=MUTED).pack(side="left")
        self._link(links, "Source", REPO_URL).pack(side="left")

        hint = (
            "Close EOS Utility / Photos first. Use a data cable and a charged battery. "
            "DIGIC 6+ bodies (80D, 5D IV, most R series) usually do not expose the count over USB."
        )
        tk.Label(self, text=hint, bg=BG, fg=MUTED, font=(FONT, 9), wraplength=400, justify="left").pack(
            anchor="w", padx=24, pady=(8, 16)
        )

    def _link(self, parent: tk.Widget, text: str, url: str) -> tk.Label:
        label = tk.Label(parent, text=text, bg=BG, fg=ACCENT, font=(FONT, 10, "underline"), cursor="hand2")
        label.bind("<Button-1>", lambda _e, target=url: webbrowser.open(target))
        return label

    def _set_status(self, text: str, color: str = MUTED) -> None:
        self.status.configure(text=text, fg=color)

    def _camera_present(self) -> bool:
        try:
            return bool(camera_usb_paths() or camera_wpd_paths())
        except Exception:
            return False

    def _refresh_presence(self) -> None:
        if self._camera_present():
            self.presence.configure(text="Canon camera detected on USB", fg=OK)
        else:
            self.presence.configure(text="No Canon camera on USB", fg=ERR)
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
        self._set_status("Read OK. IMG_ file numbers are not the shutter count.", OK)

    def _show_error(self, message: str) -> None:
        self._busy = False
        self.read_btn.configure(state="normal", text="Read shutter count")
        self.count_var.set("—")
        self._set_status(message, ERR)


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
