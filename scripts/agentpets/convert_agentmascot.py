"""Convert statically extracted AgentMascot data into offline, read-only sprite packs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

FACE_LANDMARKS = {
    "chibiterasu": {"cell": (160, 139), "left_eye": (42, 59), "right_eye": (70, 59), "head_top": (67, 20)},
    "nailong": {"cell": (480, 414), "left_eye": (220, 164), "right_eye": (287, 164), "head_top": (277, 72)},
    "kurisu": {"cell": (384, 414), "left_eye": (162, 159), "right_eye": (214, 159), "head_top": (190, 58)},
}


def face_landmarks(key: str, width: int, height: int) -> dict[str, float]:
    """Measured on the immutable peek/idle atlas cell; layout changes require remeasurement."""
    profile = FACE_LANDMARKS[key]
    if (width, height) != profile["cell"]:
        raise ValueError(f"Remeasure {key} face landmarks for the changed atlas cell")
    return {
        f"{point}_{axis}": round(coords[index] / size, 4)
        for point, coords in profile.items() if point != "cell"
        for index, (axis, size) in enumerate((("x", width), ("y", height)))
    }


def ground_baselines(key, actions, native, aliases, resting_bottoms, height):
    """Use one reference per grounded action; preserve anchor offsets and all airborne artwork."""
    if key not in ("nailong", "kurisu"):
        return {}
    sources = {slug(name): name for name in native}
    sources.update({slug(name): original for name, original in aliases.items()})
    sources.update({"peek": "stand", "running-left": "walk", "running-right": "walk"})
    baselines = {}
    for action, original in sources.items():
        if native[original]["frame"] != "ground" or original in ("sitFeetDown", "dangleFeet"):
            continue
        baseline = max(resting_bottoms[frame] for frame in actions[action]["frames"]) / height
        if not 0 < baseline <= 1:
            raise ValueError(f"Invalid ground baseline for {key}/{action}")
        baselines[action] = round(baseline, 4)
    return baselines


def peek_action(key, idle_frames):
    """Use the verified native blink with a stable baseline across both frames."""
    if key not in ("nailong", "kurisu"):
        return {"frames": idle_frames[:1], "frame_ms": 160, "loop": False}
    return {
        "frames": idle_frames[:2], "frame_ms": 140,
        "frame_durations": [3200, 140], "loop": True,
    }


def slug(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def json_formatter() -> list[str]:
    """Reuse the frontend's pinned formatter without installing or downloading tools."""
    frontend = Path(__file__).resolve().parents[2] / "plugins.v3" / "agentpets" / "frontend"
    node = shutil.which("node")
    prettier = frontend / "node_modules" / "prettier" / "bin" / "prettier.cjs"
    if not node or not prettier.is_file():
        raise RuntimeError("Asset generation requires Node.js and the existing AgentPets frontend dependencies")
    return [node, str(prettier), "--config", str(frontend / ".prettierrc.json"), "--parser", "json"]


def write_json(path: Path, value: dict, formatter: list[str]) -> None:
    """Format before writing so failures cannot leave unformatted JSON behind."""
    result = subprocess.run(
        formatter,
        input=json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    path.write_text(result.stdout, encoding="utf-8", newline="\n")


def convert(extracted: Path, destination: Path, archive_sha256: str):
    formatter = json_formatter()
    data = json.loads(extracted.read_text(encoding="utf-8"))
    if set(data["profiles"]) != {"chibiterasu", "nailong", "kurisu"}:
        raise ValueError("Unexpected built-in profile identifiers")
    images = {}
    hashes = {}
    for name, encoded in data["assets"].items():
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            images[name] = image.convert("RGBA")
        hashes[name] = hashlib.sha256(raw).hexdigest()
    report = {}
    for key, profile in data["profiles"].items():
        pack_id = f"builtin-{key}"
        target = destination / pack_id
        if target.exists():
            raise ValueError(f"Refusing to overwrite existing assets: {target}")
        unit = 128 if key == "chibiterasu" else 384
        factor = unit / 128
        variants = {}
        actions = {}
        fallbacks = []

        def frame(asset, anchor=(64, 128), frame_type="ground", flipped=False):
            reference = data["anchors"][frame_type]
            dx = round((anchor[0] - reference[0]) * factor)
            dy = round((anchor[1] - reference[1]) * factor)
            identity = (asset, dx, dy, flipped)
            if identity not in variants:
                variants[identity] = f"frame-{len(variants):03}"
            return variants[identity]

        def animation(original, flipped=False):
            sequence, durations = [], []
            for pose in original["poses"]:
                source_name = pose["imageName"]
                asset = profile["images"].get(source_name)
                if asset is None:
                    asset = profile["images"]["shime1"]
                    fallbacks.append(source_name)
                name = frame(asset, pose["anchor"], original["frame"], flipped)
                duration = max(40, round(pose["duration"] * data["tick_ms"]))
                # Long holds become repeated identical cells, retaining exact timing within the pack limit.
                pieces = math.ceil(duration / 5000)
                whole, remainder = divmod(duration, pieces)
                for index in range(pieces):
                    sequence.append(name)
                    durations.append(whole + (index < remainder))
            if not 1 <= len(sequence) <= 64 or min(durations) < 40:
                raise ValueError("Animation is outside the AgentPets contract")
            result = {"frames": sequence, "frame_ms": durations[0], "loop": original["loop"]}
            if len(set(durations)) > 1:
                result["frame_durations"] = durations
            return result

        native = profile["actions"]
        # Native artwork faces left; separate mirrored cells avoid changing existing Codex mirroring rules.
        for name, action in native.items():
            actions[slug(name)] = animation(action)
        for name, original in data["aliases"].items():
            actions[slug(name)] = animation(native[original])
        actions["running-left"] = animation(native["walk"])
        actions["running-right"] = animation(native["walk"], flipped=True)
        idle = actions["idle"]["frames"][0]
        actions["peek"] = peek_action(key, actions["idle"]["frames"])
        for asset in images:
            belongs = asset.startswith(key) if key != "chibiterasu" else asset.startswith("shime")
            if belongs:
                frame(asset)

        cells = []
        positions = []
        for (asset, dx, dy, flipped), name in variants.items():
            image = ImageOps.mirror(images[asset]) if flipped else images[asset]
            left = -unit // 2 + (dx if flipped else -dx)
            top = -unit - dy
            cells.append((name, image, left, top))
            positions.append((left, top, left + image.width, top + image.height))
        left, top = min(p[0] for p in positions), min(p[1] for p in positions)
        right, bottom = max(p[2] for p in positions), max(p[3] for p in positions)
        cell_width, cell_height = right - left, bottom - top
        columns = min(8, 4096 // cell_width, len(cells))
        rows = math.ceil(len(cells) / columns)
        if rows > 16 or rows * cell_height > 4096:
            raise ValueError("Too many atlas cells")
        sheet = Image.new("RGBA", (columns * cell_width, rows * cell_height))
        frames = {}
        rendered = {}
        for index, (name, image, x, y) in enumerate(cells):
            cell = Image.new("RGBA", (cell_width, cell_height))
            cell.alpha_composite(image, (x - left, y - top))
            sheet.alpha_composite(cell, ((index % columns) * cell_width, (index // columns) * cell_height))
            frames[name] = index
            rendered[name] = cell
        frames["idle"] = frames[idle]
        resting_bottoms = {
            name: rendered[name].getbbox()[3] + dy
            for (_asset, _dx, dy, _flipped), name in variants.items()
        }
        mappings = {
            "stage.idle": "idle", "stage.blink": "idle", "stage.wave": "cheer",
            "stage.talk": "cheer", "stage.think": "think", "stage.busy": "think",
            "stage.alert": "surprise", "stage.victory": "spin-celebrate",
            "stage.confused": "surprise", "stage.doze": "sleep", "stage.held": "drag",
            "stage.fall": "fall", "stage.jump": "jump", "stage.sit": "land",
            "stage.peek": "peek", "stage.walk-left": "running-left", "stage.walk-right": "running-right",
        }
        pack = {
            "id": pack_id, "name": profile["label"],
            "description": "shine lock专属",
            "sheet": "sheet.webp", "grid": {"cols": columns, "rows": rows},
            "frames": frames, "actions": actions, "random_actions": [], "action_mappings": mappings,
            "calibration": {"left": 0, "top": 0, "right": 1, "bottom": 1, "baseline": min(1, -top / cell_height), "offset_x": 0, "offset_y": 0,
                            **face_landmarks(key, cell_width, cell_height)},
        }
        baselines = ground_baselines(key, actions, native, data["aliases"], resting_bottoms, cell_height)
        if baselines:
            pack["action_baselines"] = baselines
        target.mkdir(parents=True)
        sheet.save(target / "sheet.webp", format="WEBP", lossless=True, method=6)
        preview = rendered[idle]
        preview = preview.crop(preview.getbbox())
        for name, limit in (("preview.png", 320), ("avatar.png", 128)):
            thumbnail = preview.copy()
            thumbnail.thumbnail((limit - 12, limit - 12), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (limit, limit))
            canvas.alpha_composite(thumbnail, ((limit - thumbnail.width) // 2, (limit - thumbnail.height) // 2))
            canvas.save(target / name)
        write_json(target / "pack.json", pack, formatter)
        provenance = {
            "archive_sha256": archive_sha256, "runtime_entry": data["runtime_entry"],
            "source_profile": key, "tick_ms": data["tick_ms"],
            "minimum_frame_ms": 40,
            "source_images_sha256": {asset: hashes[asset] for asset, *_ in variants},
            "source_fallback_frames": sorted(set(fallbacks)),
            "cell_size": [cell_width, cell_height], "cells": len(cells),
            "conversion": "Lossless atlas; action-relative anchors; mirrored right walk; no source runtime executed",
        }
        write_json(target / "provenance.json", provenance, formatter)
        report[pack_id] = {"cells": len(cells), "actions": len(actions), "sheet_bytes": (target / "sheet.webp").stat().st_size, "cell_size": [cell_width, cell_height]}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("extracted", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--archive-sha256", required=True)
    arguments = parser.parse_args()
    convert(arguments.extracted, arguments.destination, arguments.archive_sha256)
