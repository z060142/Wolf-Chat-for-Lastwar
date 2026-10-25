"""
Offline simulated game for the screen map (ui_navigator.py) and the UI flows that use it.

No real screen or mouse is touched: ScreenVision's capture is patched to return frames rendered
from the real template images, and the interactor's clicks/keys/clipboard go to the simulation.
The simulated game behaves like a laggy one:
  - every screen change starts after a random delay and slides in over ANIM seconds
  - clicks during a transition/animation are ignored, and DROP_RATE of idle clicks are dropped

Usage:
    .venv\\Scripts\\python.exe tools\\sim_game_nav.py [--runs 5] [--drop 0.15] [--seed 1]
"""

import argparse
import os
import random
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import config  # noqa: E402
import ui_interaction as U  # noqa: E402
import ui_navigator  # noqa: E402
from screen_vision import ScreenVision, Box  # noqa: E402

ANIM = 0.35
SCREEN_W, SCREEN_H = 2560, 1440
POS_KEYS = {'DEVELOPMENT': 'dev', 'INTERIOR': 'int', 'SCIENCE': 'sci', 'SECURITY': 'sec',
            'STRATEGY': 'str', 'ADMINISTRATOR': 'adm', 'MILITARY': 'mil'}
BUBBLE = (360, 620, 300, 70)   # bubble on screen (x, y, w, h)


def load_templates():
    """The detector's real template map (same dict the UI loop builds)."""
    src = open(U.__file__, encoding='utf-8').read()
    body = re.search(r"essential_templates = (\{.*?\n    \})", src, re.S).group(1)
    return eval(body, vars(U))


class SimGame:
    def __init__(self, templates, rng, drop_rate):
        self.rng, self.drop_rate = rng, drop_rate
        self.img = {k: cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR) for k, p in templates.items()
                    if os.path.exists(p)}
        base = np.full((SCREEN_H, SCREEN_W, 3), (40, 34, 30), np.uint8)
        noise = np.random.default_rng(0).integers(0, 12, (SCREEN_H, SCREEN_W, 1), dtype=np.uint8)
        self.base = cv2.add(base, np.repeat(noise, 3, axis=2))
        self.lock = threading.Lock()
        self.screen, self.page = 'chat_room', None
        self.pending = None            # (screen, page, start_time)
        self.anim_start = 0.0
        self.clipboard = ''
        self.removed = []
        self.clicks = self.dropped = 0
        avatar_x = BUBBLE[0] + AVATAR_DX
        self.avatar = (avatar_x - 25, BUBBLE[1] - 10, 50, 50)

    # ---------------------------------------------------------------- layout
    def elements(self, screen, page):
        """(key, x, y) per screen; overlays include what is under them."""
        chat = [('chat_room', 100, 70), ('chat_input', 150, 1290)]
        if screen == 'chat_room':
            return chat
        if screen == 'bubble_menu':
            return chat + [('copy_menu_item', 360, 520), ('reply_button', 520, 520)]
        card = chat + [('profile_page', 150, 400), ('profile_option', 640, 400), ('capitol_button', 200, 480)]
        if screen == 'profile_card':
            return card
        if screen == 'user_details':
            return card + [('profile_name_page', 150, 300), ('copy_name_button', 400, 700)]
        capitol = [('president_title', 400, 160), ('back_arrow', 90, 70)] + \
                  [(f'pos_btn_{k}', 150, 400 + i * 70) for i, k in enumerate(POS_KEYS.values())]
        if screen == 'capitol':
            return capitol
        position = capitol + [(f'page_{page}', 100, 300), ('dismiss_button', 300, 900), ('close_button', 800, 300)]
        if screen == 'position_page':
            return position
        if screen == 'confirm_dialog':
            return position + [('confirm_button', 330, 700)]
        raise ValueError(screen)

    # ---------------------------------------------------------------- time / frames
    def _tick(self, now):
        if self.pending and now >= self.pending[2]:
            old = set(self.elements(self.screen, self.page))
            self.screen, self.page, _ = self.pending
            self.pending = None
            self.anim_start = now
            self.new_elems = set(self.elements(self.screen, self.page)) - old

    def busy(self, now):
        return self.pending is not None or now - self.anim_start < ANIM

    def frame(self):
        with self.lock:
            now = time.time()
            self._tick(now)
            img = self.base.copy()
            if self.screen in ('bubble_menu', 'chat_room', 'profile_card', 'user_details'):
                x, y, w, h = BUBBLE
                cv2.rectangle(img, (x, y), (x + w, y + h), (225, 225, 225), -1)
                cv2.circle(img, (self.avatar[0] + 25, self.avatar[1] + 25), 25, (90, 160, 200), -1)
            t = min(1.0, (now - self.anim_start) / ANIM)
            for key, x, y in self.elements(self.screen, self.page):
                if (key, x, y) in getattr(self, 'new_elems', ()) and t < 1.0:
                    x += int(140 * (1 - t) ** 2)   # slide in from the right, ease-out
                tpl = self.img.get(key)
                if tpl is None:
                    continue
                h, w = tpl.shape[:2]
                img[y:y + h, x:x + w] = tpl
            return img

    # ---------------------------------------------------------------- input
    def _go(self, screen, page=None, now=None):
        self.pending = (screen, page if page is not None else self.page, now + self.rng.uniform(0.05, 0.5))

    def _hit(self, key, px, py):
        for k, x, y in self.elements(self.screen, self.page):
            if k == key and k in self.img:
                h, w = self.img[k].shape[:2]
                if x <= px < x + w and y <= py < y + h:
                    return True
        return False

    def click(self, px, py):
        with self.lock:
            now = time.time()
            self._tick(now)
            self.clicks += 1
            if self.busy(now) or self.rng.random() < self.drop_rate:
                self.dropped += 1
                return
            s, hit = self.screen, lambda k: self._hit(k, px, py)
            ax, ay, aw, ah = self.avatar
            if s == 'chat_room':
                if ax <= px < ax + aw and ay <= py < ay + ah:
                    self._go('profile_card', now=now)
                elif BUBBLE[0] <= px < BUBBLE[0] + BUBBLE[2] and BUBBLE[1] <= py < BUBBLE[1] + BUBBLE[3]:
                    self._go('bubble_menu', now=now)
            elif s == 'bubble_menu':
                if hit('copy_menu_item'):
                    self.clipboard = 'hello wolf'
                self._go('chat_room', now=now)
            elif s == 'profile_card':
                if hit('profile_option'):
                    self._go('user_details', now=now)
                elif hit('capitol_button'):
                    self._go('capitol', now=now)
            elif s == 'user_details':
                if hit('copy_name_button'):
                    threading.Timer(self.rng.uniform(0.05, 0.4), lambda: setattr(self, 'clipboard', 'SimUser')).start()
            elif s == 'capitol':
                for name, k in POS_KEYS.items():
                    if hit(f'pos_btn_{k}'):
                        self._go('position_page', k, now=now)
                if hit('back_arrow'):
                    self._go('profile_card', now=now)
            elif s == 'position_page':
                if hit('dismiss_button'):
                    self._go('confirm_dialog', now=now)
                elif hit('close_button'):
                    self._go('capitol', now=now)
            elif s == 'confirm_dialog':
                if hit('confirm_button'):
                    self.removed.append(self.page)
                    self._go('position_page', now=now)

    def key(self, k):
        with self.lock:
            now = time.time()
            self._tick(now)
            if k != 'esc' or self.busy(now):
                return
            back = {'bubble_menu': 'chat_room', 'profile_card': 'chat_room', 'user_details': 'profile_card',
                    'capitol': 'profile_card', 'position_page': 'capitol', 'confirm_dialog': 'position_page'}
            if self.screen in back:
                self._go(back[self.screen], now=now)


class SimInteractor(U.InteractionModule):
    def __init__(self, detector, game):
        super().__init__(detector)
        self.game = game

    def click_at(self, x, y, *a, **k):
        print(f"  (sim) click ({x}, {y}) on {self.game.screen}")
        self.game.click(x, y)
        time.sleep(0.1)
        return True

    def press_key(self, key, presses=1, interval=0.1):
        print(f"  (sim) key {key} on {self.game.screen}")
        for _ in range(presses):
            self.game.key(key)
            time.sleep(interval)

    def hotkey(self, *args):
        pass

    def get_clipboard(self):
        return self.game.clipboard

    def set_clipboard(self, text):
        self.game.clipboard = text


AVATAR_DX = U.AVATAR_OFFSET_X  # avatar position relative to the bubble's left edge


def run(runs, drop, seed):
    templates = load_templates()
    rng = random.Random(seed)
    game = SimGame(templates, rng, drop)
    ScreenVision._grab_gdi = lambda self, region: np.ascontiguousarray(
        game.frame()[region[1]:region[1] + region[3], region[0]:region[0] + region[2]])
    config.SCREEN_VISION_BACKEND = 'native'
    det = U.DetectionModule(templates, confidence=U.CONFIDENCE_THRESHOLD, state_confidence=U.STATE_CONFIDENCE_THRESHOLD,
                            region=U.SCREENSHOT_REGION)
    ui = SimInteractor(det, game)

    # Position flow inputs: bubble re-location and icon recognition are not what is tested here
    extended = Box(BUBBLE[0] - U.AVATAR_EXTENSION_PX, BUBBLE[1], BUBBLE[2] + U.AVATAR_EXTENSION_PX, BUBBLE[3])
    det.locate_image = lambda *a, **k: extended
    names = list(POS_KEYS)
    results = {'recovered': 0, 'copy_text': 0, 'sender_name': 0, 'reply': 0, 'removal': 0, 'back_in_chat': 0}
    t_start = time.time()
    for i in range(runs):
        target = rng.choice(names)
        det.detect_position_icon = lambda **k: {'name': target, 'coords': (0, 0), 'confidence': 1.0,
                                                'method': 'sim', 'distance': 0.0}
        lost = rng.choice(['chat_room', 'bubble_menu', 'user_details', 'capitol', 'position_page'])
        print(f"\n===== run {i + 1}: start lost on {lost}, copy text, sender name, reply, remove {target} =====")
        with game.lock:
            game.screen, game.page, game.pending, game.anim_start = lost, POS_KEYS[rng.choice(names)], None, 0
        results['recovered'] += U.perform_state_cleanup(det, ui)
        text = ui.copy_text_at((BUBBLE[0] + 150, BUBBLE[1] + 35))
        results['copy_text'] += text == 'hello wolf'
        name = ui.retrieve_sender_name_interaction((BUBBLE[0] + AVATAR_DX, BUBBLE[1] + 15), None, None)
        results['sender_name'] += name == 'SimUser'
        U.perform_state_cleanup(det, ui)
        menu = ui.nav.click_and_expect((BUBBLE[0] + 150, BUBBLE[1] + 35), expect={'bubble_menu'},
                                       from_screen=U.CHAT, timeout=2.0, retries=2, label='bubble (reply)')
        results['reply'] += bool(menu and ui.nav.click_and_expect('reply_button', expect={U.CHAT},
                                                                   from_screen='bubble_menu', retries=2, label='Reply'))
        before = len(game.removed)
        r = U.remove_user_position(det, ui, BUBBLE, extended, U.SCREENSHOT_REGION)
        ok = r.get('status') == 'success' and game.removed[before:] == [POS_KEYS[target]]
        results['removal'] += ok
        if not ok:
            print(f"!!! removal result {r}, removed now {game.removed[before:]}")
        results['back_in_chat'] += game.screen == 'chat_room' and not game.pending
    print(f"\n===== {runs} runs in {time.time() - t_start:.0f}s, drop rate {drop:.0%}, "
          f"clicks {game.clicks} (ignored/dropped by the game {game.dropped}) =====")
    for k, v in results.items():
        print(f"  {k:13s} {v}/{runs}")
    return all(v == runs for v in results.values())


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--drop', type=float, default=0.15)
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    sys.exit(0 if run(a.runs, a.drop, a.seed) else 1)
