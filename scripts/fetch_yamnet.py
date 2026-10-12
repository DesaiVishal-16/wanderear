"""Fetch a YAMNet (AudioSet) ONNX model + label map for the real classifier.

WanderEar's classifier accepts any ONNX export of YAMNet that takes a 1-D
float32 waveform and returns per-frame class scores. Get an ONNX export from the
ONNX Model Zoo / your preferred conversion, then point this script at it.

Usage:
    python scripts/fetch_yamnet.py --model-url <URL>
    python scripts/fetch_yamnet.py --labels-only

The label map is the standard AudioSet class map; if the default URL is stale,
pass --labels-url.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

DEFAULT_LABELS_URL = "https://storage.googleapis.com/audioset/yamnet_class_map.csv"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"→ {dest}")
    with urllib.request.urlopen(url, timeout=180) as resp, dest.open("wb") as fh:
        fh.write(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", default="data/models")
    parser.add_argument("--model-url", default=None, help="URL of a YAMNet ONNX export")
    parser.add_argument("--labels-url", default=DEFAULT_LABELS_URL)
    parser.add_argument("--labels-only", action="store_true")
    args = parser.parse_args()

    dest = Path(args.dest)
    if not args.labels_only:
        if not args.model_url:
            parser.error("--model-url is required unless --labels-only is set")
        download(args.model_url, dest / "yamnet.onnx")
    download(args.labels_url, dest / "yamnet_class_map.csv")
    print("\nDone. Test with:  wanderear analyze sample.wav --classifier yamnet")
    return 0


if __name__ == "__main__":
    sys.exit(main())