---
name: image-agent
description: >
  Search the web for images, download them with perceptual deduplication, and
  automatically rename files by analyzing their content with vision AI.

  Use when the user wants to:
  - Find/download images for a topic ("搜索一些关于 X 的图片", "找几张健身器材的照片")
  - Search and download images ("search images for X", "download photos of X")
  - Rename a batch of images by their visual content ("根据内容自动命名图片", "auto-rename images by vision")
  - Build a diverse image dataset from multiple sources
  - Fix repetitive/duplicate image search results

  Trigger phrases: "搜索下载图片" / "search and download" / "找一些关于" / "rename by vision" /
  "自动命名图片" / "download images for" / "build image dataset"
---

# Image Agent — Search + Download + Auto-Rename

Full pipeline: **search** → **download** → **dedupe** → **analyze** → **auto-rename**

```
User query
    │
    v
search_images_v2.py  (query expansion + multi-source + perceptual dedup)
    |
    v
auto_rename.py  (vision AI → rename by content)
    |
    v
Files renamed: img_001.jpg → golden_retriever_dog.jpg
```

## Quick Start (Zero Config)

```powershell
# Install dependencies
pip install -r C:\Users\Administrator\clawd\image-agent\requirements.txt

# Step 1: Search + download (20 images, no API key needed)
python C:\Users\Administrator\clawd\image-agent\scripts\search_images_v2.py "golden retriever" --max 20 -o C:\Users\Administrator\clawd\image-agent\downloads

# Step 2: Auto-rename by vision (calls AI API, renames files automatically)
python C:\Users\Administrator\clawd\image-agent\scripts\auto_rename.py C:\Users\Administrator\clawd\image-agent\downloads\golden_retriever
```

## Scripts

### `search_images_v2.py` — Enhanced Search + Download

Key improvements over the basic version:
- **Query expansion**: generates 3-5 query variations (synonyms, related terms) to broaden coverage
- **Perceptual hash dedup**: uses `imagehash` to detect near-duplicate images (same photo, different format/compression)
- **Multi-source**: Bing + Sogou + Unsplash + Pexels + SerpAPI Google + Flickr CC
- **Size filter**: requests large/high-res images from Bing

```powershell
# Basic usage
python scripts/search_images_v2.py "gym equipment" --max 30 -o ./downloads

# Large images only, no query expansion
python scripts/search_images_v2.py "city night" --max 20 --size Wallpaper --no-expand -o ./downloads

# Dry-run preview (don't rename, just analyze)
python scripts/auto_rename.py .\downloads\query_folder --dry-run
```

Arguments:
| Arg | Description |
|-----|-------------|
| `query` | Search query (required) |
| `--max N` | Max images to download (default: 20) |
| `-o, --output DIR` | Output directory (default: ./downloads) |
| `--size S` | Bing size filter: Small/Medium/Large/Wallpaper (default: Large) |
| `--no-expand` | Disable query expansion |

### `auto_rename.py` — Vision-Based Auto-Rename

Sends each image to the vision API and renames the file based on what the AI sees.

```powershell
# Auto-rename all images in a folder (requires API key)
python scripts/auto_rename.py .\downloads\query_folder

# Dry run — preview what would happen without renaming
python scripts/auto_rename.py .\downloads\query_folder --dry-run

# Slower (more polite to API)
python scripts/auto_rename.py .\downloads\query_folder --delay 1.0
```

Environment variables (optional — has sensible defaults):
```powershell
$env:OPENROUTER_API_KEY = "sk-..."     # For vision API (defaults to configured key)
$env:MINIMAX_API_KEY = "sk-..."        # Alternative vision API
$env:UNSPLASH_ACCESS_KEY = "..."       # Free Unsplash API key
$env:PEXELS_API_KEY = "..."            # Free Pexels API key
$env:SERPAPI_KEY = "..."               # SerpAPI (100 searches/month free)
```

## Troubleshooting

### "No images found"
- Try `--no-expand` if query expansion is returning unrelated images
- Try a different query (more specific terms)
- Some international sources (Unsplash, Pexels, Flickr) need API keys

### "Same images downloaded repeatedly"
- This is fixed in v2: perceptual hash dedup catches visually identical images even from different URLs
- Make sure you're using `search_images_v2.py` (not the old `search_images.py`)
- Try reducing `--max` or using `--size Wallpaper` for more variety

### "Vision API call failed"
- Check API key is set: `echo $env:OPENROUTER_API_KEY`
- Try `--delay 1.0` to slow down requests
- The default API endpoint is `https://v2.aicodee.com` (MiniMax-compatible)

## Architecture

```
image-agent/
├── SKILL.md                    <- This file (agent context)
├── scripts/
│   ├── search_images_v2.py     <- Enhanced search + download
│   ├── auto_rename.py          <- Vision AI rename (fully automated)
│   └── rename_by_vision.py     <- Manifest generator (agent-assisted)
├── requirements.txt
└── downloads/                  <- Default download location
    └── {query_slug}/
        ├── img_001.jpg
        ├── img_002.jpg
        └── manifest.json
```

## Image Sources

| Source | Key needed | Quality | Notes |
|--------|-----------|---------|-------|
| Bing Images | No | Medium-High | Works in China, primary source |
| Sogou Images | No | Medium | China alternative |
| Google Images (SerpAPI) | Yes (free tier) | High | 100 searches/month |
| Unsplash API | Yes (free) | High | 50 requests/hour |
| Pexels API | Yes (free) | High | 200 requests/month |
| Flickr CC | No | Medium | Creative Commons only |
