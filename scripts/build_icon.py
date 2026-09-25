#!/usr/bin/env python3
"""Build the app icon: comic burst, masked to the macOS squircle."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def squircle_mask(size: int) -> Image.Image:
    """Apple-style superellipse. n=5 matches the system icon shape."""
    mask = Image.new("L", (size, size), 0)
    pixels = mask.load()
    half = (size - 1) / 2
    power = 5.0
    for y in range(size):
        ny = abs((y - half) / half)
        for x in range(size):
            nx = abs((x - half) / half)
            if nx**power + ny**power <= 1:
                pixels[x, y] = 255
    return mask


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    source = Image.open(root / "assets" / "thats-not-my-name-bg.png").convert("RGBA")
    side = 420
    left = max(0, (source.width - side) // 2)
    top = 8
    icon = source.crop((left, top, left + side, top + side))
    icon = icon.resize((1024, 1024), Image.Resampling.LANCZOS)
    icon.putalpha(squircle_mask(1024))

    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    png = build / "app-icon-1024.png"
    icon.save(png)
    icon.save(
        build / "app-icon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(png)


if __name__ == "__main__":
    main()
