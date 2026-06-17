#!/usr/bin/env python3
"""Split a large file into <25MB parts so it can be uploaded to GitHub.

GitHub's browser ("Add file -> Upload files") rejects files larger than 25MB.
This tool splits any file into numbered chunks (``<name>.partNN``) plus a small
JSON manifest recording the original name, size, and SHA-256 checksums. Use
``restore_split.py`` to reassemble and verify the original file.

Usage:
    python split_file.py <path-to-file> [--chunk-size-mb 20] [--out-dir DIR]

Example:
    python split_file.py fa3_fwd-0.0.3-cp39-abi3-manylinux_2_24_x86_64.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

READ_BUF = 1024 * 1024  # 1 MiB streaming buffer


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(READ_BUF), b""):
            h.update(block)
    return h.hexdigest()


def split(path: str, chunk_size: int, out_dir: str) -> str:
    if not os.path.isfile(path):
        sys.exit(f"error: not a file: {path}")
    os.makedirs(out_dir, exist_ok=True)

    base = os.path.basename(path)
    total = os.path.getsize(path)
    print(f"Splitting {base} ({total:,} bytes) into <= {chunk_size:,}-byte parts")

    chunks = []
    with open(path, "rb") as src:
        index = 0
        while True:
            data = src.read(chunk_size)
            if not data:
                break
            part_name = f"{base}.part{index:02d}"
            part_path = os.path.join(out_dir, part_name)
            with open(part_path, "wb") as dst:
                dst.write(data)
            chunks.append(
                {
                    "name": part_name,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            print(f"  wrote {part_name} ({len(data):,} bytes)")
            index += 1

    manifest = {
        "original_name": base,
        "original_size": total,
        "original_sha256": sha256_of(path),
        "chunk_size": chunk_size,
        "num_chunks": len(chunks),
        "chunks": chunks,
    }
    manifest_path = os.path.join(out_dir, f"{base}.manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote manifest {os.path.basename(manifest_path)} ({len(chunks)} chunks)")
    return manifest_path


def main() -> None:
    p = argparse.ArgumentParser(description="Split a file into <25MB GitHub-uploadable parts.")
    p.add_argument("file", help="Path to the file to split")
    p.add_argument(
        "--chunk-size-mb",
        type=float,
        default=20,
        help="Max size of each part in MB (default: 20, safely under GitHub's 25MB limit)",
    )
    p.add_argument(
        "--out-dir",
        default=".",
        help="Directory to write the parts and manifest into (default: current dir)",
    )
    args = p.parse_args()
    chunk_size = int(args.chunk_size_mb * 1024 * 1024)
    split(args.file, chunk_size, args.out_dir)


if __name__ == "__main__":
    main()
