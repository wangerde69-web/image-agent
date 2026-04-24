# -*- coding: utf-8 -*-
"""
Image search and download with query expansion + perceptual hash deduplication.

Enhancements over basic search:
- Multi-variation query expansion (synonyms, related terms, plural forms)
- Perceptual hash (imagehash) deduplication — catches same image from different domains
- Multiple search engines: Bing, Google Images (serpapi), Sogou, Unsplash, Pexels, Flickr
- Size/color filters for diversity
- Parallel downloads with rate limiting
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlparse, unquote

# ─── Dependencies ────────────────────────────────────────────────────────────────
# pip install requests imagehash Pillow
MISSING_DEPS = []
try:
    import requests
except ImportError:
    MISSING_DEPS.append("requests")
try:
    import imagehash
except ImportError:
    MISSING_DEPS.append("imagehash")
try:
    from PIL import Image
except ImportError:
    MISSING_DEPS.append("Pillow")

if MISSING_DEPS:
    print(f"ERROR: Missing packages: {', '.join(MISSING_DEPS)}")
    print(f"  Run: pip install requests imagehash Pillow")
    sys.exit(1)

# ─── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("img_search")

# ─── Constants ────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}
TIMEOUT = 15

# ─── Query Expansion ─────────────────────────────────────────────────────────
# These word→expansion mappings broaden search coverage
_QUERY_VARIATIONS = {
    "gym": ["fitness", "workout", "exercise", "training"],
    "treadmill": ["running machine", "cardio machine", "indoor running"],
    "fitness": ["gym", "workout", "exercise", "training", "health"],
    "food": ["dish", "meal", "cuisine", "recipe", "cooking"],
    "car": ["vehicle", "automobile", "sedan", "suv"],
    "dog": ["puppy", "canine", "pet", "dog breed"],
    "cat": ["kitten", "feline", "pet", "cat breed"],
    "laptop": ["notebook computer", "portable PC", "macbook"],
    "phone": ["smartphone", "mobile phone", "cellphone"],
    "shoes": ["footwear", "sneakers", "athletic shoes", "boots"],
    "watch": ["wristwatch", "timepiece", "smartwatch"],
    "headphone": ["headset", "earphone", "audio", "earbuds"],
    "bike": ["bicycle", "cycling", "road bike", "mtb"],
    "book": ["ebook", "novel", "publication", "reading"],
    "music": ["song", "album", "audio", "playlist"],
    "art": ["painting", "artwork", "illustration", "drawing"],
    "photo": ["photograph", "picture", "image", "snapshot"],
    "video": ["clip", " footage", "recording", "movie"],
    "design": ["graphic", "visual", "artwork", "layout"],
    "nature": ["landscape", "outdoor", "scenery", "wilderness"],
    "city": ["urban", "metropolitan", "downtown", "street"],
    "beach": ["coast", "seaside", "ocean", "shoreline"],
    "mountain": ["alpine", "peak", "hiking", "hill"],
    "animal": ["wildlife", "creature", "fauna", "mammal"],
    "bird": ["avian", "feathered", "birdwatching", "poultry"],
    "flower": ["bloom", "blossom", "plant", "garden"],
    "tree": ["forest", "wood", "nature", "plant"],
    "tech": ["technology", "digital", "gadget", "innovation"],
    "business": ["office", "corporate", "professional", "work"],
    "sport": ["athlete", "competition", "game", "match"],
}

# ─── Helpers ──────────────────────────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"[\x00-\x1f]", "", name)
    return name.strip() or "untitled"


def slugify(query: str) -> str:
    return sanitize_filename(query.lower().replace(" ", "_")[:60])


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Image Deduplication via Perceptual Hash ───────────────────────────────────
class ImageDeduper:
    """
    Deduplicate images using perceptual hash (pHash).
    Catches images that are:
    - Same content, different compression/formats
    - Resized/re-cropped versions
    - Slightly edited variants
    """

    def __init__(self, hash_size: int = 8, max_hamming: int = 8):
        self.hash_size = hash_size
        self.max_hamming = max_hamming
        self.seen_hashes: dict[str, str] = {}  # hash → first_url

    def is_duplicate(self, image_path: Path) -> tuple[bool, str | None]:
        """Return (is_dup, original_url)"""
        try:
            img_hash = imagehash.phash(Image.open(image_path), hash_size=self.hash_size)
            h_str = str(img_hash)
            for stored_hash, first_url in self.seen_hashes.items():
                hamming = img_hash - imagehash.hex_to_hash(stored_hash)
                if hamming <= self.max_hamming:
                    return True, first_url
            self.seen_hashes[h_str] = str(image_path)
            return False, None
        except Exception:
            return False, None


# ─── Download ─────────────────────────────────────────────────────────────────
def download_image(url: str, filepath: Path, referer: str = "") -> bool:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        content_length = resp.headers.get("content-length", 0)
        if content_length and int(content_length) < 5000:
            return False
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return filepath.stat().st_size >= 5000
    except Exception as e:
        log.debug("Download failed: %s — %s", url[:60], e)
        return False


# ─── Bing Images (enhanced with filters + multi-page) ────────────────────────
def search_bing_images(query: str, max_results: int = 20, size_filter: str = "Large") -> list[dict]:
    """
    Search Bing Images with size filter and deep pagination.
    size_filter: "Small", "Medium", "Large", "Wallpaper"
    """
    results = []
    seen_urls = set()
    per_page = 50

    # Add size filter to query if specified
    size_abd = f" filterui:imagesize-{size_filter.upper().replace(' ', '')}"

    # Also try different page positions for diversity
    offsets = list(range(0, min(max_results * 3, 200), per_page))

    for offset in offsets:
        if len(results) >= max_results:
            break
        url = (
            f"https://www.bing.com/images/async"
            f"?q={quote(query + size_abd)}&first={offset}&count={per_page}"
            f"&mmos=1&mkt=en-US"
        )
        try:
            resp = requests.get(
                url,
                headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            log.warning("[Bing] Page offset=%d error: %s", offset, e)
            continue

        raw_urls = re.findall(r"mediaurl=(https?[^&" + chr(34) + r"\s]+)", html, re.UNICODE)
        for raw in raw_urls:
            img_url = unquote(raw)
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

        time.sleep(0.4)

    log.info("[Bing Images] found %d unique URLs", len(results))
    return results[:max_results]


# ─── Google Images via SerpAPI (optional — needs free API key) ───────────────
def search_google_images_serpapi(query: str, max_results: int = 20) -> list[dict]:
    """Search Google Images via SerpAPI (free tier: 100 searches/month)."""
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        log.info("[Google/SerpAPI] No API key (set SERPAPI_KEY to enable)")
        return []

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "tbm": "isch",
                "num": min(max_results, 100),
                "api_key": api_key,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("[Google/SerpAPI] error: %s", e)
        return []

    results = []
    seen = set()
    for item in data.get("images_results", [])[:max_results]:
        img_url = item.get("original") or item.get("source", {}).get("link", "")
        if not img_url or img_url in seen:
            continue
        seen.add(img_url)
        results.append({
            "url": img_url,
            "title": item.get("title", f"google_{len(results)}"),
            "source": "google_images",
            "license": "unknown",
        })

    log.info("[Google Images/SerpAPI] found %d images", len(results))
    return results


# ─── Sogou Images ────────────────────────────────────────────────────────────
def search_sogou_images(query: str, max_results: int = 20) -> list[dict]:
    try:
        resp = requests.get(
            f"https://pic.sogou.com/pics/json.jsp"
            f"?query={quote(query)}&st=5&start=0&xml_len={max_results}",
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("[Sogou] error: %s", e)
        return []

    results = []
    seen = set()
    for item in data.get("items", []):
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
    log.info("[Sogou Images] found %d images", len(results))
    return results


# ─── Unsplash API ─────────────────────────────────────────────────────────────
def search_unsplash(query: str, max_results: int = 20) -> list[dict]:
    api_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not api_key:
        return []
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": min(max_results, 30)},
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 401:
            log.warning("[Unsplash] Invalid API key")
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("[Unsplash] error: %s", e)
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
    log.info("[Unsplash] found %d images", len(results))
    return results


# ─── Pexels API ───────────────────────────────────────────────────────────────
def search_pexels(query: str, max_results: int = 20) -> list[dict]:
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": min(max_results, 30)},
            headers={"Authorization": api_key},
            timeout=TIMEOUT,
        )
        if resp.status_code == 401:
            log.warning("[Pexels] Invalid API key")
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("[Pexels] error: %s", e)
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
    log.info("[Pexels] found %d images", len(results))
    return results


# ─── Flickr (CC-licensed) ──────────────────────────────────────────────────────
def search_flickr_cc(query: str, max_results: int = 20) -> list[dict]:
    """Search Flickr for Creative Commons licensed images via their API."""
    try:
        resp = requests.get(
            "https://www.flickr.com/services/rest/",
            params={
                "method": "flickr.photos.search",
                "api_key": os.environ.get("FLICKR_API_KEY", "dummy"),
                "text": query,
                "license": "1,2,3,4,5,6,7,9,10",  # CC licenses
                "per_page": min(max_results, 50),
                "format": "json",
                "nojsoncallback": 1,
                "media": "photos",
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug("[Flickr] error: %s", e)
        return []

    results = []
    seen = set()
    for photo in data.get("photos", {}).get("photo", []):
        farm = photo.get("farm", 0)
        server = photo.get("server", "")
        pid = photo.get("id", "")
        secret = photo.get("secret", "")
        if not all([farm, server, pid, secret]):
            continue
        img_url = (
            f"https://farm{farm}.staticflickr.com/{server}/{pid}_{secret}_z.jpg"
        )
        if img_url in seen:
            continue
        seen.add(img_url)
        results.append({
            "url": img_url,
            "title": photo.get("title", f"flickr_{len(results)}"),
            "source": "flickr_cc",
            "license": "CC",
            "attribution": photo.get("ownername", ""),
        })
    log.info("[Flickr CC] found %d images", len(results))
    return results


# ─── Query Expansion ───────────────────────────────────────────────────────────
def expand_queries(base_query: str, max_variations: int = 5) -> list[str]:
    """
    Generate query variations to broaden search coverage.
    Combines the original query with synonyms and related terms.
    """
    queries = [base_query]
    query_lower = base_query.lower()

    # Extract key terms
    terms = re.findall(r"[a-z]+", query_lower)

    # Add variations based on known synonym groups
    for term in terms:
        if term in _QUERY_VARIATIONS:
            for syn in _QUERY_VARIATIONS[term][:2]:  # Limit to 2 per term
                variation = query_lower.replace(term, syn)
                if variation != query_lower and variation not in queries:
                    queries.append(variation)

    # Also try with common modifiers
    modifiers = ["high quality", "4k", "photo", "real", "actual"]
    for mod in modifiers:
        if mod not in query_lower:
            queries.append(f"{mod} {base_query}")

    return queries[:max_variations]


# ─── Main Search + Download ───────────────────────────────────────────────────
def search_and_download(
    query: str,
    max_results: int = 20,
    output_dir: str = "./downloads",
    size_filter: str = "Large",
    enable_expansion: bool = True,
) -> dict:
    output_path = Path(output_dir) / slugify(query)
    output_path.mkdir(parents=True, exist_ok=True)

    log.info("Query: '%s' (max=%d, size=%s)", query, max_results, size_filter)
    log.info("Output: %s", output_path)

    all_results = []

    # ── Query Expansion ──────────────────────────────────────────────────────
    if enable_expansion:
        queries = expand_queries(query, max_variations=5)
        log.info("Query expansion: %s", queries)
    else:
        queries = [query]

    # ── Search each engine with each query variation ─────────────────────────
    for q in queries:
        if len(all_results) >= max_results * 2:  # Enough results, stop expanding
            break

        # 1. Bing (always)
        Bing_size = size_filter if q == query else "Medium"  # Full size only for main query
        all_results.extend(search_bing_images(q, max_results // 2, Bing_size))

        # 2. Sogou
        all_results.extend(search_sogou_images(q, max_results // 4))

        time.sleep(0.3)

    # 3. Unsplash (high quality, no expansion needed)
    all_results.extend(search_unsplash(query, max_results // 2))

    # 4. Pexels
    all_results.extend(search_pexels(query, max_results // 2))

    # 5. SerpAPI Google (if key available)
    all_results.extend(search_google_images_serpapi(query, max_results // 2))

    # 6. Flickr CC
    all_results.extend(search_flickr_cc(query, max_results // 4))

    # ── Deduplicate by URL ───────────────────────────────────────────────────
    seen_urls = set()
    unique_results = []
    for item in all_results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_results.append(item)

    log.info("Total unique URLs: %d (from %d raw)", len(unique_results), len(all_results))
    if not unique_results:
        log.error("No images found from any source!")
        return {"query": query, "downloaded": [], "deduped_hashes": [], "output_dir": str(output_path)}

    # ── Download with perceptual hash deduplication ──────────────────────────
    deduper = ImageDeduper(hash_size=8, max_hamming=8)
    downloaded = []
    deduped_hashes = []

    for i, item in enumerate(unique_results[:max_results], 1):
        url_short = item["url"][:70]
        log.info("[%d/%d] %s: %s", i, min(len(unique_results), max_results), item["source"], url_short)

        ext = os.path.splitext(urlparse(item["url"]).path)[1] or ".jpg"
        if len(ext) > 5:
            ext = ".jpg"
        filename = f"img_{i:03d}{ext}"
        filepath = output_path / filename

        # Check URL-domain dedup BEFORE downloading (fast)
        # perceptual hash check happens after download to catch same image from different domains
        ok = download_image(item["url"], filepath)
        if not ok:
            log.debug("  -> download failed, skipping")
            continue

        # Perceptual hash dedup — skip if visually identical to already-downloaded
        is_dup, _ = deduper.is_duplicate(filepath)
        if is_dup:
            log.info("  -> perceptually duplicate, skipping")
            filepath.unlink(missing_ok=True)
            continue

        item["local_path"] = str(filepath)
        item["local_filename"] = filename
        downloaded.append(item)
        deduped_hashes.append(str(filepath))
        log.info("  -> saved: %s (%.1f KB)", filename, filepath.stat().st_size / 1024)
        time.sleep(0.2)

    # ── Save manifest ─────────────────────────────────────────────────────────
    manifest = {
        "query": query,
        "total_downloaded": len(downloaded),
        "output_dir": str(output_path),
        "images": downloaded,
    }
    manifest_path = output_path / "manifest.json"
    save_json(str(manifest_path), manifest)

    log.info("DONE: %d images -> %s", len(downloaded), output_path)
    log.info("Manifest: %s", manifest_path)

    return manifest


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Enhanced image search + download with query expansion and perceptual dedup.")
    parser.add_argument("query", help="Search query (e.g. 'gym treadmill')")
    parser.add_argument("--max", type=int, default=20, help="Max images to download (default: 20)")
    parser.add_argument("--output", "-o", default="./downloads", help="Output directory")
    parser.add_argument("--size", default="Large", choices=["Small", "Medium", "Large", "Wallpaper"],
                        help="Bing image size filter (default: Large)")
    parser.add_argument("--no-expand", action="store_true", help="Disable query expansion")
    args = parser.parse_args()

    manifest = search_and_download(
        query=args.query,
        max_results=args.max,
        output_dir=args.output,
        size_filter=args.size,
        enable_expansion=not args.no_expand,
    )
    print(f"\nDownloaded {manifest['total_downloaded']} images")
    print(f"Output: {manifest['output_dir']}")


if __name__ == "__main__":
    main()
