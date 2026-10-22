"""
tests/make_demo_data.py
=======================
Creates a safe, deterministic test folder for OmniStore duplicate detection
and cleanup testing. Contents are reproducible using a fixed random seed.
Never modifies personal files.

Usage:
    python tests/make_demo_data.py [target_folder] [--force]

Default location:
    C:\\Users\\<user>\\OmniStore_Demo
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import random
import shutil
import sys
import time

# Force UTF-8 output for Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def get_default_demo_dir() -> Path:
    return Path.home() / "OmniStore_Demo"


def _write_file_chunks(path: Path, chunk_data: bytes, repeat_count: int, remainder: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        for _ in range(repeat_count):
            f.write(chunk_data)
        if remainder:
            f.write(remainder)


def create_demo_data(target_dir: Path, force: bool = False) -> None:
    print("=" * 72)
    print("OmniStore — Safe Demo Data Generator")
    print("=" * 72)
    print(f"Target location: {target_dir}")

    if target_dir.exists():
        entries = list(target_dir.iterdir())
        if entries:
            if not force:
                print("\n[REFUSED] Target folder exists and is non-empty!")
                print(f"Directory: {target_dir}")
                print(f"Contains {len(entries)} items.")
                print("To overwrite, pass the --force flag:")
                print(f"    python tests/make_demo_data.py \"{target_dir}\" --force")
                sys.exit(1)
            else:
                print(f"[FORCE] Removing existing contents of {target_dir}...")
                for item in entries:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

    target_dir.mkdir(parents=True, exist_ok=True)

    # Seeded random generator for reproducible byte generation
    rng = random.Random(42)

    print("\nGenerating reproducible test files...")

    # Helper to generate reproducible blocks
    def gen_bytes(size: int) -> bytes:
        return rng.randbytes(size)

    # -----------------------------------------------------------------------
    # 1. Duplicate Group A: 3 identical 20 MB files in different subfolders
    # -----------------------------------------------------------------------
    size_20mb = 20 * 1024 * 1024  # 20,971,520 bytes
    print("  Generating Group A (3 x 20 MB identical files)...")
    block_1mb = gen_bytes(1024 * 1024)

    group_a_paths = [
        target_dir / "Videos" / "holiday_clip.mp4",
        target_dir / "Backup" / "holiday_clip_copy.mp4",
        target_dir / "Desktop" / "clip (1).mp4",
    ]
    for p in group_a_paths:
        _write_file_chunks(p, block_1mb, 20)

    # -----------------------------------------------------------------------
    # 2. Duplicate Group B: 2 identical 5 MB files
    # -----------------------------------------------------------------------
    size_5mb = 5 * 1024 * 1024  # 5,242,880 bytes
    print("  Generating Group B (2 x 5 MB identical files)...")
    block_5mb = gen_bytes(1024 * 1024)

    group_b_paths = [
        target_dir / "Documents" / "report_final.pdf",
        target_dir / "Documents" / "report_final (copy).pdf",
    ]
    for p in group_b_paths:
        _write_file_chunks(p, block_5mb, 5)

    # -----------------------------------------------------------------------
    # 3. Duplicate Group C: 2 identical 50 KB small files
    # -----------------------------------------------------------------------
    size_50kb = 50 * 1024  # 51,200 bytes
    print("  Generating Group C (2 x 50 KB identical files)...")
    content_50kb = gen_bytes(size_50kb)

    group_c_paths = [
        target_dir / "Work" / "notes.txt",
        target_dir / "Archive" / "notes_backup.txt",
    ]
    for p in group_c_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content_50kb)

    # -----------------------------------------------------------------------
    # 4. Negative Test: 2 files of EXACTLY same size (8 MB) with DIFFERENT content
    # -----------------------------------------------------------------------
    print("  Generating Negative Test (2 x 8 MB files, same size, different content)...")
    size_8mb = 8 * 1024 * 1024
    raw_a_block = gen_bytes(1024 * 1024)
    raw_b_block = gen_bytes(1024 * 1024)

    _write_file_chunks(target_dir / "Photos" / "pic_a.raw", raw_a_block, 8)
    _write_file_chunks(target_dir / "Photos" / "pic_b.raw", raw_b_block, 8)

    # -----------------------------------------------------------------------
    # 5. Negative Test: 2 empty (0-byte) files (must NEVER be reported as dupes)
    # -----------------------------------------------------------------------
    print("  Generating Negative Test (2 x 0-byte empty files)...")
    empty_paths = [
        target_dir / "Misc" / "empty1.log",
        target_dir / "Misc" / "empty2.log",
    ]
    for p in empty_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")

    # -----------------------------------------------------------------------
    # 6. Unique large files with old timestamps (~400 days ago)
    # -----------------------------------------------------------------------
    print("  Generating Unique Old Large Files (~400 days old)...")
    movie_path = target_dir / "Media" / "old_movie.mkv"
    iso_path = target_dir / "Downloads" / "setup_tool.iso"

    movie_block = gen_bytes(1024 * 1024)
    iso_block = gen_bytes(1024 * 1024)

    _write_file_chunks(movie_path, movie_block, 150)  # 150 MB
    _write_file_chunks(iso_path, iso_block, 60)       # 60 MB

    t_400_days_ago = time.time() - (400 * 86400)
    os.utime(movie_path, (t_400_days_ago, t_400_days_ago))
    os.utime(iso_path, (t_400_days_ago, t_400_days_ago))

    # -----------------------------------------------------------------------
    # 7. Unique small files (documents, images, audio, text)
    # -----------------------------------------------------------------------
    print("  Generating miscellaneous unique small files...")
    unique_files = [
        (target_dir / "Documents" / "budget.xlsx", 120 * 1024),
        (target_dir / "Pictures" / "avatar.png", 250 * 1024),
        (target_dir / "Work" / "todo.txt", 4 * 1024),
        (target_dir / "Music" / "song.mp3", 3 * 1024 * 1024),
    ]
    for p, sz in unique_files:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(gen_bytes(sz))

    # -----------------------------------------------------------------------
    # Summary of Expected Results
    # -----------------------------------------------------------------------
    expected_reclaimable_a = 2 * size_20mb          # 41,943,040 bytes (40 MB)
    expected_reclaimable_b = 1 * size_5mb           # 5,242,880 bytes (5 MB)
    expected_reclaimable_c = 1 * size_50kb          # 51,200 bytes (50 KB)
    total_reclaimable = expected_reclaimable_a + expected_reclaimable_b + expected_reclaimable_c  # 47,237,120 bytes

    print("\n" + "=" * 72)
    print("DEMO DATA CREATED SUCCESSFULLY")
    print("=" * 72)
    print(f"Root Folder : {target_dir}")
    print("\nExpected Duplicate Groups:")
    print(f"  Group A: 3 copies x 20.0 MB -> 2 redundant copies (saves 40.0 MB)")
    print(f"           - {group_a_paths[0].relative_to(target_dir)}")
    print(f"           - {group_a_paths[1].relative_to(target_dir)}")
    print(f"           - {group_a_paths[2].relative_to(target_dir)}")
    print(f"  Group B: 2 copies x 5.0 MB  -> 1 redundant copy (saves 5.0 MB)")
    print(f"           - {group_b_paths[0].relative_to(target_dir)}")
    print(f"           - {group_b_paths[1].relative_to(target_dir)}")
    print(f"  Group C: 2 copies x 50.0 KB -> 1 redundant copy (saves 50.0 KB)")
    print(f"           - {group_c_paths[0].relative_to(target_dir)}")
    print(f"           - {group_c_paths[1].relative_to(target_dir)}")
    print("\nNegative Tests (must NOT be detected as duplicates):")
    print("  - Photos/pic_a.raw & Photos/pic_b.raw (8 MB each, different content)")
    print("  - Misc/empty1.log & Misc/empty2.log (0 bytes each)")
    print("\nExpected Reclaimable Space:")
    print(f"  Total groups : 3")
    print(f"  Total redundant files : 4")
    print(f"  Total reclaimable     : {total_reclaimable:,} bytes (45.05 MB)")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create safe deterministic demo data for OmniStore.")
    parser.add_argument("folder", nargs="?", default=str(get_default_demo_dir()), help="Target directory")
    parser.add_argument("--force", action="store_true", help="Overwrite if folder exists and is non-empty")
    args = parser.parse_args()

    target = Path(args.folder)
    create_demo_data(target, force=args.force)


if __name__ == "__main__":
    main()
