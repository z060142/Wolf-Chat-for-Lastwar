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

from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

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


# ---------------------------------------------------------------- realistic crops
# Layout measured from a real 510x50 crop saved by the bot:
#   avatar x8-111 (top part only) | "Lv.35" x120-193 | icon x199-226 | gender x232-261 | name x266+

REAL_CROP_GLOB = os.path.join(ROOT, "debug_screenshots", "position_vision", "*.png")
AVATAR_DIR = os.path.join(ROOT, "avatar")
REAL_NAMES = ["[1st]Moshe 1st", "[WLF]Haruka", "[ABC]Dragonslayer", "[K9]Mochi", "[TW1]Aming_77",
              "[RED]Nova", "[1st]Kitsune", "[OwO]Bigspring", "[S11]Tank Mom", "[1st]xX_Sniper_Xx"]


def _font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return pv._load_font(size)


def load_real_assets():
    """Background colour, avatar strips and the gender symbol cut from a real crop."""
    import glob
    real = sorted(glob.glob(REAL_CROP_GLOB))
    if not real:
        raise SystemExit(f"No real crop found ({REAL_CROP_GLOB}). Run the bot once with "
                         "POSITION_VISION_SAVE_CROPS enabled, or use --synthetic.")
    crop = Image.open(real[0]).convert("RGB")
    bg = crop.getpixel((300, 3))
    avatars = [crop.crop((8, 18, 112, 50))]
    for name in sorted(os.listdir(AVATAR_DIR)) if os.path.isdir(AVATAR_DIR) else []:
        try:
            img = Image.open(os.path.join(AVATAR_DIR, name)).convert("RGB").resize((104, 104), Image.LANCZOS)
            avatars.append(img.crop((0, 0, 104, 32)))
        except OSError:
            continue
    male = crop.crop((232, 17, 262, 48))
    return {"bg": bg, "avatars": avatars, "male": male, "source": real[0]}


def _female_symbol(size=30):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(["seguisym.ttf", "seguiemj.ttf", "arialbd.ttf"], 30)
    draw.text((size // 2, size // 2), "♀", fill=(236, 95, 160, 255), font=font, anchor="mm",
              stroke_width=1, stroke_fill=(255, 255, 255, 255))
    return img


def make_realistic_crop(position, rng, assets):
    """Compose a name-row crop like the bot captures; returns (image, meta)."""
    width, height = rng.choice([430, 470, 510, 510, 540]), 50
    img = Image.new("RGB", (width, height), assets["bg"])
    draw = ImageDraw.Draw(img)
    img.paste(rng.choice(assets["avatars"]), (8, 18))

    lv_font = _font(["ariblk.ttf", "arialbd.ttf"], rng.randint(20, 22))
    lv_text = f"Lv.{rng.randint(1, 99)}"
    draw.text((120, 33), lv_text, fill=(10, 10, 10), font=lv_font, anchor="lm")
    x = 120 + int(draw.textlength(lv_text, font=lv_font)) + rng.randint(4, 8)

    placement = "none"
    icon_slot_x = x
    if position != pv.NO_POSITION:
        placement = "random" if rng.random() < 0.3 else "normal"
        if placement == "normal":
            x += 28 + rng.randint(4, 7)  # reserve the icon slot, gender + name follow

    gender = rng.choice(["male", "male", "female", "none"])
    if gender == "male":
        img.paste(assets["male"], (x, 17))
        x += 30 + rng.randint(3, 6)
    elif gender == "female":
        sym = _female_symbol()
        img.paste(sym, (x, 17), sym)
        x += 30 + rng.randint(3, 6)

    name_font = _font(["arialbd.ttf"], rng.randint(19, 21))
    draw.text((x, 33), rng.choice(REAL_NAMES), fill=(105, 105, 105), font=name_font, anchor="lm")

    if position != pv.NO_POSITION:
        icon = Image.open(os.path.join(pv.TEMPLATE_DIR, pv.POSITION_ICON_FILES[position])).convert("RGB")
        icon = _degrade_icon(icon, rng)
        if placement == "normal":
            ix = icon_slot_x + rng.randint(-2, 2)
            iy = 33 - icon.height // 2 + rng.randint(-2, 2)
        else:  # anywhere in the row right of the avatar, may overlap text
            ix = rng.randint(115, width - icon.width - 2)
            iy = rng.randint(8, height - icon.height)
        img.paste(icon, (ix, max(0, min(iy, height - icon.height))))
    return img, {"placement": placement, "gender": gender}


def _observed(raw):
    try:
        import json
        import re as _re
        m = _re.search(r"\{.*\}", raw or "", _re.DOTALL)
        return json.loads(m.group(0)).get("observed", "") if m else ""
    except Exception:
        return ""


def write_html_report(path, results, images, metas, settings):
    """Self-contained HTML report (images embedded)."""
    import base64
    import html
    import io

    def b64(img):
        buf = io.BytesIO()
        img.resize((img.width * 2, img.height * 2), Image.NEAREST).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    labels = pv.POSITION_NAMES + [pv.NO_POSITION]
    total = len(results)
    correct = sum(1 for r in results if r.get("position") == r["expected"])
    errors = sum(1 for r in results if "error" in r)
    lat = sorted(r.get("latency", 0.0) for r in results)
    p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else 0

    def group_acc(pred):
        sel = [r for r, m in zip(results, metas) if pred(r, m)]
        ok = sum(1 for r in sel if r.get("position") == r["expected"])
        return ok, len(sel)

    pos_ok, pos_n = group_acc(lambda r, m: r["expected"] != pv.NO_POSITION)
    neg_ok, neg_n = group_acc(lambda r, m: r["expected"] == pv.NO_POSITION)
    norm_ok, norm_n = group_acc(lambda r, m: m["placement"] == "normal")
    rand_ok, rand_n = group_acc(lambda r, m: m["placement"] == "random")

    def pct(a, b):
        return f"{100.0 * a / b:.1f}%" if b else "-"

    confusion = {e: {g: 0 for g in labels + ["ERROR"]} for e in labels}
    for r in results:
        confusion[r["expected"]][r.get("position", "ERROR")] += 1

    rows = []
    for e in labels:
        n = sum(confusion[e].values())
        if not n:
            continue
        cells = "".join(
            f'<td class="{"diag" if g == e and confusion[e][g] else ("bad" if confusion[e][g] else "")}">'
            f'{confusion[e][g] or ""}</td>' for g in labels + ["ERROR"])
        rows.append(f"<tr><th>{e}</th>{cells}<td>{pct(confusion[e][e], n)}</td></tr>")

    fail_cards, ok_cards = [], []
    for r, img, m in zip(results, images, metas):
        got = r.get("position", "ERROR")
        info = (f"expected <b>{r['expected']}</b> &middot; got <b>{got}</b> &middot; "
                f"{m['placement']} &middot; gender {m['gender']} &middot; {r.get('latency', 0):.2f}s")
        note = html.escape(r.get("error") or _observed(r.get("raw", "")))
        card = (f'<figure><img src="data:image/png;base64,{b64(img)}" alt="{html.escape(r["label"])}">'
                f"<figcaption>{info}<br><span class=\"obs\">{note}</span></figcaption></figure>")
        (ok_cards if got == r["expected"] else fail_cards).append(card)

    header = "".join(f"<th>{g}</th>" for g in labels + ["ERROR"])
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Position Vision Test</title>
<style>
:root {{ --bg:#f6f5f2; --fg:#1d1d1f; --muted:#6b6b70; --card:#fff; --line:#dedcd6; --ok:#1f7a4d; --bad:#b3261e; --okbg:#e3f3ea; --badbg:#fbe4e2; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#18181a; --fg:#ececef; --muted:#9a9aa1; --card:#232326; --line:#3a3a3f; --ok:#6fd39b; --bad:#ff8a80; --okbg:#1d3a2b; --badbg:#47201d; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, "Segoe UI", sans-serif; }}
main {{ max-width:1100px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:17px; margin:28px 0 10px; }}
.muted {{ color:var(--muted); }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-top:16px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 12px; }}
.kpi b {{ display:block; font-size:22px; }}
.scroll {{ overflow-x:auto; }}
table {{ border-collapse:collapse; background:var(--card); font-size:13px; }}
th, td {{ border:1px solid var(--line); padding:4px 8px; text-align:center; }}
td.diag {{ background:var(--okbg); color:var(--ok); font-weight:600; }}
td.bad {{ background:var(--badbg); color:var(--bad); font-weight:600; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:12px; }}
figure {{ margin:0; background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px; }}
figure img {{ width:100%; image-rendering:pixelated; display:block; }}
figcaption {{ font-size:12px; margin-top:6px; }} .obs {{ color:var(--muted); }}
</style></head><body><main>
<h1>Position icon recognition test</h1>
<p class="muted">{html.escape(settings)}</p>
<div class="kpis">
<div class="kpi"><span class="muted">Overall</span><b>{pct(correct, total)}</b>{correct}/{total}</div>
<div class="kpi"><span class="muted">With icon</span><b>{pct(pos_ok, pos_n)}</b>{pos_ok}/{pos_n}</div>
<div class="kpi"><span class="muted">No icon (NONE)</span><b>{pct(neg_ok, neg_n)}</b>{neg_ok}/{neg_n}</div>
<div class="kpi"><span class="muted">Normal placement</span><b>{pct(norm_ok, norm_n)}</b>{norm_ok}/{norm_n}</div>
<div class="kpi"><span class="muted">Random placement</span><b>{pct(rand_ok, rand_n)}</b>{rand_ok}/{rand_n}</div>
<div class="kpi"><span class="muted">Latency avg / p95 / max</span><b>{(sum(lat) / len(lat) if lat else 0):.2f}s</b>{p95:.2f}s / {(lat[-1] if lat else 0):.2f}s</div>
<div class="kpi"><span class="muted">API / parse errors</span><b>{errors}</b>of {total}</div>
</div>
<h2>Confusion matrix (rows = expected, columns = answer)</h2>
<div class="scroll"><table><tr><th></th>{header}<th>acc</th></tr>{''.join(rows)}</table></div>
<h2>Failures ({len(fail_cards)})</h2>
<div class="grid">{''.join(fail_cards) or '<p class="muted">None</p>'}</div>
<h2>Correct ({len(ok_cards)})</h2>
<div class="grid">{''.join(ok_cards)}</div>
</main></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


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
    parser.add_argument("--realistic", type=int, default=0,
                        help="Realistic samples per position, composed from a real saved crop (avatar, Lv text, gender symbol)")
    parser.add_argument("--negatives", type=int, default=-1,
                        help="NONE samples for --realistic (default: ~15%% of all samples)")
    parser.add_argument("--report", help="Write an HTML report to this path")
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
    if not (args.synthetic or args.realistic or args.dir or args.image):
        return 0

    # Settings: config.py first, then CLI overrides
    try:
        import config
        recognizer_cfg = {
            "provider": getattr(config, "POSITION_VISION_PROVIDER", "anthropic"),
            "model": getattr(config, "POSITION_VISION_MODEL", "claude-haiku-5-5"),
            "base_url": getattr(config, "POSITION_VISION_BASE_URL", "") or None,
            "api_key": getattr(config, "POSITION_VISION_API_KEY", None),
            "timeout": float(getattr(config, "POSITION_VISION_TIMEOUT", 4.0)),
        }
    except ImportError:
        recognizer_cfg = {"provider": "anthropic", "model": "claude-haiku-5-5",
                          "base_url": None, "api_key": None, "timeout": 4.0}
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
    metas = {}
    if args.realistic:
        rng = random.Random(args.seed)
        assets = load_real_assets()
        print(f"Realistic crops based on {assets['source']} ({len(assets['avatars'])} avatars)")
        n_neg = args.negatives if args.negatives >= 0 else max(2, round(args.realistic * len(pv.POSITION_NAMES) * 0.15 / 0.85))
        plan = [p for p in pv.POSITION_NAMES for _ in range(args.realistic)] + [pv.NO_POSITION] * n_neg
        rng.shuffle(plan)
        for i, position in enumerate(plan):
            img, meta = make_realistic_crop(position, rng, assets)
            label = f"realistic/{i:03d}_{position}"
            cases.append((label, position, img))
            metas[label] = meta
        if args.save_samples:
            os.makedirs(args.save_samples, exist_ok=True)
            for label, _, img in cases:
                img.save(os.path.join(args.save_samples, label.replace("/", "_") + ".png"))
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
    if args.report:
        settings = (f"{recognizer_cfg['provider']} / {recognizer_cfg['model']} | {len(cases)} cases | "
                    f"seed {args.seed} | {time.strftime('%Y-%m-%d %H:%M')}")
        meta_list = [metas.get(c[0], {"placement": "n/a", "gender": "n/a"}) for c in cases]
        write_html_report(args.report, results, [c[2] for c in cases], meta_list, settings)
        print(f"HTML report: {args.report}")
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
