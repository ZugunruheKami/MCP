#!/usr/bin/env python3
"""Reassemble a file that was split by ``split_file.py`` and verify it.

Point it at the ``*.manifest.json`` written during splitting (or at the original
file name -- it will look for the matching manifest). The parts must sit in the
same directory as the manifest.

Usage:
    python restore_split.py <manifest-or-original-name> [--out-dir DIR]

Examples:
    python restore_split.py fa3_fwd-0.0.3-cp39-abi3-manylinux_2_24_x86_64.txt.manifest.json
    python restore_split.py fa3_fwd-0.0.3-cp39-abi3-manylinux_2_24_x86_64.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

READ_BUF = 1024 * 1024


def find_manifest(arg: str) -> str:
    if arg.endswith(".manifest.json") and os.path.isfile(arg):
        return arg
    candidate = f"{arg}.manifest.json"
    if os.path.isfile(candidate):
        return candidate
    sys.exit(f"error: no manifest found (tried {arg!r} and {candidate!r})")


def restore(manifest_path: str, out_dir: str) -> str:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    part_dir = os.path.dirname(os.path.abspath(manifest_path))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, manifest["original_name"])

    print(f"Restoring {manifest['original_name']} from {manifest['num_chunks']} parts")
    h = hashlib.sha256()
    with open(out_path, "wb") as dst:
        for chunk in manifest["chunks"]:
            part_path = os.path.join(part_dir, chunk["name"])
            if not os.path.isfile(part_path):
                sys.exit(f"error: missing part {chunk['name']}")
            with open(part_path, "rb") as src:
                data = src.read()
            if len(data) != chunk["size"]:
                sys.exit(f"error: {chunk['name']} size mismatch")
            if hashlib.sha256(data).hexdigest() != chunk["sha256"]:
                sys.exit(f"error: {chunk['name']} checksum mismatch (corrupted download?)")
            dst.write(data)
            h.update(data)
            print(f"  appended {chunk['name']} ({len(data):,} bytes)")

    final = h.hexdigest()
    if final != manifest["original_sha256"]:
        sys.exit(f"error: restored file checksum mismatch\n  expected {manifest['original_sha256']}\n  got      {final}")
    size = os.path.getsize(out_path)
    print(f"OK: wrote {out_path} ({size:,} bytes), SHA-256 verified.")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Reassemble and verify a split file.")
    p.add_argument("target", help="The *.manifest.json file, or the original file name")
    p.add_argument("--out-dir", default=".", help="Where to write the restored file (default: current dir)")
    args = p.parse_args()
    restore(find_manifest(args.target), args.out_dir)


if __name__ == "__main__":
    main()
