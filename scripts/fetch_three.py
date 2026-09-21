#!/usr/bin/env python3
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "frontend" / "vendor"
VERSION = "r180"
FILES = {
    "three.module.js": f"https://raw.githubusercontent.com/mrdoob/three.js/{VERSION}/build/three.module.js",
    "three.core.js": f"https://raw.githubusercontent.com/mrdoob/three.js/{VERSION}/build/three.core.js",
    "STLLoader.js": f"https://raw.githubusercontent.com/mrdoob/three.js/{VERSION}/examples/jsm/loaders/STLLoader.js",
}

VENDOR.mkdir(parents=True, exist_ok=True)
for name, url in FILES.items():
    target = VENDOR / name
    print(f"Fetching {url}", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=45) as response:
            data = response.read()
    except Exception as exc:
        raise SystemExit(f"ERROR: unable to download {name}: {exc}") from exc
    minimum = 1_000 if name == "STLLoader.js" else 100_000
    if len(data) < minimum:
        raise SystemExit(f"ERROR: downloaded {name} is unexpectedly small ({len(data)} bytes)")
    if name == "STLLoader.js":
        data = data.decode("utf-8").replace("from 'three';", "from './three.module.js';").encode("utf-8")
    target.write_bytes(data)
    print(f"  -> {target.relative_to(ROOT)} ({len(data)} bytes)", flush=True)

print("Three.js browser dependencies ready.", flush=True)
