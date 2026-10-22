"""
tests/check_drives.py
=====================
Quick CLI sanity-check for engine.drives.

Run from the project root:
    python tests/check_drives.py

Compare the output with File Explorer > This PC.
No Qt — runs with plain Python.
"""

import sys
import os
import io

# Force UTF-8 output so box chars survive any console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.drives import list_drives, format_bytes


def _bar(pct: float, width: int = 20) -> str:
    filled = int(round(pct / 100 * width))
    return "#" * filled + "-" * (width - filled)


def main() -> None:
    print("OmniStore — Drive Check")
    print("=" * 72)

    drives = list_drives()

    if not drives:
        print("  (no drives found)")
        return

    row_fmt = (
        "{mount:<6}  {label:<20}  {fs:<8}  {type_:<10}  "
        "{used:>8} / {total:>8}  [{bar}] {pct:>5.1f}%  {status}"
    )

    header = row_fmt.format(
        mount="Drive",
        label="Label",
        fs="FS",
        type_="Type",
        used="Used",
        total="Total",
        bar=" " * 20,
        pct=0.0,
        status="",
    )
    print(header.replace("0.0%", "  Pct"))
    print("-" * 72)

    for d in drives:
        if d.accessible:
            status = "✓"
            bar    = _bar(d.percent_used)
            used   = format_bytes(d.used_bytes)
            total  = format_bytes(d.total_bytes)
            pct    = d.percent_used
        else:
            status = f"✗ {d.error}"
            bar    = "░" * 20
            used   = "—"
            total  = "—"
            pct    = 0.0

        print(row_fmt.format(
            mount  = d.mountpoint[:5],
            label  = (d.label or "(no label)")[:20],
            fs     = d.filesystem[:8],
            type_  = d.drive_type[:10],
            used   = used,
            total  = total,
            bar    = bar,
            pct    = pct,
            status = status,
        ))

    print()

    # Summary totals (accessible drives only)
    accessible = [d for d in drives if d.accessible]
    if accessible:
        total_cap  = sum(d.total_bytes for d in accessible)
        total_used = sum(d.used_bytes  for d in accessible)
        total_free = sum(d.free_bytes  for d in accessible)
        print(f"  Drives connected : {len(drives)}")
        print(f"  Accessible       : {len(accessible)}")
        print(f"  Total capacity   : {format_bytes(total_cap)}")
        print(f"  Total used       : {format_bytes(total_used)}")
        print(f"  Total free       : {format_bytes(total_free)}")


if __name__ == "__main__":
    main()
