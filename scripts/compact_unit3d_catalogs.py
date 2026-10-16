#!/usr/bin/env python3
"""Compact only UNIT3D regions/distributors against default.json in a separate directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from src.unit3d_catalogs import compact_catalog

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Extracted JSON files or directories containing them")
    parser.add_argument("--default", type=Path, default=root / "data/unit3d_catalogs/default.json")
    parser.add_argument("--output-dir", required=True, type=Path, help="Separate directory for compacted JSONs; existing files are never overwritten")
    args = parser.parse_args()
    try:
        baseline_path = args.default.resolve(strict=True)
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        files = sorted({file.resolve(strict=True) for path in args.inputs for file in (sorted(path.glob("*.json")) if path.is_dir() else [path])} - {baseline_path})
        if not files:
            raise ValueError("No tracker JSON files found")
        output_dir = args.output_dir.resolve()
        prepared: dict[Path, tuple[str, int]] = {}
        for file in files:
            target = output_dir / file.name
            if target.parent == file.parent or target.exists() or target in prepared or target == baseline_path:
                raise ValueError(f"Output must be a new file in a separate directory: {target}")
            source = file.read_text(encoding="utf-8")
            compact = compact_catalog(json.loads(source), baseline)
            content = json.dumps(compact, ensure_ascii=False, indent=2) + "\n"
            prepared[target] = (content, len(source.encode("utf-8")))
        output_dir.mkdir(parents=True, exist_ok=True)
        for target, (content, original_bytes) in prepared.items():
            with target.open("x", encoding="utf-8", newline="\n") as output:
                output.write(content)
            compact_bytes = len(content.encode("utf-8"))
            print(f"{target.name}: {original_bytes:,} -> {compact_bytes:,} bytes ({1 - compact_bytes / original_bytes:.1%} smaller)")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
