#!/usr/bin/env python3
"""
Convert per-island CSV snapshots (mm_intermediate/mm_*) into tar.gz archives that
mimic the original EMA structure: a tmp/ folder containing selected CSV files.

Usage (single zip):
    python borg_archive_processor.py \
        --archive /path/mm_intermediate_5.zip \
        --base-name MOMA_200000_ref2 \
        --step 10000 \
        --island-offset 0

Usage (second zip, continuing numbering from island 5):
    python borg_archive_processor.py \
        --archive /path/mm_intermediate_4.zip \
        --base-name MOMA_200000_ref2 \
        --step 10000 \
        --island-offset 5

Output: MOMA_200000_ref2_0.tar.gz ... MOMA_200000_ref2_8.tar.gz
"""

import argparse
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Package mm_* snapshots into tmp/ tarballs."
    )
    parser.add_argument(
        "--archive",
        required=True,
        help="Path to mm_intermediate.zip or an extracted mm_intermediate directory.",
    )
    parser.add_argument(
        "--base-name",
        required=True,
        help="Base name for outputs (e.g., MOMA_200000_ref2). "
        "Each island tar will be {base-name}_{island}.tar.gz",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=0,
        help="Only keep CSV files whose numeric name is a multiple of this step. "
        "Use 0 (default) to keep every CSV in the island folder.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for the output tar.gz files. Default: same as the archive location.",
    )
    parser.add_argument(
        "--island-offset",
        type=int,
        default=0,
        help="Integer offset added to each island index. "
        "Use 0 for the first zip (5 islands → 0..4), "
        "then 5 for the second zip (4 islands → 5..8).",
    )
    return parser.parse_args()


def extract_if_needed(archive_path: Path) -> Path:
    """If archive_path is a zip file, extract it to a temp dir and return the mm_intermediate folder.
    Otherwise, assume it already points to the mm_intermediate directory."""
    if archive_path.is_file() and archive_path.suffix == ".zip":
        temp_dir = Path(tempfile.mkdtemp(prefix="mm_intermediate_"))
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(temp_dir)
        subdirs = [p for p in temp_dir.glob("*") if p.is_dir()]
        if len(subdirs) == 1:
            extracted_root = subdirs[0]
        else:
            extracted_root = temp_dir / "mm_intermediate"
        return extracted_root
    else:
        return archive_path


def integer_basename(path: Path):
    try:
        return int(path.stem)
    except ValueError:
        return None


def select_csvs(csv_files, step):
    """Always include the first CSV, then apply the step filter (if step > 0)."""
    if not csv_files:
        return []

    selected = [csv_files[0]]

    if step <= 0:
        selected.extend(csv_files[1:])
        return selected

    for csv_file in csv_files[1:]:
        nfe = integer_basename(csv_file)
        if nfe is None:
            continue
        if nfe % step == 0:
            selected.append(csv_file)

    # Deduplicate while preserving order
    seen = set()
    unique_selected = []
    for csv_file in selected:
        if csv_file not in seen:
            unique_selected.append(csv_file)
            seen.add(csv_file)

    return unique_selected


def package_mm_island(island_dir, output_dir, base_name, island_idx, step):
    csv_files = sorted(
        [f for f in island_dir.glob("*.csv") if integer_basename(f) is not None],
        key=lambda f: integer_basename(f),
    )
    if not csv_files:
        print(f"[WARN] No numeric CSV files found in {island_dir}")
        return None

    chosen = select_csvs(csv_files, step)
    if not chosen:
        print(f"[WARN] Step filter removed all CSVs in {island_dir}; nothing to pack.")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{base_name}_{island_idx}.tar.gz"
    tar_path = output_dir / archive_name

    with tempfile.TemporaryDirectory(prefix=f"tmp_mm_{island_idx}_") as tmp_root:
        tmp_dir = Path(tmp_root) / "tmp"
        tmp_dir.mkdir()
        for csv_file in chosen:
            shutil.copy2(csv_file, tmp_dir / csv_file.name)
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(tmp_dir, arcname="tmp")

    print(f"[OK] {tar_path}  (source island: {island_dir.name})")
    return tar_path


def main():
    args = parse_args()
    archive_path = Path(args.archive)
    root = extract_if_needed(archive_path)

    if not root.exists():
        raise FileNotFoundError(
            f"Folder {root} not found (archive may have no mm_intermediate folder)."
        )

    island_dirs = sorted(
        [p for p in root.iterdir() if p.is_dir() and p.name.startswith("mm_")]
    )
    if not island_dirs:
        raise RuntimeError(f"No island subdirectories (mm_*) found under {root}")

    output_dir = Path(args.output_dir) if args.output_dir else archive_path.parent

    print(f"Archive        : {archive_path}")
    print(f"Islands found  : {len(island_dirs)}")
    print(
        f"Island offset  : {args.island_offset}  → indices {args.island_offset}..{args.island_offset + len(island_dirs) - 1}"
    )
    print(f"Step filter    : {'all CSVs' if args.step <= 0 else f'every {args.step}'}")
    print(f"Output dir     : {output_dir}")
    print()

    for local_idx, island_dir in enumerate(island_dirs):
        global_idx = local_idx + args.island_offset
        package_mm_island(
            island_dir=island_dir,
            output_dir=output_dir,
            base_name=args.base_name,
            island_idx=global_idx,  # <-- offset applied here
            step=max(args.step, 0),
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
