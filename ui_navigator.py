"""
UI navigator: an internal map of the game's screens.

Instead of "see a template, click it, hope", every interaction goes through the map:
  1. identify()       - which screen are we on (one frame, top-most overlay first)
  2. wait_screen()    - wait for a screen: an expected one is watched for directly (its signature at the
                        same spot on two polls ~30 ms apart, on a quiet frame); otherwise wait for a quiet
                        frame (nothing moving, see ScreenVision.quiet) and identify it
  3. click_and_expect - confirm the starting screen, find the button (settled), click,
                        then confirm the click had its effect (expected screen / condition).
                        No effect -> click again; unexpected screen -> stop and report it.
  4. recover_to_chat  - walk back to the chat room using each screen's known back action; after a back step
                        the screen it leads to (BACK_TARGETS) is watched for directly, like a click's expected one.

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
RANK = {name: i for i, (name, _) in enumerate(SCREENS)}  # lower = drawn on top
# Signature elements that do not sit at a fixed spot (the bubble menu opens next to the clicked bubble):
# always searched in the whole game area. Every other one is searched only where it was last seen.
MOVING = {'reply_button', 'copy_menu_item'}
# Full pages reached only through the profile card (~100 ms of searching): until one has been seen, it is
# looked for only when expected or when nothing else matched (it hides everything under it, so then nothing does)
DEEP = {'position_page', 'capitol'}

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
# Where those back actions lead. After a back step only that screen is watched for (fast, like after a click);
# if it does not show up, the full classification still finds wherever the game went. Screens without a
# fixed target (confirm_dialog: a dismissal or an update prompt; unknown) wait for a quiet frame and identify it.
BACK_TARGETS: Dict[str, set] = {
    'bubble_menu': {CHAT},
    'user_details': {'profile_card'},
    'position_page': {'capitol'},
    'capitol': {'profile_card'},
    'profile_card': {CHAT},
    'main_screen': {CHAT},
}

SAME_SPOT_PX = 3         # an expected screen counts as reached once its signature is found twice in a row this close
POLL_SECONDS = 0.03      # between two looks while waiting
# A click / key after which the game area has not changed at all for this long was ignored by the game
# (busy right after a transition, dropped): retry it now instead of waiting out the full timeout.
# Raise it if the game is slow to react (a retry then risks a double click).
NO_EFFECT_SECONDS = 1.0
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
    def identify(self, expect: Optional[Iterable[str]] = None) -> Tuple[str, Optional[str], Optional[Tuple[int, int]]]:
        """(screen, matched template key, its center) for the current frame.
        expect: screens being waited for (always searched in full, even before their first sighting)."""
        def scan(spot=(), skip=(), only=None):
            """spot: keys searched only around their last hit; skip: keys left out; only: check just these keys."""
            for name, signature in SCREENS:
                for key, conf in signature:
                    if key not in self.det.templates or key in skip or (only is not None and key not in only):
                        continue
                    locs = self.det._find_template(key, confidence=conf or self.det.state_confidence,
                                                   hint_only=key in spot)
                    if locs:
                        return name, key, locs[0]
            return UNKNOWN, None, None

        vision = getattr(self.det, 'vision', None)
        if vision:
            try:
                with vision.frozen(self.det.region):  # one capture of the game area for the whole scan
                    # Fixed elements seen before are searched only around that spot (~10x cheaper)
                    spot = {k for k, path in self.det.templates.items() if k not in MOVING and vision.has_hint(path)}
                    expect = set(expect or ())
                    skip = {k for name, sig in SCREENS if name in DEEP and name not in expect
                            for k, _ in sig if k not in spot}
                    found = scan(spot, skip)
                    if found[0] == UNKNOWN and (spot or skip):
                        # nothing matched (e.g. the game window moved, or a page not seen yet):
                        # search the remembered and the left-out ones everywhere once
                        found = scan(only=spot | skip)
                    return found
            except Exception as e:
                print(f"[Nav] Warning: shared-frame scan failed ({e}), scanning templates individually")
        return scan()

    def wait_screen(self, expect: Optional[Iterable[str]] = None, timeout: float = 3.0,
                    leave: Optional[str] = None, start: Optional[str] = None, ref=None) -> Tuple[str, Optional[str]]:
        """Wait until the screen satisfies the condition:
        in `expect` (if given), or a known screen other than `leave` (if given), or anything (neither given).
        expect: only the expected screens' signatures are watched (fast, see _wait_expected); `start` (default:
        the last known screen) is the screen we come from - if it lies on top of an expected one, it must be gone.
        Otherwise: quiet frame + identify, repeated (with `leave`) until the condition holds or the timeout.
        ref: game-area frame from just before the click / key; still unchanged after NO_EFFECT_SECONDS = it was
        ignored, stop waiting early.
        Returns (screen, matched key); on timeout the screen the last look found."""
        if expect:
            expect = set(expect)
            got = self._wait_expected(expect, self.last_screen if start is None else start, timeout, ref)
            # nothing expected showed up: classify where we are (full scan)
            return got if got else self._settled(expect)
        t0 = time.time()
        while True:
            name, key = self._settled()
            if leave is None or name not in (leave, UNKNOWN) or time.time() - t0 >= timeout:
                return name, key
            if name == leave and time.time() - t0 >= NO_EFFECT_SECONDS and self.det.unchanged_since(ref):
                return name, key
            time.sleep(POLL_SECONDS)

    def current(self, timeout: float = 2.0) -> str:
        """Current screen, read from a quiet frame (waits out transitions)."""
        screen, _ = self.wait_screen(timeout=timeout)
        self._note(screen)
        return screen

    def _settled(self, expect: Optional[Iterable[str]] = None) -> Tuple[str, Optional[str]]:
        """Screen on the next quiet frame: one identify(), a second only if the first found nothing known."""
        self.det.quiet()
        name, key, _ = self.identify(expect)
        if name == UNKNOWN:
            time.sleep(POLL_SECONDS)
            name, key, _ = self.identify(expect)
        return name, key

    def _look_for(self, expect: set, start: Optional[str]):
        """One frame: (screen, key, center) of the first expected screen whose signature is visible, or None.
        A start screen drawn on top of the expected one (bubble menu over the chat, user details over the
        profile card) hides nothing completely, so while its signature is still visible it counts as not there."""
        vision = getattr(self.det, 'vision', None)

        def find(key, conf):
            if key not in self.det.templates:
                return []
            spot = bool(vision) and key not in MOVING and vision.has_hint(self.det.templates[key])
            return self.det._find_template(key, confidence=conf or self.det.state_confidence, hint_only=spot)

        def look():
            covered = None
            for name, signature in SCREENS:
                if name not in expect:
                    continue
                if start in RANK and start not in expect and RANK[start] < RANK[name]:
                    if covered is None:
                        covered = any(find(k, c) for k, c in dict(SCREENS)[start])
                    if covered:
                        return None
                for key, conf in signature:
                    locs = find(key, conf)
                    if locs:
                        return name, key, locs[0]
            return None

        if vision:
            try:
                with vision.frozen(self.det.region):  # one capture for the whole look
                    return look()
            except Exception as e:
                print(f"[Nav] Warning: shared-frame look failed ({e}), checking templates individually")
        return look()

    def _wait_expected(self, expect: set, start: Optional[str], timeout: float, ref=None) -> Optional[Tuple[str, str]]:
        """Poll the expected screens' signatures. Reached = found at the same spot on two polls in a row, the
        area around it quiet, and still there after that. Returns (screen, key), or None at the timeout
        (or earlier when the game area still equals `ref` after NO_EFFECT_SECONDS: the click was ignored)."""
        def same(a, b):
            return a is not None and b is not None and a[1] == b[1] and \
                abs(a[2][0] - b[2][0]) <= SAME_SPOT_PX and abs(a[2][1] - b[2][1]) <= SAME_SPOT_PX

        t0 = time.time()
        deadline = t0 + timeout
        prev = None
        while True:
            if prev is None and ref is not None and time.time() - t0 >= NO_EFFECT_SECONDS \
                    and self.det.unchanged_since(ref):
                return None
            hit = self._look_for(expect, start)
            if same(prev, hit):
                self.det.quiet_around(hit[1], hit[2])  # still sliding / fading in: wait until it stops
                again = self._look_for(expect, start)
                if same(hit, again):
                    return again[0], again[1]
                hit = again
            prev = hit
            if time.time() >= deadline:
                return None
            time.sleep(POLL_SECONDS)

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
            # One frame is enough when we are already there (the click's effect is verified below);
            # anything else may be a transition (e.g. the menu still closing after Copy), so wait for it
            here = self.identify({from_screen})[0]
            if here != from_screen:
                here, _ = self.wait_screen(expect={from_screen}, timeout=1.5, start=here)
                self._note(here)
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

            ref = self.det.snapshot_gray() if until is None else None  # to tell "ignored" from "slow"
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

            # watch for the expected screen only; a full classification happens only if it never shows up
            screen, key = self.wait_screen(expect=expect, timeout=timeout, start=start_screen or UNKNOWN, ref=ref)
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

    def recover_to_chat(self, max_steps: int = 8, start: Optional[str] = None) -> bool:
        """Walk back to the chat room using the map. True once the chat room is confirmed.
        start: the screen we are known to be on (e.g. just confirmed by a click): skips the first look."""
        if start not in (None, UNKNOWN):
            screen = start
            self._note(screen)
        else:
            screen = self.current()
        for _ in range(max_steps):
            if screen == CHAT:
                return True
            print(f"[Nav] Recovering from '{screen}' to chat room...")
            left = False
            targets = BACK_TARGETS.get(screen)
            for action in BACK_ACTIONS.get(screen, BACK_ACTIONS[UNKNOWN]):
                ref = self.det.snapshot_gray()
                t0 = time.time()
                if not self._do(action):
                    continue
                if targets:
                    # watch for the screen this step leads to; anything else is classified once it does not show
                    after, _ = self.wait_screen(expect=targets, start=screen, timeout=2.0, ref=ref)
                else:
                    after, _ = self.wait_screen(leave=screen, timeout=2.0, ref=ref)
                if after != screen:
                    self._log(screen, self._action_label(action), after, t0, 1)
                    # a stable known screen needs no second look; 'unknown' may still be a transition
                    screen = after if after not in (UNKNOWN, None) else self.current()
                    left = True
                    break
                print(f"[Nav] '{self._action_label(action)}' did not leave '{screen}'")
            if not left:
                screen = self.current()
        ok = screen == CHAT
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
