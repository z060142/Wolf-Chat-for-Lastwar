#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Validation tool for LLM position icon recognition (position_vision.py).

Examples:
    # Export the reference sheet that is sent to the model
    python tools/test_position_vision.py --sheet reference_sheet.png

    # Synthetic test: every icon degraded (scale / sub-pixel shift / blur) and placed
    # in a fake chat name row, plus crops without any icon
    python tools/test_position_vision.py --synthetic 3

    # Real crops: a folder with sub-folders named after the true label, e.g.
    #   samples/SCIENCE/*.png, samples/NONE/*.png
    # (crops are saved by the bot to debug_screenshots/position_vision/ when
    #  POSITION_VISION_SAVE_CROPS is enabled)
    python tools/test_position_vision.py --dir samples

Provider / model / key default to config.py; override with --provider/--model/--base-url/--api-key.
"""

import argparse
import os
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import position_vision as pv  # noqa: E402

FAKE_NAMES = ["[WLF]Haruka", "[ABC]Dragonslayer", "[K9]Mochi", "[XYZ]StarLord", "[TW1]Aming_77", "[RED]Nova"]


def _degrade_icon(icon: Image.Image, rng: random.Random) -> Image.Image:
    """Simulate in-game rendering: random scale, sub-pixel offset and blur."""
    scale = rng.uniform(0.8, 1.15)
    dx, dy = rng.uniform(0, 1), rng.uniform(0, 1)
    w, h = icon.size
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    # Affine transform with fractional offset -> different edge aliasing each time
    out = icon.transform((nw, nh), Image.AFFINE, (1 / scale, 0, -dx, 0, 1 / scale, -dy),
                         resample=Image.BILINEAR, fillcolor=icon.getpixel((0, 0)))
    if rng.random() < 0.5:
        out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.7)))
    return out


def make_synthetic_crop(position: str, rng: random.Random) -> Image.Image:
    """Fake chat name-row strip (~ what remove_user_position captures)."""
    bg_icon = Image.open(os.path.join(pv.TEMPLATE_DIR, "development.png")).convert("RGB")
    bg = bg_icon.getpixel((0, 0))
    width, height = rng.randint(220, 380), rng.randint(40, 50)
    crop = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(crop)

    # Top part of an avatar portrait at the far left
    avatar_color = tuple(rng.randint(40, 220) for _ in range(3))
    draw.rectangle([4, height - 18, 70, height + 30], fill=avatar_color, outline=(255, 255, 255))

    x = 82
    if position != pv.NO_POSITION:
        icon = Image.open(os.path.join(pv.TEMPLATE_DIR, pv.POSITION_ICON_FILES[position])).convert("RGB")
        icon = _degrade_icon(icon, rng)
        y = height - icon.height - rng.randint(2, 6)
        crop.paste(icon, (x, max(0, y)))
        x += icon.width + 4
    font = pv._load_font(rng.randint(14, 17))
    draw.text((x, height - 12), rng.choice(FAKE_NAMES), fill=(70, 70, 70), font=font, anchor="lm")
    return crop


def run_cases(recognizer, cases, workers: int):
    """cases: list of (label, expected, PIL image). Returns list of result dicts."""
    def one(case):
        label, expected, img = case
        res = recognizer.recognize(img)
        return {"label": label, "expected": expected, **res}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, cases))


def report(results, save_failures_dir=None, images=None):
    correct = 0
    errors = 0
    confusion = defaultdict(Counter)
    latencies = []
    for i, r in enumerate(results):
        got = r.get("position", "ERROR")
        latencies.append(r.get("latency", 0.0))
        if "error" in r:
            errors += 1
        confusion[r["expected"]][got] += 1
        ok = got == r["expected"]
        correct += ok
        mark = "OK  " if ok else "FAIL"
        print(f"{mark} {r['label']:<40} expected={r['expected']:<14} got={got:<14} "
              f"{r.get('latency', 0):.2f}s {r.get('error', '') or r.get('raw', '')[:90]!s}")
        if not ok and save_failures_dir and images is not None:
            os.makedirs(save_failures_dir, exist_ok=True)
            images[i].save(os.path.join(save_failures_dir, f"{i:03d}_{r['expected']}_as_{got}.png"))

    total = len(results)
    print("\n=== Summary ===")
    print(f"Accuracy: {correct}/{total} ({100.0 * correct / max(1, total):.1f}%)   API/parse errors: {errors}")
    if latencies:
        lat = sorted(latencies)
        print(f"Latency: avg {sum(lat) / len(lat):.2f}s, p50 {lat[len(lat) // 2]:.2f}s, max {lat[-1]:.2f}s")
    print("Per expected label:")
    for expected in sorted(confusion):
        row = confusion[expected]
        n = sum(row.values())
        print(f"  {expected:<14} {row[expected]}/{n}   " +
              ", ".join(f"{k}={v}" for k, v in row.most_common() if k != expected))
    return correct == total


def main():
    parser = argparse.ArgumentParser(description="Test LLM position icon recognition")
    parser.add_argument("--sheet", help="Save the reference sheet PNG to this path")
    parser.add_argument("--synthetic", type=int, default=0, help="Synthetic samples per position (plus NONE samples)")
    parser.add_argument("--dir", help="Folder of real crops with sub-folders named by true label")
    parser.add_argument("--image", nargs="*", help="Classify specific image file(s) (no ground truth)")
    parser.add_argument("--save-samples", help="Also save generated synthetic crops to this folder")
    parser.add_argument("--save-failures", help="Save misclassified images to this folder")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--timeout", type=float)
    args = parser.parse_args()

    if args.sheet:
        pv.build_reference_sheet().save(args.sheet)
        print(f"Reference sheet saved to {args.sheet}")
    if not (args.synthetic or args.dir or args.image):
        return 0

    # Settings: config.py first, then CLI overrides
    try:
        import config
        recognizer_cfg = {
            "provider": getattr(config, "POSITION_VISION_PROVIDER", "anthropic"),
            "model": getattr(config, "POSITION_VISION_MODEL", "claude-haiku-5-5"),
            "base_url": getattr(config, "POSITION_VISION_BASE_URL", "") or None,
            "api_key": getattr(config, "POSITION_VISION_API_KEY", None),
            "timeout": float(getattr(config, "POSITION_VISION_TIMEOUT", 6.0)),
        }
    except ImportError:
        recognizer_cfg = {"provider": "anthropic", "model": "claude-haiku-5-5",
                          "base_url": None, "api_key": None, "timeout": 6.0}
    for key in ("provider", "model", "base_url", "api_key", "timeout"):
        value = getattr(args, key)
        if value is not None:
            recognizer_cfg[key] = value
    if not recognizer_cfg["api_key"]:
        env = "ANTHROPIC_API_KEY" if recognizer_cfg["provider"] == "anthropic" else "OPENAI_API_KEY"
        recognizer_cfg["api_key"] = os.getenv(env)

    print(f"Provider={recognizer_cfg['provider']} model={recognizer_cfg['model']} "
          f"base_url={recognizer_cfg['base_url'] or '(default)'} timeout={recognizer_cfg['timeout']}s")
    recognizer = pv.PositionVisionRecognizer(**recognizer_cfg)

    cases = []
    if args.synthetic:
        rng = random.Random(args.seed)
        for position in pv.POSITION_NAMES:
            for i in range(args.synthetic):
                cases.append((f"synthetic/{position}#{i}", position, make_synthetic_crop(position, rng)))
        for i in range(max(2, args.synthetic)):
            cases.append((f"synthetic/NONE#{i}", pv.NO_POSITION, make_synthetic_crop(pv.NO_POSITION, rng)))
        if args.save_samples:
            os.makedirs(args.save_samples, exist_ok=True)
            for label, _, img in cases:
                img.save(os.path.join(args.save_samples, label.replace("/", "_").replace("#", "_") + ".png"))
    if args.dir:
        for sub in sorted(os.listdir(args.dir)):
            sub_path = os.path.join(args.dir, sub)
            expected = sub.upper()
            if not os.path.isdir(sub_path) or expected not in pv.POSITION_NAMES + [pv.NO_POSITION]:
                continue
            for name in sorted(os.listdir(sub_path)):
                if name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    img = Image.open(os.path.join(sub_path, name)).convert("RGB")
                    cases.append((f"{sub}/{name}", expected, img))
    if args.image:
        for path in args.image:
            cases.append((os.path.basename(path), "?", Image.open(path).convert("RGB")))

    if not cases:
        print("No test cases found.")
        return 1

    start = time.time()
    results = run_cases(recognizer, cases, args.workers)
    print(f"Ran {len(results)} cases in {time.time() - start:.1f}s\n")
    all_ok = report(results, args.save_failures, [c[2] for c in cases])
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
