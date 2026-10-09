"""python -m src.pipeline [--check] [--raw DIR] [--out DIR]"""

import argparse
import sys

from . import PROCESSED, RAW, REFERENCE, run, stale, write


def main(argv=None):
    p = argparse.ArgumentParser(description="Build data/processed/ from data/raw/ (raw files are only read).")
    p.add_argument("--raw", default=RAW, help="raw CSV directory (default: data/raw)")
    p.add_argument("--reference", default=REFERENCE, help="reference directory (default: data/reference)")
    p.add_argument("--out", default=PROCESSED, help="output directory (default: data/processed)")
    p.add_argument("--check", action="store_true", help="do not write; exit 1 if outputs are stale")
    args = p.parse_args(argv)

    tables = run(args.raw, args.reference)
    if args.check:
        bad = stale(tables, args.out)
        if bad:
            print("stale: " + ", ".join(bad) + " - run: python -m src.pipeline", file=sys.stderr)
            return 1
        print("processed data is up to date")
        return 0
    write(tables, args.out)
    for name, (_, rows) in tables.items():
        print(f"{name}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
