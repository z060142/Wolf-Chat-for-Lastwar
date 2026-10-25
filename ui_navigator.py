"""
UI navigator: an internal map of the game's screens.

Instead of "see a template, click it, hope", every interaction goes through the map:
  1. identify()       - which screen are we on (one frame, top-most overlay first)
  2. wait_screen()    - wait until the screen is *stable* (same answer over several frames)
  3. click_and_expect - confirm the starting screen, find the button (settled), click,
                        then confirm the click had its effect (expected screen / condition).
                        No effect -> click again; unexpected screen -> stop and report it.
  4. recover_to_chat  - walk back to the chat room using each screen's known back action.

Every transition is logged as "[Nav] a --label--> b (0.42s)". When a step lands somewhere
unexpected, a screenshot is saved to debug_screenshots/nav/ so the map can be refined.
"""

import os
import time
import datetime
from collections import deque
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# Screen signatures, checked top-most first: an overlay hides what is under it, so the first hit wins.
# Each entry: (screen name, ((template key, confidence or None for the detector's state confidence), ...))
SCREENS: Sequence[Tuple[str, Tuple[Tuple[str, Optional[float]], ...]]] = (
    ('confirm_dialog', (('confirm_button', 0.8), ('update_confirm', 0.8))),
    ('bubble_menu', (('reply_button', 0.8), ('copy_menu_item', 0.75))),
    ('user_details', (('profile_name_page', None),)),
    ('position_page', tuple((k, None) for k in ('page_dev', 'page_int', 'page_sci', 'page_sec',
                                                 'page_str', 'page_adm', 'page_mil'))),
    ('capitol', (('president_title', None),)),
    ('profile_card', (('profile_page', None),)),
    ('main_screen', (('base_screen', 0.8), ('world_map_screen', 0.8))),
    ('chat_room', (('chat_room', None), ('world_chat', None), ('private_chat', None))),
)
CHAT = 'chat_room'
UNKNOWN = 'unknown'

# How to step back from each screen towards the chat room, tried in order until the screen changes.
# ('esc',), ('click', template_key), ('click_xy', (x, y))
BACK_ACTIONS: Dict[str, Sequence[tuple]] = {
    'confirm_dialog': (('esc',), ('click', 'update_confirm')),  # ESC cancels; update prompts can only be confirmed
    'bubble_menu': (('esc',),),
    'user_details': (('esc',),),
    'position_page': (('esc',), ('click', 'close_button')),
    'capitol': (('esc',), ('click', 'back_arrow')),
    'profile_card': (('esc',),),
    'main_screen': (('click_xy', (600, 1300)), ('esc',)),  # chat shortcut on base/world map
    UNKNOWN: (('esc',),),
}

STABLE_SECONDS = 0.3     # a screen counts as reached once identified identically for this long
STABLE_FRAMES = 3        # ... and in at least this many consecutive checks
POLL_SECONDS = 0.05
SNAPSHOT_DIR = os.path.join("debug_screenshots", "nav")
SNAPSHOT_KEEP = 60

Target = Union[str, Tuple[int, int], Callable[[], Optional[Tuple[int, int]]]]


class NavResult:
    def __init__(self, ok: bool, screen: str, message: str = "", attempts: int = 0, key: Optional[str] = None):
        self.ok, self.screen, self.message, self.attempts, self.key = ok, screen, message, attempts, key

    def __bool__(self):
        return self.ok

    def __repr__(self):
        return f"NavResult(ok={self.ok}, screen={self.screen!r}, attempts={self.attempts}, message={self.message!r})"


class UINavigator:
    def __init__(self, detector, interactor):
        self.det = detector
        self.ui = interactor
        self.last_screen: Optional[str] = None
        self.history: deque = deque(maxlen=30)

    # ------------------------------------------------------------------ where am I
    def identify(self) -> Tuple[str, Optional[str], Optional[Tuple[int, int]]]:
        """(screen, matched template key, its center) for the current frame."""
        def scan():
            for name, signature in SCREENS:
                for key, conf in signature:
                    if key not in self.det.templates:
                        continue
                    locs = self.det._find_template(key, confidence=conf or self.det.state_confidence)
                    if locs:
                        return name, key, locs[0]
            return UNKNOWN, None, None

        vision = getattr(self.det, 'vision', None)
        if vision:
            try:
                with vision.frozen():  # one capture for the whole scan
                    return scan()
            except Exception as e:
                print(f"[Nav] Warning: shared-frame scan failed ({e}), scanning templates individually")
        return scan()

    def wait_screen(self, expect: Optional[Iterable[str]] = None, timeout: float = 3.0,
                    leave: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Wait until the screen is stable and satisfies the condition:
        in `expect` (if given), or a known screen other than `leave` (if given), or anything (neither given).
        Returns (screen, matched key) of the last stable screen (or the last seen one on timeout)."""
        expect = set(expect) if expect else None
        deadline = time.time() + timeout
        cur, key, since, frames = None, None, 0.0, 0
        stable: Tuple[Optional[str], Optional[str]] = (None, None)
        while True:
            name, k, _ = self.identify()
            now = time.time()
            if name != cur:
                cur, key, since, frames = name, k, now, 1
            else:
                frames += 1
            if frames >= STABLE_FRAMES and now - since >= STABLE_SECONDS:
                stable = (cur, key)
                if expect is not None:
                    if cur in expect:
                        return cur, key
                elif leave is not None:
                    if cur not in (leave, UNKNOWN):
                        return cur, key
                else:
                    return cur, key
            if now >= deadline:
                return stable if stable[0] is not None else (cur, key)
            time.sleep(POLL_SECONDS)

    def current(self, timeout: float = 2.0) -> str:
        """Stable current screen (waits out transitions)."""
        screen, _ = self.wait_screen(timeout=timeout)
        self._note(screen)
        return screen

    # ------------------------------------------------------------------ act
    def click_and_expect(self, target: Target, expect: Iterable[str] = (), from_screen: Optional[str] = None,
                         until: Optional[Callable[[], bool]] = None, timeout: float = 3.0, retries: int = 2,
                         confidence: float = 0.8, label: Optional[str] = None) -> NavResult:
        """Click `target` and confirm the click took effect.
        target: template key (located and settled each attempt), fixed (x, y), or a callable returning (x, y).
        Effect: reaching a screen in `expect` (stable), or `until()` becoming true (e.g. clipboard changed).
        from_screen: the screen the click must start from; if we are elsewhere, nothing is clicked.
        A click with no effect (still on from_screen) is retried; an unexpected screen ends the step."""
        expect = set(expect)
        label = label or (target if isinstance(target, str) else 'click')
        if from_screen:
            here = self.current()
            if here != from_screen:
                return self._unexpected(f"before '{label}'", {from_screen}, here)
        start_screen = from_screen or self.last_screen

        for attempt in range(1, retries + 2):
            coords = self._resolve(target, confidence)
            if coords is None:
                screen = self.current(timeout=1.0)
                if screen in expect:  # a previous click took effect late
                    return NavResult(True, screen, f"'{label}' already done", attempt)
                return NavResult(False, screen, f"'{label}' not found on screen '{screen}'", attempt)

            t0 = time.time()
            self.ui.click_at(coords[0], coords[1])

            if until is not None:
                deadline = time.time() + timeout
                while time.time() < deadline:
                    if until():
                        retry = f", attempt {attempt}" if attempt > 1 else ""
                        line = f"[Nav] {start_screen or '?'} --{label}--> done ({time.time() - t0:.2f}s{retry})"
                        self.history.append(line)
                        print(line)
                        return NavResult(True, start_screen or UNKNOWN, "condition met", attempt)
                    time.sleep(POLL_SECONDS)
                print(f"[Nav] '{label}' had no visible effect (attempt {attempt}), retrying")
                continue

            screen, key = self.wait_screen(expect=expect, timeout=timeout)
            if screen in expect:
                self._log(start_screen, label, screen, t0, attempt)
                return NavResult(True, screen, "", attempt, key)
            if screen in (start_screen, UNKNOWN, None):
                print(f"[Nav] '{label}' had no effect, still on '{screen}' (attempt {attempt}), retrying")
                continue
            return self._unexpected(f"after '{label}'", expect, screen, attempt)

        screen = self.current(timeout=1.0)
        if until is None and screen in expect:
            return NavResult(True, screen, "", retries + 1)
        return self._unexpected(f"'{label}' never took effect", expect or {'(condition)'}, screen, retries + 1)

    def recover_to_chat(self, max_steps: int = 8) -> bool:
        """Walk back to the chat room using the map. True once the chat room is confirmed."""
        for _ in range(max_steps):
            screen = self.current()
            if screen == CHAT:
                return True
            print(f"[Nav] Recovering from '{screen}' to chat room...")
            for action in BACK_ACTIONS.get(screen, BACK_ACTIONS[UNKNOWN]):
                t0 = time.time()
                if not self._do(action):
                    continue
                after, _ = self.wait_screen(leave=screen, timeout=2.0)
                if after != screen:
                    self._log(screen, self._action_label(action), after, t0, 1)
                    break
                print(f"[Nav] '{self._action_label(action)}' did not leave '{screen}'")
        ok = self.current() == CHAT
        if not ok:
            self._snapshot(f"recover_failed_{self.last_screen}")
            print(f"[Nav] Could not get back to the chat room (stuck on '{self.last_screen}')")
        return ok

    # ------------------------------------------------------------------ helpers
    def _resolve(self, target: Target, confidence: float) -> Optional[Tuple[int, int]]:
        if isinstance(target, str):
            locs = self.det.wait_for_template(target, timeout=2.0, confidence=confidence)
            return locs[0] if locs else None
        if callable(target):
            return target()
        return target

    def _do(self, action: tuple) -> bool:
        kind = action[0]
        if kind == 'esc':
            self.ui.press_key('esc')
            return True
        if kind == 'click':
            locs = self.det.wait_for_template(action[1], timeout=1.0, confidence=0.8)
            if not locs:
                return False
            self.ui.click_at(locs[0][0], locs[0][1])
            return True
        if kind == 'click_xy':
            self.ui.click_at(*action[1])
            return True
        return False

    @staticmethod
    def _action_label(action: tuple) -> str:
        return action[0] if len(action) == 1 else f"{action[0]} {action[1]}"

    def _note(self, screen: Optional[str]):
        if screen and screen != self.last_screen:
            self.last_screen = screen

    def _log(self, src: Optional[str], label: str, dst: str, t0: float, attempt: int):
        self._note(dst)
        retry = f", attempt {attempt}" if attempt > 1 else ""
        line = f"[Nav] {src or '?'} --{label}--> {dst} ({time.time() - t0:.2f}s{retry})"
        self.history.append(line)
        print(line)

    def _unexpected(self, where: str, expected: Iterable[str], got: str, attempts: int = 0) -> NavResult:
        self._note(got)
        msg = f"{where}: expected {sorted(expected)}, on '{got}'"
        print(f"[Nav] UNEXPECTED {msg}")
        self._snapshot(f"expected_{'-'.join(sorted(expected))}_got_{got}")
        return NavResult(False, got, msg, attempts)

    def _snapshot(self, tag: str):
        """Save the game region for refining the map (bounded number of files)."""
        try:
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)[:80]
            self.det.screenshot(self.det.region).save(os.path.join(SNAPSHOT_DIR, f"{stamp}_{safe}.png"))
            files = sorted(f for f in os.listdir(SNAPSHOT_DIR) if f.endswith(".png"))
            for old in files[:-SNAPSHOT_KEEP]:
                os.remove(os.path.join(SNAPSHOT_DIR, old))
        except Exception as e:
            print(f"[Nav] Could not save snapshot: {e}")
