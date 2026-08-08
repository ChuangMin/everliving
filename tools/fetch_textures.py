"""Re-fetch the CC0 surface textures. Only needed if `tools/textures/` is emptied.

The prepared greyscale files are committed, so rendering never touches the network.
Provenance and licence in `tools/textures/PROVENANCE.md`.
"""

from __future__ import annotations

import io
import json
import pathlib
import urllib.request
import zipfile

from PIL import Image, ImageOps

#: ambientCG asset id → the name `draw_scenes.py` asks for.
WANTED = {"Rust004": "rust", "Metal032": "metal", "Concrete034": "concrete"}

OUT = pathlib.Path(__file__).resolve().parent / "textures"


def fetch(asset: str, nickname: str) -> pathlib.Path:
    meta = json.load(
        urllib.request.urlopen(
            f"https://ambientcg.com/api/v2/full_json?id={asset}&include=downloadData",
            timeout=40,
        )
    )
    downloads = meta["foundAssets"][0]["downloadFolders"]["default"][
        "downloadFiletypeCategories"
    ]["zip"]["downloads"]
    url = next(f["downloadLink"] for f in downloads if f.get("attribute") == "1K-JPG")

    with zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=180).read())) as z:
        name = next(
            n for n in z.namelist() if "Color" in n and n.lower().endswith((".jpg", ".png"))
        )
        image = Image.open(io.BytesIO(z.read(name))).convert("L")

    # Greyscale on purpose: the palette belongs to the scene, the texture only supplies
    # surface. Three photographs' worth of white balance would fight the sodium lamp.
    image = ImageOps.autocontrast(image.resize((1024, 1024), Image.LANCZOS), cutoff=2)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{nickname}.jpg"
    image.save(path, "JPEG", quality=82)
    return path


def main() -> int:
    for asset, nickname in WANTED.items():
        path = fetch(asset, nickname)
        print(f"{nickname:9s} ← {asset:12s} {path.stat().st_size / 1024:5.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
