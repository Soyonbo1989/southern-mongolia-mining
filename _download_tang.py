"""One-off downloader for Tang & Werner 2023 shapefile from Zenodo.
Streams each file to data/raw/tang2023/ and verifies md5.
"""
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

OUT_DIR = Path("data/raw/tang2023")
OUT_DIR.mkdir(parents=True, exist_ok=True)

with open("/tmp/zenodo_record.json") as f:
    rec = json.load(f)

files = rec["files"]
total_size = sum(f["size"] for f in files)
print(f"Downloading {len(files)} files, {total_size/1024/1024:.1f} MB total\n")

t0 = time.time()
for i, f in enumerate(files, 1):
    name = f["key"]
    url = f["links"]["self"]
    expected_md5 = f["checksum"].split(":", 1)[1]
    expected_size = f["size"]
    out = OUT_DIR / name

    if out.exists() and out.stat().st_size == expected_size:
        # quick skip if size matches
        h = hashlib.md5()
        with open(out, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() == expected_md5:
            print(f"[{i}/{len(files)}] {name}  (already present, md5 OK)")
            continue

    print(f"[{i}/{len(files)}] {name}  ({expected_size/1024/1024:.2f} MB) ... ", end="", flush=True)
    t_start = time.time()
    h = hashlib.md5()
    bytes_done = 0
    with urllib.request.urlopen(url) as resp, open(out, "wb") as out_fh:
        while True:
            chunk = resp.read(1 << 20)  # 1 MB
            if not chunk:
                break
            h.update(chunk)
            out_fh.write(chunk)
            bytes_done += len(chunk)
    elapsed = time.time() - t_start
    speed = (bytes_done / 1024 / 1024) / max(elapsed, 0.001)
    actual_md5 = h.hexdigest()
    ok = actual_md5 == expected_md5 and bytes_done == expected_size
    status = "OK" if ok else f"MISMATCH (md5 {actual_md5}, size {bytes_done})"
    print(f"{elapsed:.1f}s @ {speed:.1f} MB/s  [{status}]")
    if not ok:
        sys.exit(1)

print(f"\nAll done in {time.time()-t0:.1f}s")
print(f"Files in {OUT_DIR}/:")
for p in sorted(OUT_DIR.iterdir()):
    print(f"  {p.name}  {p.stat().st_size:>12,} bytes")
