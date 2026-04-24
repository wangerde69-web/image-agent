# -*- coding: utf-8 -*-
"""
Fully automated vision-based image renaming via MiniMax API.

1. Scan folder for images
2. Send each image to MiniMax vision API
3. Receive AI description → use as new filename
4. Rename files automatically

Requires:
    pip install requests Pillow
    export MINIMAX_API_KEY=your_key  (or set in env)

MiniMax API reference: https://www.minimaxi.com/document
"""

import argparse
import base64
import json
import logging
import os
import sys
import time
import re
from datetime import datetime
from pathlib import Path

# ─── Dependency check ──────────────────────────────────────────────────────────
try:
    import requests
except ImportError:
    print("ERROR: pip install requests"); sys.exit(1)
try:
    from PIL import Image
except ImportError:
    print("ERROR: pip install Pillow"); sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("auto_rename")

# ─── Config ────────────────────────────────────────────────────────────────────
# MiniMax API (used for vision analysis)
MINIMAX_BASE = os.environ.get("MINIMAX_API_BASE", "https://api.minimaxi.chat")
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "").strip()
# Fallback to the aicodee.com endpoint from tools config
if not MINIMAX_API_KEY:
    # Try the configured API key from TOOLS.md
    MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "sk-f3c39e35ded6855474b23951b6377c98").strip()

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# ─── Helpers ──────────────────────────────────────────────────────────────────
def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Make a string safe for filenames and limit length."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = name.strip(". ")
    if not name:
        name = "image"
    return name[:max_len]


def load_image_base64(path: Path) -> str | None:
    """Load an image file and return base64-encoded string (no header)."""
    try:
        with Image.open(path) as img:
            # Convert to RGB if necessary (e.g., RGBA PNG → RGB JPEG)
            if img.mode in ("RGBA", "P") and path.suffix.lower() in {".jpg", ".jpeg"}:
                img = img.convert("RGB")
            # Use JPEG for compression (reduce API payload size)
            import io
            buf = io.BytesIO()
            fmt = "JPEG" if path.suffix.lower() in {".jpg", ".jpeg", ".bmp"} else "PNG"
            img.save(buf, format=fmt, quality=85)
            img_bytes = buf.getvalue()
        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        log.warning("Failed to load image %s: %s", path.name, e)
        return None


def call_minimax_vision(image_b64: str, prompt: str = "") -> str | None:
    """
    Call MiniMax API for vision analysis.
    Returns the model's text description of the image.
    """
    if not MINIMAX_API_KEY:
        log.error("No MINIMAX_API_KEY set. Cannot call vision API.")
        log.error("  Set: $env:MINIMAX_API_KEY='your_key'")
        return None

    model = "embedded-4o-image"  # Vision-capable model on MiniMax

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            prompt or (
                                "Describe this image concisely in 2-5 words that would make a good filename. "
                                "Use lowercase letters, numbers, and underscores only. "
                                "Example: 'golden_retriever_dog.jpg' or 'mountain_sunset_landscape.jpg'. "
                                "Just output the filename description, nothing else."
                            )
                        )
                    }
                ]
            }
        ],
        "temperature": 0.3,
        "max_tokens": 50,
    }

    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{MINIMAX_BASE}/v1/text/chatcompletion_v2",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() if content else None
    except requests.exceptions.HTTPError as e:
        log.warning("MiniMax API HTTP error %d: %s", e.response.status_code, e.response.text[:200])
        return None
    except Exception as e:
        log.warning("MiniMax API call failed: %s", e)
        return None


def call_openrouter_vision(image_b64: str, prompt: str = "", model: str = "anthropic/claude-3.5-sonnet") -> str | None:
    """
    Call OpenRouter-compatible API (e.g. v2.aicodee.com) for vision.
    Works with any OpenRouter-compatible endpoint.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        api_key = os.environ.get("AICODEE_API_KEY", "sk-f3c39e35ded6855474b23951b6377c98").strip()

    base_url = os.environ.get("OPENROUTER_BASE", "https://v2.aicodee.com")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            prompt or (
                                "Describe this image in 3-6 concise English words suitable for a filename. "
                                "Use lowercase letters, numbers, underscores only. "
                                "Examples: 'golden_retriever_dog', 'mountain_sunset_landscape', 'red_sports_car'. "
                                "Output ONLY the description, nothing else."
                            )
                        )
                    }
                ]
            }
        ],
        "temperature": 0.3,
        "max_tokens": 30,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://openclaw.ai",
        "X-Title": "OpenClaw Image Agent",
    }

    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() if content else None
    except requests.exceptions.HTTPError as e:
        log.warning("Vision API HTTP error %d: %s", e.response.status_code, e.response.text[:200])
        return None
    except Exception as e:
        log.warning("Vision API call failed: %s", e)
        return None


def analyze_image_vision(image_path: Path) -> str | None:
    """
    Analyze an image using vision API and return a short description.
    Tries OpenRouter (aicodee) first, then MiniMax.
    """
    b64 = load_image_base64(image_path)
    if not b64:
        return None

    # Try OpenRouter-compatible endpoint first (aicodee.com)
    result = call_openrouter_vision(b64)
    if result:
        return result

    # Fallback to MiniMax
    result = call_minimax_vision(b64)
    return result


def safe_rename(src: Path, new_name: str) -> Path | None:
    """Rename a file, handling collisions by appending a number."""
    if new_name == src.name:
        return src

    # Ensure extension is preserved
    ext = src.suffix.lower()
    if not new_name.endswith(ext):
        new_name += ext

    new_name = sanitize_filename(new_name) + ext
    if new_name == src.name:
        return src

    dest = src.parent / new_name
    if dest.exists():
        stem = dest.stem
        i = 1
        while dest.exists():
            dest = src.parent / f"{stem}_{i}{ext}"
            i += 1

    try:
        src.rename(dest)
        return dest
    except Exception as e:
        log.warning("Rename failed: %s -> %s: %s", src.name, dest.name, e)
        return None


# ─── Main ─────────────────────────────────────────────────────────────────────
def auto_rename(folder: Path, dry_run: bool = False, delay: float = 0.5) -> dict:
    """
    Scan folder for images, analyze with vision AI, rename by content.
    Returns summary dict.
    """
    # Find images
    images = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS])
    if not images:
        log.error("No images found in %s", folder)
        return {"total": 0, "renamed": [], "failed": []}

    log.info("Found %d images in %s", len(images), folder)
    log.info("Dry run: %s", dry_run)

    renamed = []
    failed = []

    for i, img_path in enumerate(images, 1):
        log.info("[%d/%d] Analyzing: %s", i, len(images), img_path.name)

        description = analyze_image_vision(img_path)
        if not description:
            log.warning("  -> Could not analyze, skipping")
            failed.append({"path": str(img_path), "reason": "vision_failed"})
            continue

        # Clean up description: remove quotes, extra spaces, etc.
        description = re.sub(r'["\'\`\*\[\]\{\}]', "", description).strip()
        description = re.sub(r"\s+", "_", description)
        description = sanitize_filename(description)

        if not description:
            description = f"image_{i}"

        new_name = f"{description}{img_path.suffix.lower()}"
        log.info("  -> Description: %s -> %s", description, new_name)

        if dry_run:
            log.info("  [DRY RUN] Would rename: %s -> %s", img_path.name, new_name)
        else:
            new_path = safe_rename(img_path, new_name)
            if new_path:
                log.info("  [OK] Renamed: %s -> %s", img_path.name, new_path.name)
                renamed.append({"old": str(img_path), "new": str(new_path), "description": description})
            else:
                failed.append({"path": str(img_path), "reason": "rename_failed"})

        time.sleep(delay)  # Rate limiting

    summary = {
        "total": len(images),
        "renamed": renamed,
        "failed": failed,
        "dry_run": dry_run,
    }

    # Save rename log
    log_path = folder / "rename_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log.info("Rename log: %s", log_path)

    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Auto-rename images by vision AI analysis.")
    parser.add_argument("folder", help="Folder containing images")
    parser.add_argument("--dry-run", action="store_true", help="Preview without renaming")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds)")
    parser.add_argument("--api-key", help="Override API key (or set MINIMAX_API_KEY / OPENROUTER_API_KEY)")
    args = parser.parse_args()

    if args.api_key:
        os.environ["OPENROUTER_API_KEY"] = args.api_key

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory")
        sys.exit(1)

    result = auto_rename(folder, dry_run=args.dry_run, delay=args.delay)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Summary:")
    print(f"  Total images: {result['total']}")
    print(f"  Renamed: {len(result['renamed'])}")
    print(f"  Failed: {len(result['failed'])}")
    if result['failed']:
        print(f"  Failed items:")
        for item in result['failed']:
            print(f"    - {Path(item['path']).name}: {item['reason']}")


if __name__ == "__main__":
    main()
