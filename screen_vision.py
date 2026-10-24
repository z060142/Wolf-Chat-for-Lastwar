"""
Native screen vision for Wolf Chat (replaces pyautogui.locateOnScreen / locateAllOnScreen).

Why:
- pyautogui grabs the whole screen and re-reads the template file on every call, then
  matches against the full haystack (~200 ms per call at 2560x1440).
- This module captures only the region it needs (GDI BitBlt), caches templates,
  remembers where each template was last seen (hint ROI), and uses a coarse
  half-resolution pass before a full-resolution verify for large searches.
- wait_for()/wait_gone() poll at a high rate so callers can replace fixed sleeps
  with "continue as soon as the screen is ready, give up after N seconds".

Scores use cv2.TM_CCOEFF_NORMED exactly like pyscreeze (color or grayscale),
so existing confidence values keep their meaning.
"""

import threading
import time
from contextlib import contextmanager
from typing import Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image

try:
    import win32con
    import win32gui
    import win32ui
    _HAS_WIN32 = True
except ImportError:  # pragma: no cover - non-Windows fallback
    _HAS_WIN32 = False

try:
    from pyscreeze import Box  # Same namedtuple pyautogui returns
except ImportError:  # pragma: no cover
    from collections import namedtuple
    Box = namedtuple('Box', 'left top width height')

Region = Tuple[int, int, int, int]  # (left, top, width, height)
Match = Tuple[int, int, int, int, float]  # (left, top, width, height, score)

HINT_MARGIN = 48           # px around the last hit to search first
COARSE_MIN_AREA = 250_000  # haystacks larger than this use the coarse pass
COARSE_MIN_SIDE = 32       # smaller templates lose too much at half resolution (tested: 24px icons missed)
COARSE_SLACK = 0.18        # coarse candidates accepted at (confidence - slack)
GRAY_SLACK = 0.12          # full-res grayscale candidates for small templates (color verify after)
MAX_CANDIDATES = 300  # verify is cheap (template-sized windows); busy screens produce many coarse peaks


def _screen_size() -> Tuple[int, int]:
    if _HAS_WIN32:
        import win32api
        return win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
    from PIL import ImageGrab
    img = ImageGrab.grab()
    return img.size


def _clip_region(region: Region, bounds: Region) -> Optional[Region]:
    x, y, w, h = region
    bx, by, bw, bh = bounds
    x0, y0 = max(x, bx), max(y, by)
    x1, y1 = min(x + w, bx + bw), min(y + h, by + bh)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


class _Template:
    __slots__ = ('color', 'gray', 'half_gray', 'w', 'h')

    def __init__(self, bgr: np.ndarray):
        self.color = bgr
        self.gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        self.h, self.w = self.gray.shape[:2]
        if min(self.w, self.h) >= COARSE_MIN_SIDE:
            self.half_gray = cv2.resize(self.gray, (self.w // 2, self.h // 2), interpolation=cv2.INTER_AREA)
        else:
            self.half_gray = None


class ScreenVision:
    """Thread-safe screen capture + template matching helper."""

    def __init__(self, debug: bool = False):
        self.debug = debug
        self._templates: Dict[str, _Template] = {}
        self._hints: Dict[str, Region] = {}
        self._lock = threading.Lock()
        self._frozen = threading.local()  # per-thread frozen full frame
        self.screen_w, self.screen_h = _screen_size()
        self.stats = {'calls': 0, 'hint_hits': 0, 'time': 0.0}

    # ------------------------------------------------------------------ capture
    def _grab_gdi(self, region: Region) -> np.ndarray:
        left, top, w, h = region
        hwnd = win32gui.GetDesktopWindow()
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        mem_dc = src_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        try:
            bmp.CreateCompatibleBitmap(src_dc, w, h)
            mem_dc.SelectObject(bmp)
            mem_dc.BitBlt((0, 0), (w, h), src_dc, (left, top), win32con.SRCCOPY)
            raw = bmp.GetBitmapBits(True)
            img = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)
            return img[:, :, :3].copy()  # BGRA -> BGR
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            mem_dc.DeleteDC()
            src_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)

    def grab(self, region: Optional[Region] = None) -> Tuple[np.ndarray, Region]:
        """Capture region (left, top, width, height) as BGR. Returns (image, actual_region)."""
        full = (0, 0, self.screen_w, self.screen_h)
        region = _clip_region(tuple(int(v) for v in region), full) if region else full
        if region is None:
            raise ValueError("Capture region is outside the screen")

        frozen = getattr(self._frozen, 'frame', None)
        if frozen is not None:
            x, y, w, h = region
            return frozen[y:y + h, x:x + w], region

        if _HAS_WIN32:
            try:
                return self._grab_gdi(region), region
            except Exception as e:
                if self.debug:
                    print(f"[ScreenVision] GDI capture failed, falling back to PIL: {e}")
        from PIL import ImageGrab
        x, y, w, h = region
        pil = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR), region

    def grab_pil(self, region: Optional[Region] = None) -> Image.Image:
        img, _ = self.grab(region)
        return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    @contextmanager
    def frozen(self):
        """Capture the screen once; every grab() in this thread reuses that frame.
        Use when checking several templates against the same moment (state checks)."""
        if getattr(self._frozen, 'frame', None) is not None:
            yield  # already frozen (nested)
            return
        self._frozen.frame, _ = self.grab(None)
        try:
            yield
        finally:
            self._frozen.frame = None

    # ---------------------------------------------------------------- templates
    def _get_template(self, needle: Union[str, Image.Image, np.ndarray]) -> Tuple[Optional[str], Optional[_Template]]:
        """Returns (cache_key, template). Paths are cached; images are not."""
        if isinstance(needle, str):
            with self._lock:
                tpl = self._templates.get(needle)
            if tpl is None:
                data = np.fromfile(needle, dtype=np.uint8)  # handles non-ASCII paths
                bgr = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
                if bgr is None:
                    return needle, None
                tpl = _Template(bgr)
                with self._lock:
                    self._templates[needle] = tpl
            return needle, tpl
        if isinstance(needle, Image.Image):
            arr = np.asarray(needle.convert('RGB'))
            return None, _Template(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        if isinstance(needle, np.ndarray):
            bgr = needle if needle.ndim == 3 else cv2.cvtColor(needle, cv2.COLOR_GRAY2BGR)
            return None, _Template(bgr)
        raise TypeError(f"Unsupported needle type: {type(needle)}")

    # ----------------------------------------------------------------- matching
    @staticmethod
    def _peaks(result: np.ndarray, threshold: float, tw: int, th: int, limit: int) -> List[Tuple[int, int, float]]:
        """Non-maximum suppression: best peaks >= threshold, best first."""
        peaks = []
        res = result.copy()
        hw, hh = max(1, tw // 2), max(1, th // 2)
        for _ in range(limit):
            _, max_val, _, (mx, my) = cv2.minMaxLoc(res)
            if max_val < threshold or not np.isfinite(max_val):
                break
            peaks.append((mx, my, float(max_val)))
            res[max(0, my - hh):my + hh + 1, max(0, mx - hw):mx + hw + 1] = -1.0
        return peaks

    def _match_in(self, tpl: _Template, hay: np.ndarray, offset: Tuple[int, int],
                  confidence: float, grayscale: bool, limit: int) -> List[Match]:
        """Full-resolution match of tpl inside hay (BGR). Coordinates returned absolute."""
        if hay.shape[0] < tpl.h or hay.shape[1] < tpl.w:
            return []
        if grayscale:
            res = cv2.matchTemplate(cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY), tpl.gray, cv2.TM_CCOEFF_NORMED)
        else:
            res = cv2.matchTemplate(hay, tpl.color, cv2.TM_CCOEFF_NORMED)
        ox, oy = offset
        return [(ox + x, oy + y, tpl.w, tpl.h, s) for x, y, s in self._peaks(res, confidence, tpl.w, tpl.h, limit)]

    def _search(self, tpl: _Template, hay: np.ndarray, region: Region,
                confidence: float, grayscale: bool, limit: int) -> List[Match]:
        hh, hw = hay.shape[:2]
        if hw * hh < COARSE_MIN_AREA or (grayscale and tpl.half_gray is None):
            return self._match_in(tpl, hay, region[:2], confidence, grayscale, limit)

        if tpl.half_gray is None:
            # Small template: full-res grayscale finds candidates (about 3x cheaper than color),
            # color verifies them.
            gray_res = cv2.matchTemplate(cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY), tpl.gray, cv2.TM_CCOEFF_NORMED)
            matches = []
            for x, y, _ in self._peaks(gray_res, confidence - GRAY_SLACK, tpl.w, tpl.h, MAX_CANDIDATES):
                x0, y0 = max(0, x - 2), max(0, y - 2)
                x1, y1 = min(hw, x + tpl.w + 2), min(hh, y + tpl.h + 2)
                matches.extend(self._match_in(tpl, hay[y0:y1, x0:x1], (region[0] + x0, region[1] + y0),
                                              confidence, False, 1))
            matches.sort(key=lambda m: m[4], reverse=True)
            return matches[:limit]

        # Coarse pass at half resolution, then verify each candidate at full resolution
        small = cv2.resize(cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY), (hw // 2, hh // 2), interpolation=cv2.INTER_AREA)
        if small.shape[0] < tpl.half_gray.shape[0] or small.shape[1] < tpl.half_gray.shape[1]:
            return self._match_in(tpl, hay, region[:2], confidence, grayscale, limit)
        coarse = cv2.matchTemplate(small, tpl.half_gray, cv2.TM_CCOEFF_NORMED)
        candidates = self._peaks(coarse, confidence - COARSE_SLACK, tpl.half_gray.shape[1],
                                 tpl.half_gray.shape[0], MAX_CANDIDATES)
        matches: List[Match] = []
        # Peak suppression in the coarse map can hide the true peak behind a stronger neighbour up to
        # half a template away, so each verify window covers that neighbourhood.
        pad_x, pad_y = tpl.w // 2 + 4, tpl.h // 2 + 4
        for cx, cy, _ in candidates:
            x0, y0 = max(0, cx * 2 - pad_x), max(0, cy * 2 - pad_y)
            x1, y1 = min(hw, cx * 2 + tpl.w + pad_x), min(hh, cy * 2 + tpl.h + pad_y)
            found = self._match_in(tpl, hay[y0:y1, x0:x1], (region[0] + x0, region[1] + y0),
                                   confidence, grayscale, 1)
            matches.extend(found)
        # Overlapping verify windows can report the same hit twice
        unique: List[Match] = []
        for m in sorted(matches, key=lambda m: m[4], reverse=True):
            if all(abs(m[0] - u[0]) > tpl.w // 2 or abs(m[1] - u[1]) > tpl.h // 2 for u in unique):
                unique.append(m)
        return unique[:limit]

    def locate_all(self, needle: Union[str, Image.Image, np.ndarray], region: Optional[Region] = None,
                   confidence: float = 0.9, grayscale: bool = False, limit: int = 50,
                   use_hint: bool = True) -> List[Match]:
        """Find all matches of needle in region. Best match first.
        use_hint: try the area around the previous hit first (single-instance UI elements)."""
        start = time.perf_counter()
        self.stats['calls'] += 1
        try:
            key, tpl = self._get_template(needle)
            if tpl is None:
                return []

            full = (0, 0, self.screen_w, self.screen_h)
            search_region = _clip_region(tuple(int(v) for v in region), full) if region else full
            if search_region is None:
                return []

            hint = self._hints.get(key) if (use_hint and key) else None
            if hint:
                hx, hy, hw, hh = hint
                hint_region = _clip_region((hx - HINT_MARGIN, hy - HINT_MARGIN,
                                            hw + 2 * HINT_MARGIN, hh + 2 * HINT_MARGIN), search_region)
                if hint_region:
                    hay, actual = self.grab(hint_region)
                    found = self._match_in(tpl, hay, actual[:2], confidence, grayscale, limit)
                    if found:
                        self.stats['hint_hits'] += 1
                        return found

            hay, actual = self.grab(search_region)
            found = self._search(tpl, hay, actual, confidence, grayscale, limit)
            if found and key:
                self._hints[key] = found[0][:4]
            return found
        finally:
            self.stats['time'] += time.perf_counter() - start

    def locate(self, needle, region: Optional[Region] = None, confidence: float = 0.9,
               grayscale: bool = False, use_hint: bool = True) -> Optional[Box]:
        found = self.locate_all(needle, region, confidence, grayscale, limit=1, use_hint=use_hint)
        return Box(*found[0][:4]) if found else None

    def best_score(self, needle, region: Optional[Region] = None, grayscale: bool = False) -> Tuple[float, Optional[Box]]:
        """Best match score anywhere in region (no threshold). For diagnostics and tiered thresholds."""
        _, tpl = self._get_template(needle)
        if tpl is None:
            return 0.0, None
        hay, actual = self.grab(region)
        if hay.shape[0] < tpl.h or hay.shape[1] < tpl.w:
            return 0.0, None
        if grayscale:
            res = cv2.matchTemplate(cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY), tpl.gray, cv2.TM_CCOEFF_NORMED)
        else:
            res = cv2.matchTemplate(hay, tpl.color, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, (mx, my) = cv2.minMaxLoc(res)
        return float(max_val), Box(actual[0] + mx, actual[1] + my, tpl.w, tpl.h)

    # ------------------------------------------------------------------ waiting
    def wait_for(self, needles: Sequence, timeout: float = 2.0, region: Optional[Region] = None,
                 confidence: float = 0.9, grayscale: bool = False, interval: float = 0.03,
                 stable_hits: int = 1) -> Optional[Tuple[int, List[Match]]]:
        """Poll until any needle appears (seen on `stable_hits` consecutive polls).
        Returns (index_of_needle, matches) or None on timeout."""
        deadline = time.perf_counter() + timeout
        streak_idx, streak = -1, 0
        while True:
            for idx, needle in enumerate(needles):
                found = self.locate_all(needle, region, confidence, grayscale, limit=5)
                if found:
                    streak = streak + 1 if idx == streak_idx else 1
                    streak_idx = idx
                    if streak >= stable_hits:
                        return idx, found
                    break
            else:
                streak_idx, streak = -1, 0
            if time.perf_counter() >= deadline:
                return None
            time.sleep(interval)

    def wait_gone(self, needle, timeout: float = 2.0, region: Optional[Region] = None,
                  confidence: float = 0.9, grayscale: bool = False, interval: float = 0.03,
                  stable_misses: int = 2) -> bool:
        """Poll until needle is absent on `stable_misses` consecutive polls. True if it went away."""
        deadline = time.perf_counter() + timeout
        misses = 0
        while True:
            if self.locate_all(needle, region, confidence, grayscale, limit=1):
                misses = 0
            else:
                misses += 1
                if misses >= stable_misses:
                    return True
            if time.perf_counter() >= deadline:
                return False
            time.sleep(interval)
