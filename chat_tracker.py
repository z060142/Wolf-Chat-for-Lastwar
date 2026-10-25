"""
Chat tracker: decides which chat messages are new by their position, not by their content.

The record is the list of messages already seen, oldest first. On every clean, still frame of the chat room:
  1. split the chat into messages: background gaps give the islands (name row + avatar + bubble),
     the HSV bubble colours (bubble_colors.json) say whose bubble it is (other / bot / system row)
  2. find the newest recorded message on screen, confirmed by the recorded one above it
     (whole-message image compare, tolerant to 1-4 px jitter and to a translation line)
  3. everything below it is new; a message seen above it is history and never processed again

So the same text sent again after someone else spoke is new (it sits below), and old commands do not
re-run when someone scrolls up. A recalled message (turns into "X recalled a message") is stepped over.
The record is saved to disk, so after a game / script restart the bot continues where it stopped.

Only the plain chat room view is complete: an open bubble menu, the reply bar or a multi-line input
eat the bottom of the chat, so update() is only called while the bot is just watching.
"""

import datetime
import json
import os
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

X0, X1 = 14, 640                    # chat content columns (crop coords); x > 640 holds floating buttons
LEFT_COL, RIGHT_COL = (14, 126), (560, 640)   # avatar columns: other people left, the bot account right
GAP_ROWS = 6                        # background rows that separate two messages
CLIP_MARGIN = 3                     # a complete newest message sits 4-9 px above the input bar, a cut one <= 2 px
BOTTOM_MARGIN = 12                  # at the bottom of the chat the newest message ends this close to the input bar
MATCH = 0.95                        # whole-message similarity for "same message"
KEEP_ITEMS = 80                     # records kept (and saved)
MAX_CATCHUP = 3                     # after a restart, answer at most this many messages sent to the bot meanwhile
LOST_REBASE_SECONDS = 30            # record not found this long at the bottom of a clean chat: start over
MAX_ATTEMPTS = 3                    # tries per message before giving up on it
STILL_MIN_GAP, STILL_MAX_AGE = 0.15, 2.0  # previous look's frame counts for the stillness check in this age window
STILL_GAP = 0.1                     # otherwise: second grab this long after the first

PENDING = "to bot"


def _log(msg: str):
    print(f"[Tracker] {msg}")


class ChatTracker:
    def __init__(self, detector, nav, region: Tuple[int, int, int, int], data_dir: str):
        self.det, self.nav, self.region = detector, nav, region
        self.data_dir = data_dir
        self.colors = list(getattr(detector, "bubble_colors", []) or [])
        self.items: List[dict] = []
        self.next_seq = 1
        self.dir = 0                    # +1: content moved down (someone scrolled up), -1: back at the newest
        self.tops: Dict[int, int] = {}  # seq -> top row last time it was seen
        self.lost_since: Optional[float] = None
        self.catchup = False            # first match after loading a saved record
        self.last_verdict = ""
        self._last_layout, self._last_time = None, None  # previous still() frame: message rows, grab time
        os.makedirs(data_dir, exist_ok=True)
        self.load()

    # ------------------------------------------------------------------ frames
    def grab(self) -> np.ndarray:
        vision = getattr(self.det, "vision", None)
        if vision:
            img, _ = vision.grab(self.region)
            return np.ascontiguousarray(img)
        import pyautogui
        return cv2.cvtColor(np.array(pyautogui.screenshot(region=self.region)), cv2.COLOR_RGB2BGR)

    @staticmethod
    def _diff(img, bg):
        """Per pixel sum over B, G, R of |pixel - bg| (float32; ~10x faster than numpy int arrays)."""
        if img.size == 0:
            return np.zeros(img.shape[:2], np.float32)
        d = cv2.absdiff(np.ascontiguousarray(img), (int(bg[0]), int(bg[1]), int(bg[2]), 0))
        return cv2.transform(d, np.ones((1, 3), np.float32))

    @staticmethod
    def background_and_viewport(img):
        """Background colour from the left margin; viewport = longest run of rows whose margin is background,
        minus full-width bars at its top (sub-tab bar)."""
        margin = img[:, 5:12].reshape(-1, 3)
        q = (margin // 4).astype(np.int32)
        keys = q[:, 0] * 4096 + q[:, 1] * 64 + q[:, 2]
        vals, counts = np.unique(keys, return_counts=True)
        k = vals[counts.argmax()]
        bg = np.array([(k // 4096) * 4 + 2, ((k // 64) % 64) * 4 + 2, (k % 64) * 4 + 2])
        row_is_bg = (ChatTracker._diff(img[:, 5:12], bg) < 30).mean(axis=1) > 0.8
        best, start = (0, 0), None
        for y, ok in enumerate(list(row_is_bg) + [False]):
            if ok and start is None:
                start = y
            elif not ok and start is not None:
                if y - start > best[1] - best[0]:
                    best = (start, y)
                start = None
        y0, y1 = best
        head = min(120, y1 - y0)  # a sub-tab bar can only sit at the top
        full = (ChatTracker._diff(img[y0:y0 + head, 14:718], bg) > 30).mean(axis=1) > 0.97
        top = 0
        for y in range(head):
            if full[y]:
                top = y + 1
        return bg, (y0 + top + 2 if top else y0, y1)

    @staticmethod
    def segment(img, bg, vp):
        """Islands of content between background gaps; kind from which avatar column has content."""
        y0, y1 = vp
        content = ChatTracker._diff(img[y0:y1, X0:X1], bg) > 30
        rows = content.mean(axis=1) > 0.003
        islands, start, gap, end = [], None, 0, 0
        for y, r in enumerate(list(rows) + [False] * (GAP_ROWS + 2)):
            if r:
                if start is None:
                    start = y
                gap, end = 0, y
            elif start is not None:
                gap += 1
                if gap >= GAP_ROWS:
                    islands.append((start, end + 1))
                    start = None
        out = []
        for a, b in islands:
            blk = content[a:min(b, a + 100)]
            left = blk[:, LEFT_COL[0] - X0:LEFT_COL[1] - X0].mean()
            right = blk[:, RIGHT_COL[0] - X0:RIGHT_COL[1] - X0].mean()
            kind = "other" if left > 0.25 else "self" if left < 0.05 and right > 0.25 else "system"
            out.append({"top": a + y0, "bottom": b + y0, "kind": kind,
                        "clip_top": a <= 6, "clip_bottom": b >= (y1 - y0) - CLIP_MARGIN})
        return out

    def hsv_bubbles(self, img, vp):
        y0, y1 = vp
        if y1 <= y0:
            return []
        hsv = cv2.cvtColor(img[y0:y1, X0:X1], cv2.COLOR_BGR2HSV)
        found = []
        for c in self.colors:
            mask = cv2.inRange(hsv, np.array(c["hsv_lower"]), np.array(c["hsv_upper"]))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
            n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
            for k in range(1, n):
                x, y, w, h, area = stats[k]
                if c.get("min_area", 3000) <= area <= c.get("max_area", 100000):
                    found.append({"box": [x + X0, y + y0, x + X0 + w, y + y0 + h], "color": c["name"],
                                  "is_bot": c.get("is_bot", False)})
        # several colour classes can catch the same bubble (e.g. easter / cookie): keep one per place
        merged = []
        for b in sorted(found, key=lambda b: -(b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1])):
            if not any(_overlap(b["box"], m["box"]) > 0.6 for m in merged):
                merged.append(b)
        return merged

    @staticmethod
    def covered_rows(img, bg, vp):
        """Rows inside the chat where the left margin is not background = a banner lies over the chat."""
        y0, y1 = vp
        margin = ChatTracker._diff(img[y0:y1, 5:12], bg) >= 30
        return np.nonzero(margin.mean(axis=1) > 0.5)[0] + y0

    def messages(self, img):
        """Messages on screen, top to bottom: islands, each with the HSV bubble inside it (cross-checked:
        a bubble box spanning two islands is split, pieces of one bubble cut by an overlay are joined)."""
        bg, vp = self.background_and_viewport(img)
        islands = self.segment(img, bg, vp)
        bubbles = self.hsv_bubbles(img, vp)
        cover = self.covered_rows(img, bg, vp)
        msgs = []
        for isl in islands:
            inside = []
            for b in bubbles:
                t, btm = max(b["box"][1], isl["top"]), min(b["box"][3], isl["bottom"])
                if btm - t > 8:
                    inside.append(dict(b, box=[b["box"][0], t, b["box"][2], btm]))
            bubble = None
            if inside:
                same = [b for b in inside if b["color"] == inside[0]["color"]]
                bubble = {"box": [min(b["box"][0] for b in same), min(b["box"][1] for b in same),
                                  max(b["box"][2] for b in same), max(b["box"][3] for b in same)],
                          "color": same[0]["color"], "is_bot": same[0]["is_bot"]}
            hidden = bool(len(cover) and ((cover >= isl["top"]) & (cover < isl["bottom"])).any())
            who = ("bot" if (bubble and bubble["is_bot"]) or isl["kind"] == "self" else
                   "other" if isl["kind"] == "other" else "system")
            msgs.append({"top": isl["top"], "bottom": isl["bottom"], "who": who, "bubble": bubble,
                         "complete": not (isl["clip_top"] or isl["clip_bottom"] or hidden), "covered": hidden})
        return msgs, vp

    def still(self, check_screen: bool = True):
        """(frame, messages, viewport) of a still chat room frame, or None.
        Still = same layout (message rows) as a frame STILL_MIN_GAP..STILL_MAX_AGE s earlier: the previous call's
        frame when it is in that window (the UI loop looks every ~0.3 s), else a second grab STILL_GAP s before."""
        if check_screen and self.nav.identify()[0] != "chat_room":
            self._last_time = None
            return None
        age = time.time() - self._last_time if self._last_time is not None else None
        if age is not None and STILL_MIN_GAP <= age <= STILL_MAX_AGE:
            layout1 = self._last_layout
        else:
            f1 = self.grab()
            time.sleep(STILL_GAP)
            # the first frame only has to show the same layout (message rows), no bubble colours needed
            bg1, vp1 = self.background_and_viewport(f1)
            layout1 = [(i["top"], i["bottom"]) for i in self.segment(f1, bg1, vp1)]
        t2 = time.time()
        f2 = self.grab()
        m2, vp = self.messages(f2)
        layout2 = [(m["top"], m["bottom"]) for m in m2]
        self._last_layout, self._last_time = layout2, t2
        if layout1 != layout2:
            return None
        return f2, m2, vp

    # ------------------------------------------------------------------ comparing
    @staticmethod
    def crop(img, m):
        return cv2.cvtColor(img[m["top"]:m["bottom"], X0:X1], cv2.COLOR_BGR2GRAY)

    @staticmethod
    def similar(a, b):
        """Normalised correlation allowing +-4 px misalignment."""
        h, w = min(a.shape[0], b.shape[0]) - 8, min(a.shape[1], b.shape[1]) - 8
        if h < 8 or w < 8:
            return 0.0
        return float(cv2.matchTemplate(a[:h + 8, :w + 8], b[4:4 + h, 4:4 + w], cv2.TM_CCOEFF_NORMED).max())

    def same_message(self, a, b):
        """Whole message over the overlapping height without the bottom border: a translated bubble still
        matches its original, two replies with the same first line do not."""
        h = min(a.shape[0], b.shape[0]) - 12
        h = max(h, min(a.shape[0], b.shape[0])) if h < 14 else h
        return self.similar(a[:h], b[:h])

    def locate(self, img, msgs):
        """Newest record found on screen, confirmed by the records above it.
        Returns (ri, si, pairs) with pairs = [(record index, screen index), ...] upward, or None.
        A recalled message turns into a one-line system notice or vanishes: the walk may step over 2 gaps."""
        crops = [self.crop(img, m) if m["complete"] else None for m in msgs]

        def same(a, b):
            return crops[b] is not None and msgs[b]["who"] == self.items[a]["who"] \
                and self.same_message(self.items[a]["img"], crops[b]) >= MATCH

        def walk(ri, si):
            pairs, a, b, skips = [(ri, si)], ri - 1, si - 1, 0
            while a >= 0 and b >= 0 and crops[b] is not None:
                if same(a, b):
                    pairs.append((a, b)); a -= 1; b -= 1
                    continue
                if skips == 2:
                    break
                steps = ([(a - 1, b - 1), (a, b - 1)] if msgs[b]["who"] == "system" else []) + [(a - 1, b)]
                nxt = next(((a2, b2) for a2, b2 in steps if a2 >= 0 and b2 >= 0 and same(a2, b2)), None)
                if nxt is None:
                    break
                a, b, skips = nxt[0], nxt[1], skips + 1
            return pairs

        for ri in range(len(self.items) - 1, -1, -1):
            best = None
            for si in range(len(msgs)):
                if not same(ri, si):
                    continue
                pairs = walk(ri, si)
                # a second match is only asked for when there is a real message above to confirm with
                above = any(crops[b] is not None and msgs[b]["who"] != "system" for b in range(si))
                need = 2 if (above and ri > 0) else 1
                if len(pairs) >= need and (best is None or len(pairs) > len(best[2])):
                    best = (ri, si, pairs)
            if best:
                return best
        return None

    @staticmethod
    def at_bottom(msgs, vp):
        last = msgs[-1] if msgs else None
        return bool(last and last["complete"] and last["bottom"] >= vp[1] - BOTTOM_MARGIN)

    # ------------------------------------------------------------------ record
    def _add(self, img, m, status, keyword=None):
        item = {"seq": self.next_seq, "who": m["who"], "img": self.crop(img, m), "status": status,
                "color": m["bubble"]["color"] if m["bubble"] else None, "keyword": keyword,
                "time": datetime.datetime.now().isoformat(timespec="seconds"), "attempts": 0}
        self.next_seq += 1
        self.items.append(item)
        self.tops[item["seq"]] = m["top"]
        return item

    def _keyword(self, m):
        if not m["bubble"] or m["who"] != "other":
            return None
        x0, y0, x1, y1 = m["bubble"]["box"]
        r = self.det.find_keyword_in_region((x0 + self.region[0], y0 + self.region[1], x1 - x0, y1 - y0))
        return r[1] if r else None

    def _baseline(self, img, msgs, why):
        self.items, self.tops, self.dir, self.lost_since, self.catchup = [], {}, 0, None, False
        for m in msgs:
            if m["complete"]:
                self._add(img, m, "history")
        self.save()
        return f"{why}: {len(self.items)} messages on screen recorded as history"

    def pending(self) -> List[dict]:
        """Messages to the bot not handled yet, oldest first."""
        return [it for it in self.items if it["status"] == PENDING]

    def mark(self, item, status):
        item["status"] = status
        self.save()

    def reset(self):
        """Forget everything; the next clean frame at the bottom becomes the new history."""
        self.items, self.tops, self.dir, self.lost_since = [], {}, 0, None
        self.save()

    def screen_box(self, m) -> Tuple[int, int, int, int]:
        """(x, y, w, h) on screen of a message's bubble (or of the whole message without one)."""
        x0, y0, x1, y1 = m["bubble"]["box"] if m["bubble"] else (X0, m["top"], X1, m["bottom"])
        return (int(x0 + self.region[0]), int(y0 + self.region[1]), int(x1 - x0), int(y1 - y0))

    # ------------------------------------------------------------------ the decision
    def update(self, check_screen: bool = True) -> Tuple[str, Dict[int, dict]]:
        """Look at the chat once. Returns (verdict, view) where view maps the seq of every record
        placed on this frame to its screen message. New messages are added to the record."""
        got = self.still(check_screen)
        if got is None:
            return "not a still chat room frame - wait", {}
        img, msgs, vp = got
        if not msgs:
            return "chat area empty (game redrawing) - wait", {}
        bottom = self.at_bottom(msgs, vp)
        if not self.items:
            if not bottom:
                return "waiting: start recording only when the chat is at the bottom", {}
            return self._baseline(img, msgs, "start"), {}

        hit = self.locate(img, msgs)
        if hit is None:
            if self.dir > 0:
                return "scrolled up past the record (older history on screen) - nothing new", {}
            if any(m["covered"] for m in msgs):
                return "record not found while a banner covers the chat - wait", {}
            if bottom:
                self.lost_since = self.lost_since or time.time()
                if time.time() - self.lost_since >= LOST_REBASE_SECONDS:
                    return self._baseline(img, msgs, f"WARNING record not found for {LOST_REBASE_SECONDS}s "
                                                     f"(other channel / chat changed?), starting over"), {}
            return "LOST: record not found on screen (other channel?) - nothing processed", {}
        self.lost_since = None

        ri, si, pairs = hit
        view = {self.items[a]["seq"]: msgs[b] for a, b in pairs}
        seq = self.items[ri]["seq"]
        prev = self.tops.get(seq)
        moved = 0 if prev is None else msgs[si]["top"] - prev
        if moved:
            self.dir = 1 if moved > 0 else -1
        self.tops = {self.items[a]["seq"]: msgs[b]["top"] for a, b in pairs}

        if ri < len(self.items) - 1:
            # New messages only push content up; content that moved down means someone scrolled up,
            # and it stays "scrolled up" until the newest record is seen again
            if not bottom or moved > 0 or self.dir > 0:
                return f"scrolled up: newest visible #{seq}, newest known #{self.items[-1]['seq']} - nothing new", view
            # At the bottom, yet the newest records did not match: their look changed (re-render, expanded
            # "View All", animation). Map them by position if sender and bubble colour agree.
            later, cand = self.items[ri + 1:], msgs[si + 1:]
            for j, r in enumerate(later):
                m = cand[j] if j < len(cand) else None
                mcolor = m["bubble"]["color"] if m and m["bubble"] else None
                if m is not None and m["complete"] and m["who"] == "system" and r["who"] != "system":
                    _log(f"#{r['seq']} ({r['who']}) was recalled, a system notice took its place")
                    r.update(who="system", color=None, status="recalled" if r["status"] != "done" else "done")
                    continue
                if m is None or not m["complete"] or m["who"] != r["who"] or mcolor != r.get("color"):
                    return (f"UNCERTAIN: at the bottom but record #{r['seq']} ({r['who']}, {r.get('color')}) "
                            f"cannot be placed - wait, nothing processed"), view
            for j, r in enumerate(later):
                r["img"] = self.crop(img, cand[j])
                self.tops[r["seq"]] = cand[j]["top"]
                view[r["seq"]] = cand[j]
            _log(f"re-matched #{later[0]['seq']}..#{later[-1]['seq']} by position (their look changed)")
            si, seq = si + len(later), self.items[-1]["seq"]

        self.dir = -1
        new = []
        for m in msgs[si + 1:]:
            if not m["complete"]:
                break                                   # wait until it is fully visible / uncovered
            kw = self._keyword(m)
            status = PENDING if kw else "not to bot" if m["who"] == "other" else m["who"]
            item = self._add(img, m, status, kw)
            view[item["seq"]] = m
            new.append(f"#{item['seq']} {m['who']} [{item['color']}] -> {status}" + (f" ({kw})" if kw else ""))

        if self.catchup:
            # first look after a restart: only the newest few messages to the bot are still worth an answer
            self.catchup = False
            waiting = self.pending()
            for it in waiting[:-MAX_CATCHUP] if len(waiting) > MAX_CATCHUP else []:
                it["status"] = "skipped (sent while the bot was offline)"
            if new:
                _log(f"after restart: {len(new)} messages arrived while offline, "
                     f"{min(len(waiting), MAX_CATCHUP)} to the bot will be answered")
        if new:
            self._trim()
            self.save()
            return f"NEW below #{seq} (matched {len(pairs)} in a row): " + "; ".join(new), view
        return (f"at newest #{seq}, moved {moved:+d}px - nothing new" if moved else f"no change (newest #{seq})"), view

    # ------------------------------------------------------------------ persistence
    def _trim(self):
        if len(self.items) > KEEP_ITEMS:
            self.items = self.items[-KEEP_ITEMS:]

    def _paths(self):
        return os.path.join(self.data_dir, "record.json"), os.path.join(self.data_dir, "record.npz")

    def save(self):
        meta_path, img_path = self._paths()
        try:
            np.savez_compressed(img_path, *[it["img"] for it in self.items])
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"next_seq": self.next_seq,
                           "items": [{k: v for k, v in it.items() if k != "img"} for it in self.items]},
                          f, ensure_ascii=False, indent=1)
        except Exception as e:
            _log(f"Warning: could not save the record: {e}")

    def load(self):
        meta_path, img_path = self._paths()
        if not (os.path.exists(meta_path) and os.path.exists(img_path)):
            return
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            data = np.load(img_path)
            items = meta["items"]
            for k, it in enumerate(items):
                it["img"] = data[f"arr_{k}"]
            self.items, self.next_seq = items, meta.get("next_seq", len(items) + 1)
            self.catchup = bool(items)
            _log(f"loaded {len(items)} recorded messages (newest #{items[-1]['seq'] if items else '-'}): "
                 f"continuing where the bot stopped")
        except Exception as e:
            _log(f"Warning: could not load the saved record ({e}), starting fresh")
            self.items, self.next_seq = [], 1


def _overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / small if small else 0.0
