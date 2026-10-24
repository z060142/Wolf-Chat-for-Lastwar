"""
Live on-screen test for DetectionModule waits (native vs pyautogui backend).

A borderless Tk window draws a UI template after a random delay; the detector thread calls
wait_for_template() and we measure detection latency after appearance and coordinate error.
Then the template is removed and wait_for_template_gone() is timed the same way.

Usage:
    .venv\\Scripts\\python.exe tools\\test_screen_wait.py [--trials 10] [--backend native|pyautogui|both]
"""

import argparse
import os
import random
import sys
import threading
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import config  # noqa: E402
import ui_interaction  # noqa: E402  (imports pyautogui -> process is DPI aware)
from PIL import Image, ImageTk  # noqa: E402

TEMPLATES = {
    'profile_page': ui_interaction.PROFILE_PAGE_IMG,
    'confirm_button': ui_interaction.CONFIRM_BUTTON_IMG,
    'dismiss_button': ui_interaction.DISMISS_BUTTON_IMG,
    'capitol_button': ui_interaction.CAPITOL_BUTTON_IMG,
}
WIN_X, WIN_Y, WIN_W, WIN_H = 120, 120, 700, 500


def run(backend, trials, seed):
    config.SCREEN_VISION_BACKEND = backend
    det = ui_interaction.DetectionModule(TEMPLATES, region=(WIN_X, WIN_Y, WIN_W, WIN_H))
    rng = random.Random(seed)

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.geometry(f"{WIN_W}x{WIN_H}+{WIN_X}+{WIN_Y}")
    canvas = tk.Canvas(root, width=WIN_W, height=WIN_H, bg='#20242c', highlightthickness=0)
    canvas.pack()
    photos = {k: ImageTk.PhotoImage(Image.open(p)) for k, p in TEMPLATES.items()}
    sizes = {k: Image.open(p).size for k, p in TEMPLATES.items()}
    results = []
    state = {}

    def worker():
        time.sleep(0.5)
        for i in range(trials):
            key = rng.choice(list(TEMPLATES))
            w, h = sizes[key]
            x, y = rng.randrange(0, WIN_W - w), rng.randrange(0, WIN_H - h)
            delay = rng.uniform(0.1, 0.8)
            state.update(key=key, x=x, y=y, shown_at=None, hidden_at=None)
            root.after(int(delay * 1000), lambda k=key, x=x, y=y: show(k, x, y))
            t0 = time.perf_counter()
            locs = det.wait_for_template(key, timeout=3.0, confidence=0.9)
            t_found = time.perf_counter()
            r = {'backend': backend, 'key': key, 'found': bool(locs)}
            if locs and state['shown_at']:
                r['latency_ms'] = (t_found - state['shown_at']) * 1000
                cx, cy = WIN_X + x + w // 2, WIN_Y + y + h // 2
                r['err_px'] = abs(locs[0][0] - cx) + abs(locs[0][1] - cy)
            root.after(0, hide)
            gone = det.wait_for_template_gone(key, timeout=3.0, confidence=0.9)
            t_gone = time.perf_counter()
            if gone and state['hidden_at']:
                r['gone_latency_ms'] = (t_gone - state['hidden_at']) * 1000
            r['gone'] = gone
            results.append(r)
            time.sleep(0.2)
        root.after(0, root.destroy)

    def show(key, x, y):
        canvas.delete('all')
        canvas.create_image(x, y, image=photos[key], anchor='nw')
        root.update_idletasks()
        state['shown_at'] = time.perf_counter()

    def hide():
        canvas.delete('all')
        root.update_idletasks()
        state['hidden_at'] = time.perf_counter()

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()
    return results


def summarize(results):
    found = [r for r in results if r['found']]
    lat = sorted(r['latency_ms'] for r in found if 'latency_ms' in r)
    gone = sorted(r['gone_latency_ms'] for r in results if 'gone_latency_ms' in r)
    errs = [r['err_px'] for r in found if 'err_px' in r]
    b = results[0]['backend'] if results else '?'
    print(f"[{b}] found {len(found)}/{len(results)}  "
          f"appear->detect avg {sum(lat) / max(1, len(lat)):.0f} ms max {max(lat, default=0):.0f} ms  "
          f"vanish->detect avg {sum(gone) / max(1, len(gone)):.0f} ms max {max(gone, default=0):.0f} ms  "
          f"max coord error {max(errs, default=0)} px")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--trials', type=int, default=10)
    ap.add_argument('--backend', default='both', choices=['native', 'pyautogui', 'both'])
    ap.add_argument('--seed', type=int, default=3)
    args = ap.parse_args()
    for b in (['native', 'pyautogui'] if args.backend == 'both' else [args.backend]):
        summarize(run(b, args.trials, args.seed))
