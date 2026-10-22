"""
engine/drives.py
================
Drive enumeration for Windows using psutil + ctypes.

No PySide6 / Qt imports — this module is safe to run headless.

Public API
----------
DriveInfo   – dataclass describing one drive
list_drives()  -> list[DriveInfo]   – enumerate all accessible drives
format_bytes(n) -> str              – human-readable size (e.g. "245.3 GB")
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass, field
from typing import Optional

import psutil

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GetDriveTypeW return values (winbase.h)
# ---------------------------------------------------------------------------
_DRIVE_UNKNOWN   = 0
_DRIVE_NO_ROOT   = 1
_DRIVE_REMOVABLE = 2
_DRIVE_FIXED     = 3
_DRIVE_REMOTE    = 4
_DRIVE_CDROM     = 5
_DRIVE_RAMDISK   = 6

_TYPE_MAP = {
    _DRIVE_FIXED:     "Internal",
    _DRIVE_REMOVABLE: "Removable",
    _DRIVE_REMOTE:    "Network",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_bytes(n: int) -> str:
    """
    Convert *n* bytes to a human-readable string using 1024-based units.

    Examples
    --------
    format_bytes(1_073_741_824) -> "1.0 GB"
    format_bytes(1_500_000_000) -> "1.4 GB"
    format_bytes(500_000_000_000) -> "465.7 GB"
    """
    if n < 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit in ("B", "KB"):
                return f"{n:.0f} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"  # unreachable in practice, but keeps mypy happy


def _get_volume_label(root: str) -> str:
    """
    Return the Windows volume label for *root* (e.g. "C:\\").
    Returns an empty string on any failure.
    """
    try:
        buf = ctypes.create_unicode_buffer(261)
        ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            root,
            buf,
            ctypes.sizeof(buf),
            None, None, None, None, 0,
        )
        return buf.value
    except Exception as exc:
        log.debug("GetVolumeInformationW failed for %r: %s", root, exc)
        return ""


def _get_drive_type(root: str) -> str:
    """
    Return a human-readable drive type string for *root*.
    Falls back to "Other" on any failure.
    """
    try:
        code = ctypes.windll.kernel32.GetDriveTypeW(root)  # type: ignore[attr-defined]
        return _TYPE_MAP.get(code, "Other")
    except Exception as exc:
        log.debug("GetDriveTypeW failed for %r: %s", root, exc)
        return "Other"


# ---------------------------------------------------------------------------
# DriveInfo dataclass
# ---------------------------------------------------------------------------

@dataclass
class DriveInfo:
    """All information about a single drive / mount point."""

    mountpoint:   str            # e.g. "C:\\"
    label:        str            # volume name; may be empty
    filesystem:   str            # e.g. "NTFS", "FAT32", "exFAT"
    drive_type:   str            # "Internal" | "Removable" | "Network" | "Other"
    total_bytes:  int            # 0 when inaccessible
    used_bytes:   int
    free_bytes:   int
    percent_used: float          # 0.0–100.0
    accessible:   bool
    error:        Optional[str]  # plain-English reason when not accessible


# ---------------------------------------------------------------------------
# list_drives
# ---------------------------------------------------------------------------

def list_drives() -> list[DriveInfo]:
    """
    Enumerate all drives Windows reports as mounted.

    - Uses psutil.disk_partitions(all=False) so virtual/pseudo filesystems
      are excluded.
    - Reads capacity via psutil.disk_usage (real values, never hardcoded).
    - Reads volume label and drive type via ctypes kernel32 calls.
    - Silently skips CD/DVD (DRIVE_CDROM) and empty removable readers.
    - Inaccessible drives are returned with accessible=False and an
      English-language error; this function never raises.

    Returns a list sorted by mountpoint.
    """
    results: list[DriveInfo] = []

    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception as exc:
        log.error("psutil.disk_partitions failed: %s", exc)
        return results

    for part in partitions:
        root = part.mountpoint
        if not root:
            continue

        # ── Skip CD/DVD drives silently ────────────────────────────
        try:
            raw_type = ctypes.windll.kernel32.GetDriveTypeW(root)  # type: ignore[attr-defined]
        except Exception:
            raw_type = _DRIVE_UNKNOWN

        if raw_type == _DRIVE_CDROM:
            log.debug("Skipping CD/DVD: %s", root)
            continue

        # ── Volume label and type ──────────────────────────────────
        label      = _get_volume_label(root)
        drive_type = _get_drive_type(root)

        # ── Capacity via psutil ────────────────────────────────────
        try:
            usage = psutil.disk_usage(root)

            # Skip empty removable slots (card readers with no media)
            if usage.total == 0:
                log.debug("Skipping zero-size drive: %s", root)
                continue

            results.append(DriveInfo(
                mountpoint   = root,
                label        = label,
                filesystem   = part.fstype or "Unknown",
                drive_type   = drive_type,
                total_bytes  = usage.total,
                used_bytes   = usage.used,
                free_bytes   = usage.free,
                percent_used = usage.percent,
                accessible   = True,
                error        = None,
            ))

        except PermissionError:
            results.append(DriveInfo(
                mountpoint   = root,
                label        = label,
                filesystem   = part.fstype or "Unknown",
                drive_type   = drive_type,
                total_bytes  = 0,
                used_bytes   = 0,
                free_bytes   = 0,
                percent_used = 0.0,
                accessible   = False,
                error        = "Access denied — run OmniStore as administrator to see this drive.",
            ))

        except OSError as exc:
            # Covers disconnected network drives, ejected removable media, etc.
            results.append(DriveInfo(
                mountpoint   = root,
                label        = label,
                filesystem   = part.fstype or "Unknown",
                drive_type   = drive_type,
                total_bytes  = 0,
                used_bytes   = 0,
                free_bytes   = 0,
                percent_used = 0.0,
                accessible   = False,
                error        = f"Drive not available ({exc.strerror or 'OS error'}).",
            ))

        except Exception as exc:  # noqa: BLE001  last-resort catch
            log.warning("Unexpected error reading %r: %s", root, exc)
            results.append(DriveInfo(
                mountpoint   = root,
                label        = label,
                filesystem   = part.fstype or "Unknown",
                drive_type   = drive_type,
                total_bytes  = 0,
                used_bytes   = 0,
                free_bytes   = 0,
                percent_used = 0.0,
                accessible   = False,
                error        = f"Unexpected error: {exc}",
            ))

    results.sort(key=lambda d: d.mountpoint)
    return results
