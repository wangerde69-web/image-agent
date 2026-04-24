---
name: image-agent
description: >
  Search the web for images, download them with cross-session perceptual deduplication,
  and automatically rename files by analyzing their visual content with vision AI.

  Use when the user wants to:
  - Find and download images for a topic ("搜索一些关于 X 的图片")
  - Search and download images ("search images for X")
  - Rename a batch of images by their visual content ("根据内容自动命名图片")
  - Build a diverse image dataset from multiple sources
  - Fix repetitive/duplicate image search results
  - Full pipeline: search → download → dedupe → auto-rename

  Trigger phrases: "搜索下载图片" / "search and download" / "找一些关于" /
  "rename by vision" / "自动命名图片" / "download images for" /
  "build image dataset" / "找一些不一样的图片"
---

# Image Agent — Search + Download + Cross-Session Deduplication + Auto-Rename

## Architecture

```
User query ("找一些健身房图片")
    │
    v
search_images_v3.py  ← KEY SCRIPT (use this one, NOT v2!)
    ├── PersistentHashDB     (cross-session dedup — never re-download similar images)
    ├── DomainDiversityFilter (max 3 per domain — diverse sources)
    ├── Multi-source: Bing + Sogou + Baidu + Reddit + Tumblr + Pixiv
    │                   + Unsplash + Pexels + SerpAPI + Flickr CC
    └── Query permutation (genuinely different queries, not just synonyms)
    │
    v  (downloaded images)
auto_rename.py  (OR: use the agent's `image` tool directly for renaming)
    └── Vision AI → rename by content
    │
    v
Files renamed: img_001.jpg → golden_retriever_dog.jpg
```

## Quick Start

### Step 1: Install dependencies
```powershell
pip install requests imagehash Pillow
```

### Step 2: Search + Download (v3 — fixes the "same images repeatedly" problem!)
```powershell
# Basic: 20 images, zero config
python C:\Users\Administrator\clawd\image-agent\scripts\search_images_v3.py "golden retriever" --max 20 -o C:\Users\Administrator\clawd\image-agent\downloads

# Maximum diversity: scan existing folders into hash DB first (recommended!)
python C:\Users\Administrator\clawd\image-agent\scripts\search_images_v3.py "健身房器材" --max 30 -o C:\Users\Administrator\clawd\image-agent\downloads --scan-existing

# No query expansion, single query
python C:\Users\Administrator\clawd\image-agent\scripts\search_images_v3.py "gym treadmill" --max 20 --no-expand -o C:\Users\Administrator\clawd\image-agent\downloads
```

### Step 3: Auto-rename by vision (agent tool — best quality, free)
The agent's built-in `image` tool uses Claude Sonnet (free via OpenClaw).
**This is the recommended way to rename — just ask the agent!**

```
User: "帮我把 downloads/golden_retriever 里的图片按内容重命名"
Agent: Uses `image` tool to analyze each image, then renames files.
```

Or via script (requires API key with vision support):
```powershell
python C:\Users\Administrator\clawd\image-agent\scripts\auto_rename.py C:\Users\Administrator\clawd\image-agent\downloads\golden_retriever --dry-run
```

## v3 vs v2 — What's Fixed

| Problem | v2 | v3 |
|---------|----|----|
| Same images on every search | Bing returns same popular images | Multi-source + Baidu + Reddit |
| Re-downloads similar images | Only within-batch dedup | Persistent hash DB, cross-session |
| Bing pagination stuck | Same results | Randomized offsets + freshness filters |
| Query expansion too narrow | Just synonyms | Semantic query permutation |
| Limited sources | Bing + Sogou | 10 sources: Bing + Baidu + Sogou + Reddit + Tumblr + Pixiv + 4 APIs |

## Scripts

### `search_images_v3.py` — The main search script

```powershell
python C:\Users\Administrator\clawd\image-agent\scripts\search_images_v3.py "query" [options]
```

| Arg | Description |
|-----|-------------|
| `query` | Search query (required) |
| `--max N` | Max images to download (default: 20) |
| `-o, --output DIR` | Output directory (default: ./downloads) |
| `--size S` | Bing size: Small/Medium/Large/Wallpaper (default: Large) |
| `--no-expand` | Disable query expansion |
| `--scan-existing` | Scan existing folders into hash DB first (recommended!) |
| `--hashdb PATH` | Custom path for persistent hash database |

**The `--scan-existing` flag is highly recommended** — it loads all previously
downloaded images into the hash DB, so you never re-download visually similar
images even across completely different search queries.

### `auto_rename.py` — Vision-based auto-rename

```powershell
# Dry run
python C:\Users\Administrator\clawd\image-agent\scripts\auto_rename.py .\downloads\query_folder --dry-run

# Auto-rename (needs vision-capable API key)
python C:\Users\Administrator\clawd\image-agent\scripts\auto_rename.py .\downloads\query_folder --delay 1.0
```

## Image Sources

| Source | API Key | Quality | Diversity | Notes |
|--------|---------|---------|-----------|-------|
| Bing Images | ❌ No | Medium-High | ⭐⭐⭐ | Primary source, improved pagination |
| Baidu Images | ❌ No | Medium | ⭐⭐⭐ | **NEW** — different results from Bing |
| Sogou Images | ❌ No | Medium | ⭐⭐ | China alternative |
| Reddit | ❌ No | High | ⭐⭐⭐⭐ | Real user photos, very different from search engines |
| Tumblr | ❌ No | Medium | ⭐⭐⭐ | **NEW** — unique images not on other platforms |
| Pixiv | ❌ No | High | ⭐⭐⭐ | **NEW** — Japanese art/illustration platform |
| Unsplash API | ✅ Free | High | ⭐⭐⭐ | 50 req/hour, high-quality photos |
| Pexels API | ✅ Free | High | ⭐⭐⭐ | 200 req/month, high-quality photos |
| Google (SerpAPI) | ✅ Free tier | High | ⭐⭐⭐ | 100 searches/month |
| Flickr CC | ❌ No | Medium | ⭐⭐ | Creative Commons only |

## The "Same Images" Problem — Root Cause & Solution

### Why search engines return the same images
Search engines rank by **popularity/relevance**, not uniqueness. For "gym treadmill",
the top results are always the same popular product photos, regardless of pagination.

### The v3 solution: 4 layers of diversity

**Layer 1 — Cross-session persistent hash DB**
Every image ever downloaded is hashed (pHash) and stored in a persistent database at
`~/.cache/image-agent/hashdb.json`. Even if you search for something completely
different next week, if the image is visually similar to one you already have, it
gets skipped. Run with `--scan-existing` to populate the DB from all previous downloads.

**Layer 2 — Domain diversity filter (max 3 per domain)**
Without this, Bing might return 20 images from Amazon + Wikipedia, all showing the
same product. v3 limits to 3 images per domain.

**Layer 3 — Multiple genuinely different search engines**
Bing + Baidu + Sogou all index different image pools. Baidu is especially effective
for Chinese-language queries and returns completely different photos.

**Layer 4 — Reddit/Tumblr/Pixiv as content sources**
These platforms have organic, user-generated content that never appears in
search engine results. Reddit for "gym" returns real gym photos from real users.

## Environment Variables

```powershell
# Vision API (for auto_rename.py — MUST support vision models)
# NOTE: aicodee.com MiniMax models do NOT support vision!
$env:OPENROUTER_API_KEY = "sk-..."

# Optional image search API keys (better quality sources)
$env:UNSPLASH_ACCESS_KEY = "..."   # unsplash.com/developers (free)
$env:PEXELS_API_KEY = "..."        # pexels.com/api (free)
$env:SERPAPI_KEY = "..."           # serpapi.com (100 searches/month free)
```

## Directory Structure

```
image-agent/
├── SKILL.md                      ← This file (agent context)
├── README.md                     ← User-facing documentation
├── requirements.txt
├── scripts/
│   ├── search_images_v3.py       ← MAIN SCRIPT (use this!)
│   ├── auto_rename.py            ← Vision AI rename
│   └── rename_by_vision.py       ← Manifest generator (agent-assisted)
├── downloads/                    ← Default download location (create manually)
│   └── {query_slug}/
│       ├── img_001.jpg
│       └── manifest.json
└── ~/.cache/image-agent/hashdb.json  ← Persistent hash DB (auto-created)
```

## Troubleshooting

### "No images found"
- Try `--no-expand` if query expansion is returning unrelated images
- Try a different query (more specific terms)
- Some sources (Unsplash, Pexels) need API keys

### "Same images downloaded as before"
- **Use v3 with `--scan-existing`** — this is the key fix
- Run: `python scripts/search_images_v3.py "query" --scan-existing --max 30`

### "auto_rename.py says 'vision API' failed"
- aicodee.com MiniMax models do NOT support image input
- **Best solution**: Ask the agent directly — it has a built-in `image` tool
  that uses Claude Sonnet for vision, which is free
- Alternative: Set `OPENROUTER_API_KEY` with a key that supports vision
  (e.g., `anthropic/claude-3.5-sonnet` via OpenRouter)
