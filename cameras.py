"""Shutter ratings and USB readout notes.

Rated lives are published shutter durability figures, not a hard stop.
USB readout of property 0xD1AC works on many older DSLRs.
Newer bodies often do not expose that property over USB.
"""

from __future__ import annotations

# Longer / more specific names first.
_RATED_LIFE: tuple[tuple[str, int], ...] = (
    ("1D X MARK III", 500_000),
    ("1DX MARK III", 500_000),
    ("1D X MARK II", 400_000),
    ("1DX MARK II", 400_000),
    ("1D MARK IV", 300_000),
    ("1D MARK III", 300_000),
    ("1DS MARK III", 300_000),
    ("1D X", 400_000),
    ("1DX", 400_000),
    ("R5 MARK II", 500_000),
    ("R6 MARK II", 400_000),
    ("EOS R5", 500_000),
    ("EOS R6", 300_000),
    ("EOS R3", 500_000),
    ("EOS R8", 100_000),
    ("EOS R7", 200_000),
    ("EOS R10", 100_000),
    ("EOS R50", 100_000),
    ("EOS RP", 100_000),
    ("5D MARK IV", 150_000),
    ("5D MARK III", 150_000),
    ("5D MARK II", 150_000),
    ("5DS", 150_000),
    ("6D MARK II", 100_000),
    ("EOS 6D", 100_000),
    ("7D MARK II", 200_000),
    ("EOS 7D", 150_000),
    ("EOS 90D", 120_000),
    ("EOS 80D", 100_000),
    ("EOS 70D", 100_000),
    ("EOS 60D", 100_000),
    ("EOS 50D", 100_000),
    ("EOS 40D", 100_000),
    ("REBEL T8I", 100_000),
    ("REBEL T7I", 100_000),
    ("REBEL T7", 100_000),
    ("REBEL T6S", 100_000),
    ("REBEL T6I", 100_000),
    ("REBEL T6", 100_000),
    ("REBEL T5I", 100_000),
    ("REBEL T5", 100_000),
    ("REBEL T4I", 100_000),
    ("REBEL T3I", 100_000),
    ("REBEL T3", 100_000),
    ("REBEL SL3", 100_000),
    ("REBEL SL2", 100_000),
    ("REBEL SL1", 100_000),
    ("KISS X90", 100_000),
    ("KISS X80", 100_000),
    ("2000D", 100_000),
    ("1500D", 100_000),
    ("4000D", 100_000),
    ("3000D", 100_000),
    ("850D", 100_000),
    ("800D", 100_000),
    ("760D", 100_000),
    ("750D", 100_000),
    ("700D", 100_000),
    ("650D", 100_000),
    ("600D", 100_000),
    ("550D", 100_000),
    ("250D", 100_000),
    ("200D", 100_000),
    ("100D", 100_000),
    ("EOS 77D", 100_000),
)

USB_LIKELY = (
    "Many older DSLRs typically report the count over USB, including Rebel T7. "
    "Open a GitHub issue if you want another camera added."
)

USB_UNLIKELY = (
    "This body did not report a shutter count over USB. "
    "A service centre can still read some cameras that block this. "
    "Open a GitHub issue if you want another model added."
)


def _norm(model: str) -> str:
    return " ".join(model.upper().replace("-", " ").split())


def rated_life_for(model: str) -> int | None:
    text = _norm(model)
    if not text:
        return None
    for needle, life in _RATED_LIFE:
        if needle in text:
            return life
    return None
