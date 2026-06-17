# Large-file split / restore tools

This repo stores Python wheels as `.txt` files (rename back to `.whl` to
`pip install`). Most fit fine, but some exceed GitHub's limits.

## GitHub size limits

| Path | Limit |
|------|-------|
| `git push` (used for this repo) | **100 MB** per file |
| Browser "Add file → Upload files" | **25 MB** per file |

`fa3_fwd-0.0.3-cp39-abi3-manylinux_2_24_x86_64.txt` (~26.3 MB) is pushed
**whole** via git, which is under the 100 MB push limit. The split tools below
are only needed if you ever have to re-upload a >25 MB file through the
**browser**, or share a >100 MB file.

> Note: wheels are already zip-compressed, so gzip-ing them saves ~2% — not
> worth it. Splitting is the reliable fix.

## Splitting a file into <25 MB parts

```bash
python split_file.py path/to/bigfile.txt --chunk-size-mb 20
```

Produces:
- `bigfile.txt.part00`, `bigfile.txt.part01`, … (each ≤ chunk size)
- `bigfile.txt.manifest.json` — original name, size, and per-part + whole-file
  SHA-256 checksums

Upload the `.partNN` files and the `.manifest.json` together.

## Restoring the original file

```bash
python restore_split.py bigfile.txt
# or point directly at the manifest:
python restore_split.py bigfile.txt.manifest.json
```

This concatenates the parts (in order), verifies every chunk's SHA-256 **and**
the reassembled file's SHA-256, then writes the original back. Both scripts are
pure standard-library Python 3 — no dependencies.
