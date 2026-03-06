from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps

MAX_ICON_SIZE = 10 * 1024 * 1024  # 10MB
MAX_ICON_DIMENSION = 2048
ICON_SIZE = 256


def process_icon(image_data: bytes) -> bytes:
    """Process icon image: normalize orientation, center-crop to square, downscale to 256, output PNG.

    Args:
        image_data: Raw image bytes

    Returns:
        Processed PNG image bytes

    Raises:
        ValueError: If image is too large or invalid
    """
    if len(image_data) > MAX_ICON_SIZE:
        raise ValueError(
            f"Image file too large. Maximum size is {MAX_ICON_SIZE // (1024 * 1024)}MB"
        )

    try:
        img = Image.open(io.BytesIO(image_data))
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}") from e

    width, height = img.size
    if width > MAX_ICON_DIMENSION or height > MAX_ICON_DIMENSION:
        raise ValueError(
            f"Image dimensions too large. Maximum allowed is {MAX_ICON_DIMENSION}x{MAX_ICON_DIMENSION}"
        )

    if hasattr(img, "_getexif") and img._getexif():
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")

    size = min(img.size)
    left = (img.width - size) // 2
    top = (img.height - size) // 2
    right = left + size
    bottom = top + size
    img = img.crop((left, top, right, bottom))

    if img.width > ICON_SIZE or img.height > ICON_SIZE:
        img.thumbnail((ICON_SIZE, ICON_SIZE), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output.getvalue()


def generate_icon_filename(processed_data: bytes) -> str:
    """Generate an icon filename based on SHA1 hash of the processed image data.

    Args:
        processed_data: Processed PNG bytes

    Returns:
        Relative path like "icons/<sha1>.png"
    """
    sha1_hash = hashlib.sha1(processed_data).hexdigest()
    return f"icons/{sha1_hash}.png"


def save_icon(processed_data: bytes, rel_path: str) -> Path:
    """Save processed icon data to static storage.

    Args:
        processed_data: Processed PNG bytes
        rel_path: Relative path including icons/ prefix

    Returns:
        Absolute path to saved file
    """
    from app.config import get_static_path

    static_path = get_static_path()
    file_path = static_path / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(processed_data)
    return file_path
