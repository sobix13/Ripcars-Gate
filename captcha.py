"""Pure CAPTCHA generation and verification for Ripcars Gate."""

from __future__ import annotations

import hashlib
import hmac
import io
import secrets
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
DEFAULT_LENGTH = 6
MIN_LENGTH = 4
MAX_LENGTH = 8


@dataclass(frozen=True)
class Challenge:
    answer: str
    salt: str
    digest: str
    png: bytes


def normalize(value: str) -> str:
    return "".join(ch for ch in (value or "").upper().strip() if ch.isalnum())


def make_digest(answer: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{normalize(answer)}".encode()).hexdigest()


def verify(answer: str, salt: str, expected: str) -> bool:
    return hmac.compare_digest(make_digest(answer, salt), expected or "")


def generate_answer(length: int = DEFAULT_LENGTH) -> str:
    length = max(MIN_LENGTH, min(MAX_LENGTH, int(length)))
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def render(answer: str, width: int = 520, height: int = 180) -> bytes:
    answer = normalize(answer)
    image = Image.new("RGB", (width, height), (25, 9, 16))
    draw = ImageDraw.Draw(image)
    for _ in range(18):
        x1, y1 = secrets.randbelow(width), secrets.randbelow(height)
        x2, y2 = secrets.randbelow(width), secrets.randbelow(height)
        color = (30 + secrets.randbelow(55), 55 + secrets.randbelow(80),
                 35 + secrets.randbelow(65))
        draw.line((x1, y1, x2, y2), fill=color, width=1 + secrets.randbelow(3))

    font = _font(82)
    cell = width / max(1, len(answer))
    for index, char in enumerate(answer):
        layer = Image.new("RGBA", (110, 130), (0, 0, 0, 0))
        pen = ImageDraw.Draw(layer)
        color = (235 + secrets.randbelow(21), 165 + secrets.randbelow(61), 185 + secrets.randbelow(51), 255)
        pen.text((18, 7), char, font=font, fill=color, stroke_width=1,
                 stroke_fill=(20, 30, 44, 255))
        layer = layer.rotate(secrets.randbelow(25) - 12,
                             resample=Image.Resampling.BICUBIC, expand=False)
        x = int(index * cell + cell / 2 - layer.width / 2)
        image.paste(layer, (x, 22 + secrets.randbelow(20)), layer)

    pixels = image.load()
    for _ in range(width * height // 28):
        x, y = secrets.randbelow(width), secrets.randbelow(height)
        shade = 80 + secrets.randbelow(150)
        pixels[x, y] = (shade, shade // 3, shade // 2)
    image = image.filter(ImageFilter.GaussianBlur(0.35))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def create(length: int = DEFAULT_LENGTH) -> Challenge:
    answer = generate_answer(length)
    salt = secrets.token_hex(16)
    return Challenge(answer, salt, make_digest(answer, salt), render(answer))
