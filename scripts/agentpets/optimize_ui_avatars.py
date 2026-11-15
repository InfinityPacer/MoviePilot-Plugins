"""Generate lossless UI avatar derivatives while keeping the editable PNG originals."""

from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

AVATARS = (
    "ying/avatar.png",
    "packs/projector-cat/avatar.png",
    "packs/builtin-chibiterasu/avatar.png",
    "packs/builtin-nailong/avatar.png",
    "packs/builtin-kurisu/avatar.png",
    "packs/builtin-kurisu-z256/avatar.png",
)


def ui_path(source: Path) -> Path:
    """The UI derivative has its own name; published avatar.png paths stay intact."""
    return source.with_name("avatar.ui.webp")


def encode(source: Path) -> bytes:
    """Preserve every RGBA pixel and any embedded color/orientation metadata."""
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
        options = {
            key: image.info[key]
            for key in ("icc_profile", "exif")
            if image.info.get(key)
        }
        buffer = BytesIO()
        rgba.save(buffer, "WEBP", lossless=True, exact=True, method=6, **options)
        return buffer.getvalue()


def inspect(source: Path, output: bytes) -> dict[str, object]:
    """Validate the derivative before writing or accepting existing generated files."""
    with Image.open(source) as original, Image.open(BytesIO(output)) as restored:
        if (
            original.size != restored.size
            or original.convert("RGBA").tobytes() != restored.convert("RGBA").tobytes()
        ):
            raise ValueError(f"Avatar pixels changed: {source}")
        for key in ("icc_profile", "exif"):
            if original.info.get(key) != restored.info.get(key):
                raise ValueError(f"Avatar metadata changed: {source}")
    return {
        "png_bytes": source.stat().st_size,
        "webp_bytes": len(output),
        "rgba_equal": True,
    }


def main() -> None:
    """Write new derivatives explicitly, or validate existing ones without changes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets-root",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "plugins.v3/agentpets/frontend/src/assets",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Create missing derivatives; never overwrite existing files",
    )
    args = parser.parse_args()
    root = args.assets_root.resolve(strict=True)
    pairs = [(root / relative, ui_path(root / relative)) for relative in AVATARS]
    if args.write and any(target.exists() for _, target in pairs):
        raise FileExistsError(
            "UI derivative already exists; validate or generate in a fresh task directory"
        )
    results = []
    for source, target in pairs:
        output = encode(source) if args.write else target.read_bytes()
        result = {
            "source": source.relative_to(root).as_posix(),
            **inspect(source, output),
        }
        if args.write:
            with target.open("xb") as destination:
                destination.write(output)
        results.append(result)
    before = sum(int(row["png_bytes"]) for row in results)
    after = sum(int(row["webp_bytes"]) for row in results)
    if after >= before:
        raise ValueError("Generated avatars do not reduce the total image size")
    print(
        json.dumps(
            {
                "images": results,
                "png_bytes": before,
                "webp_bytes": after,
                "writes_performed": args.write,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
