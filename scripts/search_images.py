#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

"""
Image search and download tool.

Search sources (in priority order):
  1. Bing Images      — Works in China, no key, up to 100+ results per page
  2. Unsplash API     — High quality, needs free API key
  3. Pexels API       — High quality, needs free API key
  4. Sogou Images     — Works in China, no key (alternative)
  5. Wikipedia        — International, no key, often blocked in China
"""

import argparse
import os
import sys
import json
import time
import re
from pathlib import Path
from urllib.parse import quote, urlparse, unquote

# ─── External dependencies ──────────────────────────────────────────────────────
try:
    import requests
except ImportError:
    print("ERROR: `requests` not installed. Run: pip install requests")
    sys.exit(1)

# ─── Constants ────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://image.baidu.com/",
}
TIMEOUT = 15


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'[\x00-\x1f]', '', name)
    return name.strip() or "untitled"


def slugify(query: str) -> str:
    """Convert a search query into a safe directory name."""
    return sanitize_filename(query.lower().replace(" ", "_")[:60])


# ─── Source 1: Bing Images (primary — works in China, no key) ─────────────────
def search_bing_images(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Bing Images via the HTML async endpoint.
    Works reliably from China, returns 100+ image URLs per page.
    """
    results = []
    seen_urls = set()
    per_page = 50
    pages_needed = max(1, (max_results + per_page - 1) // per_page)

    for page in range(pages_needed):
        offset = page * per_page
        url = (
            f"https://cn.bing.com/images/async"
            f"?q={quote(query)}&first={offset}&count={per_page}"
        )
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"  [Bing] Page {page+1} error: {e}")
            continue

        # Extract mediaurl=... patterns (URL-encoded)
        raw_urls = re.findall(r"mediaurl=(https?[^&\"<\s]+)", html)

        for raw in raw_urls:
            # Decode URL (may be double-encoded)
            img_url = unquote(unquote(raw))
            if img_url in seen_urls or not img_url.startswith("http"):
                continue
            seen_urls.add(img_url)
            results.append({
                "url": img_url,
                "title": f"bing_{len(results)}",
                "source": "bing_images",
                "license": "unknown",
            })
            if len(results) >= max_results:
                break

        if len(results) >= max_results:
            break
        time.sleep(0.3)

    print(f"  [Bing Images] found {len(results)} images")
    return results[:max_results]


# ─── Source 2: Sogou Images (works in China, no key) ─────────────────────────
def search_sogou_images(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Sogou Images via their JSON API.
    """
    query_encoded = quote(query)
    url = (
        f"https://pic.sogou.com/pics/json.jsp"
        f"?query={query_encoded}&st=5&start=0&xml_len={max_results}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Sogou] API error: {e}")
        return []

    items = data.get("items", [])
    results = []
    seen = set()
    for item in items:
        img_url = item.get("thumbUrl") or item.get("pic_url", "")
        if not img_url or img_url in seen:
            continue
        seen.add(img_url)
        results.append({
            "url": img_url,
            "title": item.get("title", f"sogou_{len(results)}"),
            "source": "sogou_images",
            "license": "unknown",
        })

    print(f"  [Sogou Images] found {len(results)} images")
    return results[:max_results]


# ─── Source 3: Unsplash API (high quality, requires free key) ────────────────
def search_unsplash(query: str, max_results: int = 20) -> list[dict]:
    """Search Unsplash via their free API. Requires UNSPLASH_ACCESS_KEY env var."""
    api_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not api_key:
        print("  [Unsplash] No API key (set UNSPLASH_ACCESS_KEY to enable)")
        return []

    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": min(max_results, 30), "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {api_key}", "Accept-Version": "v1"},
            timeout=TIMEOUT
        )
        if resp.status_code == 401:
            print("  [Unsplash] Invalid API key")
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Unsplash] API error: {e}")
        return []

    results = []
    for photo in data.get("results", []):
        urls = photo.get("urls", {})
        results.append({
            "url": urls.get("regular") or urls.get("full", ""),
            "title": f"unsplash_{photo.get('id', 'unk')}",
            "source": "unsplash",
            "license": "Unsplash License",
            "attribution": photo.get("user", {}).get("name", ""),
        })

    print(f"  [Unsplash] found {len(results)} images")
    return results[:max_results]


# ─── Source 4: Pexels API (high quality, requires free key) ───────────────────
def search_pexels(query: str, max_results: int = 20) -> list[dict]:
    """Search Pexels via their API. Requires PEXELS_API_KEY env var."""
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        print("  [Pexels] No API key (set PEXELS_API_KEY to enable)")
        return []

    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": min(max_results, 30), "orientation": "landscape"},
            headers={"Authorization": api_key},
            timeout=TIMEOUT
        )
        if resp.status_code == 401:
            print("  [Pexels] Invalid API key")
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Pexels] API error: {e}")
        return []

    results = []
    for photo in data.get("photos", []):
        src = photo.get("src", {})
        results.append({
            "url": src.get("large") or src.get("original", ""),
            "title": f"pexels_{photo.get('id', 'unk')}",
            "source": "pexels",
            "license": "Pexels License",
            "attribution": photo.get("photographer", ""),
        })

    print(f"  [Pexels] found {len(results)} images")
    return results[:max_results]


# ─── Source 5: Wikipedia Commons (no key, often blocked in China) ─────────────
def search_wikipedia_commons(query: str, max_results: int = 20) -> list[dict]:
    """Search Wikimedia Commons via the API (fallback source)."""
    try:
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "srnamespace": 6, "srlimit": max_results * 2, "format": "json"},
            headers=HEADERS, timeout=TIMEOUT
        )
        resp.raise_for_status()
        titles = [r["title"] for r in resp.json().get("query", {}).get("search", [])]
    except Exception as e:
        print(f"  [Wikipedia] API error: {e}")
        return []

    if not titles:
        return []

    try:
        resp2 = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={"action": "query", "titles": " | ".join(titles),
                    "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 800,
                    "format": "json"},
            headers=HEADERS, timeout=TIMEOUT
        )
        resp2.raise_for_status()
        pages = resp2.json().get("query", {}).get("pages", {})
    except Exception as e:
        print(f"  [Wikipedia] file info error: {e}")
        return []

    results = []
    for page in pages.values():
        if page.get("missing"):
            continue
        info = page.get("imageinfo", [{}])[0]
        url = info.get("thumburl") or info.get("url", "")
        mime = info.get("mime", "")
        if url and "image" in mime:
            results.append({
                "url": url, "title": page.get("title", "unknown"),
                "source": "wikimedia_commons", "license": "CC",
            })

    print(f"  [Wikipedia Commons] found {len(results)} images")
    return results[:max_results]


# ─── Download a single image ──────────────────────────────────────────────────
def download_image(item: dict, output_dir: Path, index: int) -> Path | None:
    """Download one image URL to output_dir. Returns the saved Path or None."""
    url = item["url"]
    ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
    if len(ext) > 5:
        ext = ".jpg"
    filename = f"img_{index:03d}{ext}"
    filepath = output_dir / filename

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size = filepath.stat().st_size
        if size < 5000:
            filepath.unlink()
            return None
        item["local_path"] = str(filepath)
        return filepath
    except Exception as e:
        print(f"  [Download] Failed: {url[:60]}... - {e}")
        return None


# ─── Main search + download ───────────────────────────────────────────────────
def search_and_download(query: str, max_results: int = 20,
                         output_dir: str = "./downloads") -> list[dict]:
    """
    Search all sources, download up to max_results, return list of downloaded items.
    Source order (for Chinese network): Baidu -> Sogou -> Unsplash -> Pexels -> Wikipedia
    """
    output_path = Path(output_dir) / slugify(query)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\n[SEARCH] Query: '{query}' (max {max_results})")
    print(f"[OUTPUT] {output_path}\n")

    all_results = []

    # 1. Bing Images (primary for China)
    print("[1/5] Bing Images...")
    all_results.extend(search_bing_images(query, max_results))

    # 2. Sogou Images (secondary for China)
    print("[2/5] Sogou Images...")
    all_results.extend(search_sogou_images(query, max_results))

    # 3. Unsplash (high quality, international)
    if os.environ.get("UNSPLASH_ACCESS_KEY"):
        print("[3/5] Unsplash...")
        all_results.extend(search_unsplash(query, max_results))
    else:
        print("[3/5] Unsplash... (skip - set UNSPLASH_ACCESS_KEY)")

    # 4. Pexels (high quality, international)
    if os.environ.get("PEXELS_API_KEY"):
        print("[4/5] Pexels...")
        all_results.extend(search_pexels(query, max_results))
    else:
        print("[4/5] Pexels... (skip - set PEXELS_API_KEY)")

    # 5. Wikipedia (fallback)
    print("[5/5] Wikipedia Commons (fallback)...")
    all_results.extend(search_wikipedia_commons(query, max_results))

    # Deduplicate
    seen_urls = set()
    unique_results = []
    for item in all_results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_results.append(item)

    print(f"\n[TOTAL] Unique images to download: {len(unique_results)}")
    if not unique_results:
        print("[ERROR] No images found from any source.")
        return []

    # Download
    downloaded = []
    for i, item in enumerate(unique_results[:max_results], 1):
        src = item["source"]
        url_short = item["url"][:70]
        print(f"  [{i}/{min(len(unique_results), max_results)}] {src}: {url_short}...")
        path = download_image(item, output_path, i)
        if path:
            downloaded.append(item)
            print(f"    [OK] {path.name} ({path.stat().st_size // 1024}KB)")
        time.sleep(0.25)

    # Save manifest
    manifest_path = output_path / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "query": query, "total_downloaded": len(downloaded),
            "items": downloaded,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] Downloaded {len(downloaded)} images -> {output_path}")
    print(f"[INFO] Manifest: {manifest_path}")
    return downloaded


# ─── CLI entry point ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Search and download images.")
    parser.add_argument("query", help="Search query (e.g. 'gym treadmill')")
    parser.add_argument("--max", type=int, default=20, help="Max images (default: 20)")
    parser.add_argument("--output", "-o", default="./downloads", help="Output dir (default: ./downloads)")
    parser.add_argument("--auto-rename", action="store_true", help="Also run vision rename")
    args = parser.parse_args()

    downloaded = search_and_download(args.query, max_results=args.max, output_dir=args.output)

    if args.auto_rename and downloaded:
        print("\n[NEXT] Run vision rename:")
        print(f"  python scripts/rename_by_vision.py {Path(args.output) / slugify(args.query)}")


if __name__ == "__main__":
    main()
