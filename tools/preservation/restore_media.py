"""Restore one media-atoms v1 identity from local chunks to a fresh generated path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tools.paths import VAR_DIR
from tools.preservation.media_chunks import load_manifest, restore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--chunk-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = restore(load_manifest(args.manifest, VAR_DIR), args.asset_id,
                         store=args.chunk_dir, destination=args.output, root=VAR_DIR)
    except (OSError, ValueError) as error:
        parser.exit(2, f"restore refused ({type(error).__name__}); original and existing outputs retained\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
