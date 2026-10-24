#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Position icon recognition with a multimodal LLM.

Replaces OpenCV template matching for the small (~20-28px) position icons shown
next to a player's name in chat. Edge aliasing / scaling makes template matching
unreliable, so the cropped name-row region is sent to a vision LLM together with a
labelled reference sheet built from templates/positions/*.png.

Supported providers:
- "anthropic": Anthropic Messages API (default model: claude-haiku-5-5)
- "openai":    OpenAI or any OpenAI-compatible Chat Completions endpoint

Usage (standalone test): see tools/test_position_vision.py
"""

import base64
import io
import json
import os
import re
import time
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "positions")

# Position name -> icon template file. Names match the keys used by remove_user_position().
POSITION_ICON_FILES = {
    "ADMINISTRATOR": "administrator.png",
    "DEVELOPMENT": "development.png",
    "INTERIOR": "interior.png",
    "MILITARY": "military.png",
    "SCIENCE": "science.png",
    "SECURITY": "security.png",
    "STRATEGY": "strategy.png",
}
POSITION_NAMES = list(POSITION_ICON_FILES.keys())
NO_POSITION = "NONE"

# Visual descriptions written from the actual template images.
# The pairs most likely to be confused are called out explicitly.
POSITION_DESCRIPTIONS = {
    "ADMINISTRATOR": "a vertical BLUE card/plaque with a GOLD border and a single RED GEM in the middle (no star).",
    "DEVELOPMENT": "a crossed GREY HAMMER and WRENCH; the hammer has an ORANGE/wooden handle. No frame, no blue, no red.",
    "INTERIOR": "a closed RED BOOK seen from the front, with a WHITE label strip near the top and a small YELLOW bookmark at the bottom.",
    "MILITARY": "two crossed SILVER SWORDS forming an X over a GOLD/ORANGE laurel-like background.",
    "SCIENCE": "a LIGHT-BLUE glass laboratory FLASK (cone-shaped bottle with a narrow neck).",
    "SECURITY": "a square-ish GOLD SHIELD/badge with a RED STAR (white-outlined) in the centre.",
    "STRATEGY": "an officer's PEAKED CAP: white/light top, NAVY-BLUE band and visor, with a small GOLD STAR on the front.",
}

# On-screen icons are upscaled by this factor before being sent; the reference sheet
# uses the same factor so the model compares objects at the same apparent size.
UPSCALE = 4
MAX_IMAGE_SIDE = 1500

SYSTEM_PROMPT = """You are a strict visual classifier for the mobile game "Last War: Survival".
Your ONLY job: decide which government position icon (if any) appears in a screenshot crop of the chat name row.

Image 1 is the REFERENCE SHEET. Each row shows one position: its NAME on the left, then the same icon
rendered three times (clean, slightly blurred, slightly shrunk) because in-game the icon is tiny
(about 20-28 pixels) and its edges look different every time due to scaling and anti-aliasing.

Image 2 is the CROP from the live chat, enlarged 4x. It is the strip just above a chat bubble and may contain:
- the player's NAME text and an alliance tag like [ABC] (ignore text, never read it as an icon),
- the top part of the player's square AVATAR portrait at the far left (ignore it; it is a large picture, not a position icon),
- parts of other UI or the previous message (ignore).
A position icon, if present, is a SMALL standalone emblem sitting in the name row, usually right next to the name.

Position icons:
{descriptions}

Rules:
- Judge by overall SHAPE and COLOUR, not by exact edges. Blurry or jagged edges are normal.
- SECURITY vs STRATEGY: both have a star. SECURITY = red star on a gold shield. STRATEGY = gold star on a white/navy cap.
- ADMINISTRATOR vs SECURITY: both have gold and red. ADMINISTRATOR = blue card with a red gem. SECURITY = gold shield with a red star.
- If no small emblem matching one of the seven icons is visible, answer NONE. Do not guess from the avatar or the name.

Reply with JSON only: {{"observed": "<a few words describing the small emblem you see, or 'none'>", "position": "<one of {names} or NONE>"}}"""

USER_PROMPT = "Image 1 = reference sheet, Image 2 = live chat crop. Which position icon is in Image 2?"


def _load_font(size: int):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _upscale(img: Image.Image, factor: float) -> Image.Image:
    w, h = img.size
    return img.resize((max(1, int(w * factor)), max(1, int(h * factor))), Image.BICUBIC)


def prepare_crop(crop: Image.Image) -> Image.Image:
    """Enlarge the live crop the same way the reference icons are enlarged."""
    crop = crop.convert("RGB")
    factor = min(UPSCALE, MAX_IMAGE_SIDE / max(crop.size))
    return _upscale(crop, factor)


def build_reference_sheet(template_dir: str = TEMPLATE_DIR) -> Image.Image:
    """Build a labelled reference sheet: one row per position, three renderings per icon."""
    icons = {}
    for name, filename in POSITION_ICON_FILES.items():
        path = os.path.join(template_dir, filename)
        icons[name] = Image.open(path).convert("RGB")

    cell = max(max(i.size) for i in icons.values()) * UPSCALE + 16
    label_w = 300
    pad = 10
    font = _load_font(30)
    # Chat background colour, sampled from a template corner
    bg = icons["DEVELOPMENT"].getpixel((0, 0))

    width = label_w + 3 * (cell + pad) + pad
    height = len(icons) * (cell + pad) + pad
    sheet = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(sheet)

    for row, (name, icon) in enumerate(icons.items()):
        y = pad + row * (cell + pad)
        draw.rectangle([0, y - pad // 2, width, y + cell + pad // 2 - 1], outline=(150, 150, 150))
        draw.text((pad, y + cell // 2), name, fill=(0, 0, 0), font=font, anchor="lm")

        w, h = icon.size
        variants = [
            _upscale(icon, UPSCALE),
            _upscale(icon.filter(ImageFilter.GaussianBlur(0.6)), UPSCALE),
            _upscale(icon.resize((max(1, int(w * 0.8)), max(1, int(h * 0.8))), Image.BILINEAR), UPSCALE),
        ]
        for col, v in enumerate(variants):
            x = label_w + pad + col * (cell + pad)
            sheet.paste(v, (x + (cell - v.width) // 2, y + (cell - v.height) // 2))
    return sheet


def _png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def parse_position_answer(text: str) -> Optional[str]:
    """Return a position name, NO_POSITION, or None if the answer can't be understood."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            value = str(json.loads(match.group(0)).get("position", "")).strip().upper()
            if value in POSITION_NAMES or value == NO_POSITION:
                return value
        except (json.JSONDecodeError, AttributeError):
            pass
    # Fallback: exactly one known name mentioned in free text
    upper = text.upper()
    found = [n for n in POSITION_NAMES if re.search(rf"\b{n}\b", upper)]
    if len(found) == 1:
        return found[0]
    if not found and re.search(r"\bNONE\b", upper):
        return NO_POSITION
    return None


class PositionVisionRecognizer:
    """Classifies a chat name-row crop into one of the seven positions (or NONE)."""

    def __init__(self, provider: str = "anthropic", model: str = "claude-haiku-5-5",
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 timeout: float = 4.0):
        self.provider = (provider or "anthropic").lower()
        self.model = model
        self.timeout = timeout
        self.system_prompt = SYSTEM_PROMPT.format(
            descriptions="\n".join(f"- {n}: {d}" for n, d in POSITION_DESCRIPTIONS.items()),
            names=", ".join(POSITION_NAMES),
        )
        self.reference_b64 = _png_b64(build_reference_sheet())

        if self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key or None, base_url=base_url or None,
                                              timeout=timeout, max_retries=1)
        elif self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key or None, base_url=base_url or None,
                                 timeout=timeout, max_retries=1)
        else:
            raise ValueError(f"Unknown position vision provider: {provider}")

    def _call_anthropic(self, crop_b64: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.system_prompt,
            output_config={
                "effort": "low",
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "observed": {"type": "string"},
                            "position": {"type": "string", "enum": POSITION_NAMES + [NO_POSITION]},
                        },
                        "required": ["observed", "position"],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": self.reference_b64}},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": crop_b64}},
                    {"type": "text", "text": USER_PROMPT},
                ],
            }],
        )
        if response.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in response.content if b.type == "text")

    def _call_openai(self, crop_b64: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{self.reference_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{crop_b64}"}},
                    {"type": "text", "text": USER_PROMPT},
                ]},
            ],
        )
        return response.choices[0].message.content or ""

    def recognize(self, crop: Image.Image) -> Dict[str, Any]:
        """
        Returns:
            {'position': <name> | 'NONE', 'raw': str, 'latency': float} on success
            {'error': <message>, 'raw': str, 'latency': float} on API / parse failure
        """
        start = time.time()
        raw = ""
        try:
            crop_b64 = _png_b64(prepare_crop(crop))
            if self.provider == "anthropic":
                raw = self._call_anthropic(crop_b64)
            else:
                raw = self._call_openai(crop_b64)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "raw": raw, "latency": time.time() - start}

        position = parse_position_answer(raw)
        if position is None:
            return {"error": "unparseable answer", "raw": raw, "latency": time.time() - start}
        return {"position": position, "raw": raw, "latency": time.time() - start}


def create_recognizer_from_config(config_module) -> PositionVisionRecognizer:
    """Build a recognizer from config.py values (generated by Setup.py)."""
    provider = getattr(config_module, "POSITION_VISION_PROVIDER", "anthropic")
    model = getattr(config_module, "POSITION_VISION_MODEL", "claude-haiku-5-5")
    base_url = getattr(config_module, "POSITION_VISION_BASE_URL", "") or None
    timeout = float(getattr(config_module, "POSITION_VISION_TIMEOUT", 4.0))
    api_key = getattr(config_module, "POSITION_VISION_API_KEY", None)
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY") if provider == "anthropic" else os.getenv("OPENAI_API_KEY")
    return PositionVisionRecognizer(provider=provider, model=model, api_key=api_key,
                                    base_url=base_url, timeout=timeout)
