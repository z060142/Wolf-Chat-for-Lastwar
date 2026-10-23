#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Template matching diagnostics for the "click avatar -> profile -> copy name" flow.

Measures the best match confidence of each template on the live screen using the same
method as pyautogui.locateAllOnScreen (OpenCV TM_CCOEFF_NORMED, colour, full screen),
and compares it with the threshold ui_interaction.py uses.

Usage:
    # Watch for 20 seconds; perform the flow manually in the game meanwhile
    python tools/diagnose_templates.py --watch 20

    # Single snapshot after 3 seconds, save annotated screenshot
    python tools/diagnose_templates.py --delay 3 --save

    # Specific templates (keys below) only
    python tools/diagnose_templates.py --watch 20 profile_page profile_option
"""

import argparse
import datetime
import os
import sys
import time

import cv2
import numpy as np
import pyautogui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(ROOT, "templates")

# key: (file, threshold used in ui_interaction.py, step description)
TEMPLATES = {
    "profile_page": ("Profile_page.png", 0.9, "avatar clicked -> profile card open (STATE_CONFIDENCE_THRESHOLD)"),
    "profile_option": ("profile_option.png", 0.7, "profile card -> user details option"),
    "copy_name_button": ("copy_name_button.png", 0.7, "user details -> Copy Name button"),
    "capitol_button": (os.path.join("capitol", "capitol_#11.png"), 0.8, "profile page -> Capitol button (position removal)"),
    "profile_name_page": ("Profile_Name_page.png", 0.9, "user details page state"),
}


def load_templates(keys):
    loaded = {}
    for key in keys:
        filename, threshold, desc = TEMPLATES[key]
        path = os.path.join(TEMPLATE_DIR, filename)
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"[WARN] cannot load template {path}")
            continue
        loaded[key] = (img, threshold, desc, path)
    return loaded


def grab_screen():
    shot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)


def measure(screen, templates):
    results = {}
    for key, (tpl, threshold, _desc, _path) in templates.items():
        if screen.shape[0] < tpl.shape[0] or screen.shape[1] < tpl.shape[1]:
            results[key] = (0.0, (0, 0))
            continue
        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        h, w = tpl.shape[:2]
        results[key] = (float(max_val), (max_loc[0] + w // 2, max_loc[1] + h // 2))
    return results


def save_annotated(screen, templates, results, tag="all"):
    out = screen.copy()
    for key, (conf, center) in results.items():
        tpl, threshold, _desc, _path = templates[key]
        h, w = tpl.shape[:2]
        color = (0, 200, 0) if conf >= threshold else (0, 0, 255)
        tl = (center[0] - w // 2, center[1] - h // 2)
        cv2.rectangle(out, tl, (tl[0] + w, tl[1] + h), color, 2)
        cv2.putText(out, f"{key} {conf:.2f}/{threshold}", (tl[0], max(12, tl[1] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    save_dir = os.path.join(ROOT, "debug_screenshots")
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, f"template_diag_{datetime.datetime.now():%Y%m%d_%H%M%S}_{tag}.png")
    cv2.imwrite(path, out)
    return path


def print_table(templates, results, prefix=""):
    for key, (conf, center) in results.items():
        _tpl, threshold, desc, _path = templates[key]
        status = "PASS" if conf >= threshold else "fail"
        print(f"{prefix}{status} {key:<18} conf={conf:.3f} need>={threshold:<4} at {center}  ({desc})")


def main():
    parser = argparse.ArgumentParser(description="Diagnose template matching on the live screen")
    parser.add_argument("keys", nargs="*", help=f"Template keys (default: all). Choices: {', '.join(TEMPLATES)}")
    parser.add_argument("--delay", type=float, default=0, help="Seconds to wait before a single snapshot")
    parser.add_argument("--watch", type=float, default=0, help="Sample repeatedly for N seconds and report peaks")
    parser.add_argument("--interval", type=float, default=0.3)
    parser.add_argument("--save", action="store_true", help="Save annotated screenshot(s) to debug_screenshots/")
    args = parser.parse_args()

    keys = args.keys or list(TEMPLATES)
    unknown = [k for k in keys if k not in TEMPLATES]
    if unknown:
        print(f"Unknown keys: {unknown}")
        return 1
    templates = load_templates(keys)
    print(f"Screen size: {pyautogui.size()}")
    for key, (tpl, threshold, desc, path) in templates.items():
        print(f"  {key:<18} {tpl.shape[1]}x{tpl.shape[0]}  {path}")

    if not args.watch:
        if args.delay:
            print(f"Waiting {args.delay}s...")
            time.sleep(args.delay)
        screen = grab_screen()
        results = measure(screen, templates)
        print_table(templates, results)
        if args.save:
            print(f"Saved: {save_annotated(screen, templates, results)}")
        return 0

    print(f"\nWatching for {args.watch}s - perform the flow in the game now (Ctrl+C to stop)\n")
    peaks = {k: (0.0, (0, 0), None, 0.0) for k in templates}  # conf, center, screen, t
    start = time.time()
    was_pass = {k: False for k in templates}
    try:
        while time.time() - start < args.watch:
            t = time.time() - start
            screen = grab_screen()
            results = measure(screen, templates)
            for key, (conf, center) in results.items():
                threshold = templates[key][1]
                if conf > peaks[key][0]:
                    peaks[key] = (conf, center, screen if args.save else None, t)
                passed = conf >= threshold
                if passed != was_pass[key]:
                    state = "APPEARED" if passed else "gone"
                    print(f"[{t:5.1f}s] {key:<18} {state} (conf={conf:.3f}, need>={threshold}) at {center}")
                    was_pass[key] = passed
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass

    print("\n=== Peak confidence during watch ===")
    for key, (conf, center, screen, t) in peaks.items():
        _tpl, threshold, desc, _path = templates[key]
        status = "PASS" if conf >= threshold else "FAIL"
        print(f"{status} {key:<18} peak={conf:.3f} need>={threshold:<4} at {center} (t={t:.1f}s)  ({desc})")
        if args.save and screen is not None:
            print(f"      saved: {save_annotated(screen, {key: templates[key]}, {key: (conf, center)}, tag=key)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
