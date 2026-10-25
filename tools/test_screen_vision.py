"""
Equivalence + speed test: screen_vision.ScreenVision vs pyscreeze (pyautogui backend).

Builds haystacks from a real screenshot with UI templates pasted at random positions,
then asks both engines to find every template. Reports agreement, position error and time.

Usage:
    .venv\\Scripts\\python.exe tools\\test_screen_vision.py            # synthetic, 40 rounds
    .venv\\Scripts\\python.exe tools\\test_screen_vision.py --rounds 10 --live
"""

import argparse
import glob
import os
import random
import sys
import time

import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pyscreeze  # noqa: E402
from screen_vision import ScreenVision  # noqa: E402

pyscreeze.USE_IMAGE_NOT_FOUND_EXCEPTION = False


def template_paths():
    paths = []
    for p in sorted(glob.glob(os.path.join('templates', '**', '*.png'), recursive=True)):
        img = cv2.imread(p)
        if img is not None and 8 <= min(img.shape[:2]) and max(img.shape[:2]) <= 600:
            paths.append(p)
    return paths


def pyscreeze_all(path, hay_pil, region, confidence):
    sub = hay_pil.crop((region[0], region[1], region[0] + region[2], region[1] + region[3]))
    boxes = list(pyscreeze.locateAll(path, sub, confidence=confidence, grayscale=False) or [])
    return [(b.left + region[0], b.top + region[1], b.width, b.height) for b in boxes]


def run_synthetic(rounds, confidence, seed, native_only=False):
    rng = random.Random(seed)
    vision = ScreenVision()
    base, _ = vision.grab(None)
    paths = template_paths()
    tpls = {p: cv2.imread(p) for p in paths}
    print(f"Templates: {len(paths)}  Haystack: {base.shape[1]}x{base.shape[0]}  confidence={confidence}")

    stats = {'cases': 0, 'agree': 0, 'both_found': 0, 'only_pyscreeze': 0, 'only_native': 0,
             'pos_err_max': 0, 'placed': 0, 'placed_found': 0, 't_py': 0.0, 't_native': 0.0, 't_native_hint': 0.0, 'hint_cases': 0}
    disagreements = []

    for r in range(rounds):
        hay = base.copy()
        placed = {}
        for p in rng.sample(paths, k=min(6, len(paths))):
            t = tpls[p]
            th, tw = t.shape[:2]
            if tw >= hay.shape[1] or th >= hay.shape[0]:
                continue
            x, y = rng.randrange(0, hay.shape[1] - tw), rng.randrange(0, hay.shape[0] - th)
            hay[y:y + th, x:x + tw] = t
            placed[p] = (x, y)
        hay_pil = Image.fromarray(cv2.cvtColor(hay, cv2.COLOR_BGR2RGB))
        vision._frozen.frame = (hay, (0, 0, hay.shape[1], hay.shape[0]))  # make ScreenVision read this haystack
        vision._hints.clear()

        # Half the rounds use the bot's default game region, half the full screen
        region = (70, 50, 800, 1365) if r % 2 else (0, 0, hay.shape[1], hay.shape[0])

        for p in paths:
            s = time.perf_counter()
            py = None if native_only else pyscreeze_all(p, hay_pil, region, confidence)
            stats['t_py'] += time.perf_counter() - s
            s = time.perf_counter()
            nat = vision.locate_all(p, region=region, confidence=confidence)
            stats['t_native'] += time.perf_counter() - s
            stats['cases'] += 1
            if p in placed and region[0] <= placed[p][0] and placed[p][0] + tpls[p].shape[1] <= region[0] + region[2]                     and region[1] <= placed[p][1] and placed[p][1] + tpls[p].shape[0] <= region[1] + region[3]:
                stats['placed'] += 1
                if any(abs(m[0] - placed[p][0]) <= 1 and abs(m[1] - placed[p][1]) <= 1 for m in nat):
                    stats['placed_found'] += 1
                else:
                    x, y = placed[p]
                    th, tw = tpls[p].shape[:2]
                    exact = float(cv2.matchTemplate(hay[y:y + th, x:x + tw], tpls[p], cv2.TM_CCOEFF_NORMED)[0, 0])
                    if exact < confidence:
                        stats['placed'] -= 1  # overwritten by a later paste: not a real miss
                    else:
                        print(f"  MISS round {r} {p} at {placed[p]} exact={exact:.3f} native={[(m[0], m[1], round(m[4], 3)) for m in nat[:3]]}")

            if nat:  # second call: hint path
                s = time.perf_counter()
                vision.locate_all(p, region=region, confidence=confidence)
                stats['t_native_hint'] += time.perf_counter() - s
                stats['hint_cases'] += 1

            if native_only:
                continue
            if bool(py) == bool(nat):
                stats['agree'] += 1
                if py:
                    stats['both_found'] += 1
                    # pyscreeze returns raster order; compare against the nearest of its boxes
                    nx, ny = nat[0][:2]
                    err = min(abs(nx - bx) + abs(ny - by) for bx, by, _, _ in py)
                    stats['pos_err_max'] = max(stats['pos_err_max'], err)
            else:
                key = 'only_pyscreeze' if py else 'only_native'
                stats[key] += 1
                score, _ = vision.best_score(p, region=region)
                disagreements.append((r, p, key, round(score, 4), p in placed))
        vision._frozen.frame = None

    n = stats['cases']
    print(f"\nCases: {n}   Agreement: {stats['agree']}/{n} ({stats['agree'] / n:.1%})")
    print(f"  both found: {stats['both_found']}   only pyscreeze: {stats['only_pyscreeze']}   "
          f"only native: {stats['only_native']}   max position error: {stats['pos_err_max']} px")
    print(f"Ground truth (pasted templates inside region): native found {stats['placed_found']}/{stats['placed']}")
    print(f"Average time per call: pyscreeze {stats['t_py'] / n * 1000:.1f} ms   "
          f"native {stats['t_native'] / n * 1000:.1f} ms   "
          f"native (hint hit) {stats['t_native_hint'] / max(1, stats['hint_cases']) * 1000:.2f} ms")
    for d in disagreements[:30]:
        print(f"  round {d[0]:>3} {d[2]:<15} best={d[3]:.4f} placed={d[4]}  {d[1]}")
    return stats


def run_live(confidence):
    import pyautogui
    pyautogui.useImageNotFoundException(False)
    vision = ScreenVision()
    paths = template_paths()[:10]
    region = (70, 50, 800, 1365)
    for label, fn in [
        ('pyautogui.locateAllOnScreen', lambda p: list(pyautogui.locateAllOnScreen(p, region=region, confidence=confidence))),
        ('ScreenVision.locate_all', lambda p: vision.locate_all(p, region=region, confidence=confidence)),
    ]:
        s = time.perf_counter()
        for p in paths:
            fn(p)
        print(f"Live {label:<30} {(time.perf_counter() - s) / len(paths) * 1000:.1f} ms/call")
    for label, reg in [('full screen', None), ('game region', region), ('300x200 ROI', (200, 200, 300, 200))]:
        s = time.perf_counter()
        for _ in range(20):
            vision.grab(reg)
        print(f"Capture {label:<12} {(time.perf_counter() - s) / 20 * 1000:.2f} ms")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=40)
    ap.add_argument('--confidence', type=float, default=0.8)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--native-only', action='store_true', help='skip the slow pyscreeze baseline (ground truth only)')
    ap.add_argument('--live', action='store_true', help='also time real screen capture/matching')
    args = ap.parse_args()
    run_synthetic(args.rounds, args.confidence, args.seed, args.native_only)
    if args.live:
        run_live(args.confidence)
