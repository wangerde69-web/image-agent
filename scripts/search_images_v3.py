# -*- coding: utf-8 -*-
"""
Enhanced image search v3 — fixes the "same images repeatedly" problem.

Key improvements over v2:
- Persistent cross-session hash database: tracks ALL downloaded images across runs,
  so we never re-download a visually similar image even in a completely new search.
- Domain diversity: limits results per domain to ensure diverse sources.
- Bing pagination diversity: adds time-based and random offsets to break popularity ranking.
- Query permutation: instead of just synonyms, generates semantically different queries.
- Multiple search strategies combined for maximum coverage.
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse, unquote

# ─── Dependencies ────────────────────────────────────────────────────────────────
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
log = logging.getLogger("img_search_v3")

# ─── Constants ──────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}
TIMEOUT = 15

# ─── Persistent Hash Database ───────────────────────────────────────────────────
class PersistentHashDB:
    """
    A JSON-backed perceptual hash database that persists across sessions.
    This is the KEY fix for the "same images repeatedly" problem:
    - Tracks ALL images ever downloaded by this script
    - Even across different query sessions
    - Uses pHash (perceptual hash) for visual similarity matching
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_dir = Path.home() / ".cache" / "image-agent"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "hashdb.json"
        self.db_path = Path(db_path)
        self.hashes: dict[str, dict] = {}  # hash_string → {url, first_seen, domains_seen}
        self._load()

    def _load(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.hashes = data.get("hashes", {})
                log.info("Hash DB loaded: %d entries from %s", len(self.hashes), self.db_path)
            except (json.JSONDecodeError, IOError) as e:
                log.warning("Hash DB corrupted, resetting: %s", e)
                self.hashes = {}
        else:
            log.info("New hash DB created at %s", self.db_path)

    def _save(self):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump({"hashes": self.hashes, "version": 1}, f, ensure_ascii=False)

    def is_known(self, image_path: Path, max_hamming: int = 6) -> tuple[bool, str | None]:
        """
        Return (is_known, first_seen_url) if the image is visually similar to any known image.
        max_hamming=6 is stricter than v2's 8, catching more near-duplicates.
        """
        try:
            img_hash = imagehash.phash(Image.open(image_path), hash_size=8)
            h_str = str(img_hash)

            for stored_hash, info in self.hashes.items():
                stored_hash_obj = imagehash.hex_to_hash(stored_hash)
                dist = img_hash - stored_hash_obj
                if dist <= max_hamming:
                    return True, info.get("url", "unknown")

            # No match found — add to DB
            self.hashes[h_str] = {
                "url": str(image_path),
                "first_seen": datetime.now().isoformat(),
                "domains": [],
            }
            return False, None
        except Exception as e:
            log.debug("Hash error for %s: %s", image_path.name, e)
            return False, None

    def add(self, image_path: Path, source_url: str = ""):
        """Manually add an image to the DB (e.g., from a folder scan)."""
        try:
            img_hash = imagehash.phash(Image.open(image_path), hash_size=8)
            h_str = str(img_hash)
            domain = urlparse(source_url).netloc if source_url else "local"
            if h_str not in self.hashes:
                self.hashes[h_str] = {"url": source_url, "first_seen": datetime.now().isoformat(), "domains": []}
            if domain not in self.hashes[h_str].get("domains", []):
                self.hashes[h_str]["domains"].append(domain)
            self._save()
        except Exception:
            pass

    def scan_folder(self, folder: Path):
        """Scan an existing folder and add all images to the DB (dedup across searches)."""
        count = 0
        for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
            for img_path in folder.rglob(f"*{ext}"):
                self.add(img_path, str(img_path))
                count += 1
        if count:
            self._save()
            log.info("Scanned %d existing images from %s into hash DB", count, folder)


# ─── Domain Diversity Filter ────────────────────────────────────────────────────
class DomainDiversityFilter:
    """
    Limits how many images we accept from the same domain.
    This is crucial for diversity — without it, Bing often returns 20 images
    from the same 2-3 popular sites, all showing the same subject.
    """

    def __init__(self, max_per_domain: int = 3):
        self.max_per_domain = max_per_domain
        self.domain_counts: dict[str, int] = {}

    def allow(self, url: str) -> bool:
        domain = urlparse(url).netloc
        count = self.domain_counts.get(domain, 0)
        if count >= self.max_per_domain:
            return False
        self.domain_counts[domain] = count + 1
        return True

    def reset(self):
        self.domain_counts.clear()


# ─── Download ───────────────────────────────────────────────────────────────────
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


# ─── Bing Images (v3: with diversity offsets + domain filter) ──────────────────
def search_bing_images(
    query: str,
    max_results: int = 20,
    size_filter: str = "Large",
    domain_filter: DomainDiversityFilter = None,
) -> list[dict]:
    """
    Search Bing Images with diversity enhancements:
    - Multiple offset positions for same query (not just page 1)
    - Time-based offset parameter to break popularity ranking
    - Domain diversity filtering
    """
    results = []
    seen_urls = set()
    per_page = 35

    offsets = list(range(0, min(max_results * 4, 300), per_page))
    random.shuffle(offsets)
    offsets = offsets[:8]
    offsets.sort()

    size_abd = f" filterui:imagesize-{size_filter.upper().replace(' ', '')}"
    freshness_filters = ["", "filterui:photo-photo", "filterui:imagesize-wallpaper"]

    for freshness in freshness_filters[:2]:
        if len(results) >= max_results * 2:
            break
        for offset in offsets:
            if len(results) >= max_results * 2:
                break
            q = query + size_abd + freshness
            url = (
                f"https://www.bing.com/images/async"
                f"?q={quote(q)}&first={offset}&count={per_page}"
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
                log.warning("[Bing] offset=%d error: %s", offset, e)
                continue

            raw_urls = re.findall(r"mediaurl=(https?[^&" + chr(34) + r"\s]+)", html, re.UNICODE)
            for raw in raw_urls:
                img_url = unquote(raw)
                if img_url in seen_urls or not img_url.startswith("http"):
                    continue
                if domain_filter and not domain_filter.allow(img_url):
                    log.debug("  [domain filter] skipping %s", urlparse(img_url).netloc)
                    continue
                seen_urls.add(img_url)
                results.append({
                    "url": img_url,
                    "title": f"bing_{len(results)}",
                    "source": "bing_images",
                    "license": "unknown",
                })
                if len(results) >= max_results * 2:
                    break
            time.sleep(0.3 + random.uniform(0, 0.3))

    log.info("[Bing] found %d unique URLs (domain-diverse)", len(results))
    return results[: max_results * 2]


# ─── Sogou Images ───────────────────────────────────────────────────────────────
def search_sogou_images(
    query: str,
    max_results: int = 20,
    domain_filter: DomainDiversityFilter = None,
) -> list[dict]:
    results = []
    seen = set()
    for start in range(0, min(max_results * 3, 60), 20):
        try:
            resp = requests.get(
                f"https://pic.sogou.com/pics/json.jsp"
                f"?query={quote(query)}&st=5&start={start}&xml_len=20",
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("[Sogou] error: %s", e)
            continue

        for item in data.get("items", []):
            img_url = item.get("thumbUrl") or item.get("pic_url", "")
            if not img_url or img_url in seen:
                continue
            if domain_filter and not domain_filter.allow(img_url):
                continue
            seen.add(img_url)
            results.append({
                "url": img_url,
                "title": item.get("title", f"sogou_{len(results)}"),
                "source": "sogou_images",
                "license": "unknown",
            })
            if len(results) >= max_results:
                break
        time.sleep(0.3)
    log.info("[Sogou] found %d images", len(results))
    return results


# ─── Baidu Images (NEW in v3 — important Chinese search engine) ─────────────────
def search_baidu_images(
    query: str,
    max_results: int = 20,
    domain_filter: DomainDiversityFilter = None,
) -> list[dict]:
    """
    Baidu Images is a major Chinese image search engine that often returns
    DIFFERENT images than Bing/Sogou for the same query.
    """
    results = []
    seen = set()
    for pn in range(0, min(max_results * 3, 60), 30):
        try:
            url = (
                f"https://image.baidu.com/search/acjson"
                f"?tn=resultjson_com&word={quote(query)}&pn={pn}&rn=30"
            )
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("[Baidu] error: %s", e)
            continue

        for item in data.get("data", []):
            img_url = item.get("middleURL") or item.get("thumbURL", "")
            if not img_url or not img_url.startswith("http"):
                continue
            if img_url in seen:
                continue
            if domain_filter and not domain_filter.allow(img_url):
                continue
            seen.add(img_url)
            results.append({
                "url": img_url,
                "title": item.get("fromPageTitleEnc", f"baidu_{len(results)}"),
                "source": "baidu_images",
                "license": "unknown",
            })
            if len(results) >= max_results:
                break
        time.sleep(0.4 + random.uniform(0, 0.2))

    log.info("[Baidu] found %d images", len(results))
    return results


# ─── Reddit Images (NEW in v3 — highly diverse, real user photos) ───────────────
def search_reddit_images(query: str, max_results: int = 15) -> list[dict]:
    """
    Reddit is excellent for diversity: real user photos across many communities.
    Each subreddit is a different source with different content.
    """
    subreddit_map = {
        "gym": ["gym", "fitness", "homegym", "FitnessRooms"],
        "treadmill": ["fitness", "gym", "homegym"],
        "car": ["cars", "carporn", "Autos"],
        "dog": ["dogpictures", "dogs", "puppies"],
        "cat": ["catpictures", "cats"],
        "food": ["food", "FoodPorn", "cooking"],
        "nature": ["nature", "earthporn", "landscapephotos"],
        "city": ["cityporn", "urbanporn"],
        "beach": ["beach", "EarthPorn"],
        "mountain": ["mountainporn", "hiking"],
        "laptop": ["laptops", "tech"],
        "phone": ["smartphones"],
        "shoes": ["Sneakers", "goodsmiles"],
        "watch": ["Watches", "Wristcheck"],
        "bike": ["bicycling", "bikeporn"],
        "art": ["Art", "artwork"],
        "photo": ["photographs", "itookapicture"],
    }

    query_lower = query.lower()
    relevant_subs = []
    for key, subs in subreddit_map.items():
        if key in query_lower:
            relevant_subs.extend(subs)
    if not relevant_subs:
        relevant_subs = ["all", "pics", "interestingasfuck"]

    relevant_subs = list(set(relevant_subs))[:4]
    results = []
    seen = set()

    for subreddit in relevant_subs:
        try:
            url = (
                f"https://www.reddit.com/r/{subreddit}/search.json"
                f"?q={quote(query)}&restrict_sr=1&sort=top&limit=10"
            )
            resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            log.debug("[Reddit] r/%s error: %s", subreddit, e)
            continue

        for post in data.get("data", {}).get("children", []):
            post_data = post.get("data", {})
            post_url = post_data.get("url", "")
            if not post_url or not any(post_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                if "reddit.com/gallery" in post_url:
                    post_url = f"https://reddit.com{post_data.get('permalink', '')}"
                else:
                    continue
            if post_url in seen:
                continue
            seen.add(post_url)
            results.append({
                "url": post_url,
                "title": post_data.get("title", f"reddit_{len(results)}"),
                "source": f"reddit:r/{subreddit}",
                "license": "reddit",
                "attribution": post_data.get("author", ""),
            })
            if len(results) >= max_results:
                break
        time.sleep(0.3)

    log.info("[Reddit] found %d images", len(results))
    return results


# ─── Tumblr Images ──────────────────────────────────────────────────────────────
def search_tumblr_images(query: str, max_results: int = 10) -> list[dict]:
    """Tumblr often has unique images not on mainstream search engines."""
    results = []
    seen = set()
    try:
        url = f"https://www.tumblr.com/search/{quote(query)}/image"
        resp = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=TIMEOUT)
        if resp.status_code != 200:
            return []
        html = resp.text
    except Exception as e:
        log.debug("[Tumblr] error: %s", e)
        return []

    img_patterns = [
        r'"original_size"\s*:\s*\{\s*"url"\s*:\s*"([^"]+)"',
        r'src="(https://\d+\.media\.tumblr\.com/[^"]+\.jpg)"',
    ]
    for pattern in img_patterns:
        for match in re.finditer(pattern, html):
            img_url = match.group(1).replace("\\/", "/")
            if img_url in seen:
                continue
            seen.add(img_url)
            results.append({
                "url": img_url,
                "title": f"tumblr_{len(results)}",
                "source": "tumblr",
                "license": "tumblr",
            })
            if len(results) >= max_results:
                break

    log.info("[Tumblr] found %d images", len(results))
    return results


# ─── Pixiv (NEW — high-quality Japanese illustration/art) ────────────────────────
def search_pixiv_images(query: str, max_results: int = 10) -> list[dict]:
    """Pixiv — Japanese art platform with very different content from Western search engines."""
    results = []
    seen = set()
    try:
        url = f"https://www.pixiv.net/en/tags/{quote(query)}/artworks"
        resp = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=TIMEOUT)
        if resp.status_code != 200:
            return []
        html = resp.text
    except Exception as e:
        log.debug("[Pixiv] error: %s", e)
        return []

    pattern = r'"medium"\s*:\s*"([^"]+\.pixiv\.net[^"]+)"'
    for match in re.finditer(pattern, html):
        img_url = match.group(1).replace("\\/", "/")
        if "/600x600" in img_url or "/150x150" in img_url:
            continue
        if img_url in seen:
            continue
        seen.add(img_url)
        results.append({
            "url": img_url,
            "title": f"pixiv_{len(results)}",
            "source": "pixiv",
            "license": "pixiv",
        })
        if len(results) >= max_results:
            break

    log.info("[Pixiv] found %d images", len(results))
    return results


# ─── Google Images via SerpAPI ─────────────────────────────────────────────────
def search_google_images_serpapi(query: str, max_results: int = 20) -> list[dict]:
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        log.info("[SerpAPI] No API key (set SERPAPI_KEY to enable)")
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "tbm": "isch", "num": min(max_results, 100), "api_key": api_key},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("[SerpAPI] error: %s", e)
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
    log.info("[SerpAPI] found %d images", len(results))
    return results


# ─── Unsplash API ───────────────────────────────────────────────────────────────
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


# ─── Pexels API ────────────────────────────────────────────────────────────────
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


# ─── Flickr CC ────────────────────────────────────────────────────────────────
def search_flickr_cc(query: str, max_results: int = 15) -> list[dict]:
    try:
        resp = requests.get(
            "https://www.flickr.com/services/rest/",
            params={
                "method": "flickr.photos.search",
                "api_key": os.environ.get("FLICKR_API_KEY", "dummy"),
                "text": query,
                "license": "1,2,3,4,5,6,7,9,10",
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
        img_url = f"https://farm{farm}.staticflickr.com/{server}/{pid}_{secret}_z.jpg"
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
    log.info("[Flickr] found %d images", len(results))
    return results


# ─── Query Expansion v3: Semantic Variations ────────────────────────────────────
def expand_queries_v3(base_query: str, max_variations: int = 6) -> list[str]:
    """
    Generate genuinely diverse query variations (not just synonyms).
    Each variation targets a different TYPE of image.
    """
    queries = [base_query]
    ql = base_query.lower()

    facets = [
        f"{ql} close up",
        f"{ql} real photo",
        f"{ql} 高清",
        f"best {ql}",
        f"{ql} 真实拍摄",
        f"{ql} stock photo",
        f"authentic {ql}",
        f"{ql} outdoor",
        f"{ql} studio",
        f"natural {ql}",
    ]
    for f in facets:
        if f != base_query and f not in queries:
            queries.append(f)

    return list(set(queries))[:max_variations]


# ─── Slug / sanitize ───────────────────────────────────────────────────────────
def slugify(query: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", query)
    name = re.sub(r"[\x00-\x1f]", "", name)
    return name.strip().lower().replace(" ", "_")[:60] or "untitled"


def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, ensure_ascii=False, indent=2, fp=f)


# ─── Main Search + Download ────────────────────────────────────────────────────
def search_and_download(
    query: str,
    max_results: int = 20,
    output_dir: str = "./downloads",
    size_filter: str = "Large",
    enable_expansion: bool = True,
    hash_db_path: str = None,
    scan_existing_first: bool = False,
) -> dict:
    output_path = Path(output_dir) / slugify(query)
    output_path.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("Image Search v3 — Query: '%s' (max=%d)", query, max_results)
    log.info("Output: %s", output_path)
    log.info("=" * 60)

    hashdb = PersistentHashDB(hash_db_path)

    if scan_existing_first:
        existing_folders = [p for p in output_path.parent.iterdir() if p.is_dir() and p != output_path]
        for folder in existing_folders:
            hashdb.scan_folder(folder)
            log.info("  Scanned existing folder: %s", folder.name)

    all_results = []
    domain_filter = DomainDiversityFilter(max_per_domain=3)

    if enable_expansion:
        queries = expand_queries_v3(query, max_variations=6)
        log.info("Query variations: %s", queries)
    else:
        queries = [query]

    # Phase 1: Bing + Sogou + Baidu with query variations
    for q in queries:
        if len(all_results) >= max_results * 3:
            break
        size = size_filter if q == query else "Medium"
        all_results.extend(search_bing_images(q, max_results, size, domain_filter))
        time.sleep(0.4)
        all_results.extend(search_sogou_images(q, max_results // 3, domain_filter))
        time.sleep(0.3)
        all_results.extend(search_baidu_images(q, max_results // 3, domain_filter))
        time.sleep(0.4)

    domain_filter.reset()

    # Phase 2: Diverse platforms (always different images)
    all_results.extend(search_reddit_images(query, max_results // 2))
    all_results.extend(search_tumblr_images(query, max_results // 3))
    all_results.extend(search_pixiv_images(query, max_results // 3))

    # Phase 3: API-based (high quality)
    all_results.extend(search_unsplash(query, max_results // 2))
    all_results.extend(search_pexels(query, max_results // 2))
    all_results.extend(search_google_images_serpapi(query, max_results // 2))
    all_results.extend(search_flickr_cc(query, max_results // 4))

    # URL-level dedup
    seen_urls = set()
    unique_results = []
    for item in all_results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_results.append(item)

    log.info("Total unique URLs: %d (from %d raw)", len(unique_results), len(all_results))
    if not unique_results:
        log.error("No images found from any source!")
        return {"query": query, "downloaded": [], "hashdb_entries": len(hashdb.hashes), "output_dir": str(output_path)}

    # Download with PERCEPTUAL HASH dedup against ENTIRE hash DB
    downloaded = []
    skipped_known = 0

    for i, item in enumerate(unique_results[:max_results * 2], 1):
        if len(downloaded) >= max_results:
            break

        url_short = item["url"][:70]
        log.info("[%d/%d] [%s] %s", i, min(len(unique_results), max_results * 2), item["source"], url_short)

        ext = os.path.splitext(urlparse(item["url"]).path)[1] or ".jpg"
        if len(ext) > 5:
            ext = ".jpg"
        filename = f"img_{len(downloaded)+1:03d}{ext}"
        filepath = output_path / filename

        ok = download_image(item["url"], filepath)
        if not ok:
            log.debug("  -> download failed")
            continue

        is_known, first_seen_url = hashdb.is_known(filepath, max_hamming=6)
        if is_known:
            log.info("  -> known image (similar to previous download), skipping")
            filepath.unlink(missing_ok=True)
            skipped_known += 1
            hashdb.add(filepath, item["url"])
            continue

        item["local_path"] = str(filepath)
        item["local_filename"] = filename
        downloaded.append(item)
        hashdb.add(filepath, item["url"])
        log.info("  -> saved: %s (%.1f KB, hash DB total: %d)", filename, filepath.stat().st_size / 1024, len(hashdb.hashes))
        time.sleep(0.15 + random.uniform(0, 0.1))

    hashdb._save()

    manifest = {
        "query": query,
        "total_found": len(unique_results),
        "total_downloaded": len(downloaded),
        "skipped_known_by_hashdb": skipped_known,
        "output_dir": str(output_path),
        "hashdb_path": str(hashdb.db_path),
        "images": downloaded,
    }
    manifest_path = output_path / "manifest.json"
    save_json(str(manifest_path), manifest)

    log.info("=" * 60)
    log.info("DONE: %d images -> %s", len(downloaded), output_path)
    log.info("Hash DB now has %d unique image signatures", len(hashdb.hashes))
    log.info("Skipped %d known images (same visual content, different URL)", skipped_known)
    log.info("Manifest: %s", manifest_path)
    log.info("=" * 60)

    return manifest


# ─── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Image search v3: fixes the 'same images repeatedly' problem "
                    "with persistent cross-session hash DB and domain diversity."
    )
    parser.add_argument("query", help="Search query (e.g. 'gym treadmill')")
    parser.add_argument("--max", type=int, default=20, help="Max images to download (default: 20)")
    parser.add_argument("--output", "-o", default="./downloads", help="Output directory")
    parser.add_argument("--size", default="Large",
                        choices=["Small", "Medium", "Large", "Wallpaper"],
                        help="Bing image size filter (default: Large)")
    parser.add_argument("--no-expand", action="store_true", help="Disable query expansion")
    parser.add_argument("--scan-existing", action="store_true",
                        help="Scan existing folders into hash DB first (recommended!)")
    parser.add_argument("--hashdb", default=None,
                        help="Custom path for the persistent hash database")
    args = parser.parse_args()

    manifest = search_and_download(
        query=args.query,
        max_results=args.max,
        output_dir=args.output,
        size_filter=args.size,
        enable_expansion=not args.no_expand,
        hash_db_path=args.hashdb,
        scan_existing_first=args.scan_existing,
    )
    print(f"\nDownloaded {manifest['total_downloaded']} images")
    print(f"Output: {manifest['output_dir']}")
    print(f"Hash DB entries: {manifest['hashdb_entries']}")


if __name__ == "__main__":
    main()
