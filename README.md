# Image Agent

AI-powered image search, download, and content-based renaming for AI agents.

**Given a search query → search the web for images → download with deduplication → use vision AI to analyze each image → rename files by content.**

---

## Features

- **Multi-source search**: Bing Images (works in China), Sogou, Unsplash, Pexels, Google Images (SerpAPI), Flickr CC
- **Query expansion**: Automatically generates 3-5 query variations (synonyms, related terms) to broaden coverage
- **Perceptual hash deduplication**: Uses `imagehash` to detect near-duplicate images (same photo, different format/domain)
- **Vision-based auto-rename**: Analyzes image content via AI and renames files by what they actually contain
- **Zero-config start**: Works without API keys (Bing and Sogou are free)
- **Cross-platform**: Windows (PowerShell), Linux, macOS

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Search and download images

```bash
python scripts/search_images_v2.py "golden retriever" --max 20 -o ./downloads
```

This will:
- Expand your query into 3-5 variations for broader coverage
- Search multiple sources (Bing, Sogou, Unsplash, Pexels, etc.)
- Download images with perceptual hash deduplication
- Save a `manifest.json` with all downloaded image info

### 3. Rename by vision

**Option A — Fully automated (requires vision API key):**

```bash
python scripts/auto_rename.py ./downloads/golden_retriever
```

Set API key for vision:
```bash
# Windows
$env:OPENROUTER_API_KEY = "your-key-here"
# Then run the command above
```

**Option B — Agent-assisted (no extra setup):**

Give the downloaded folder to an AI agent with the `image-agent` skill. The agent will use its vision model to analyze each image and rename files automatically.

```powershell
# Agent does this automatically:
# 1. Read manifest.json
# 2. For each image, use vision model to analyze content
# 3. Rename: img_001.jpg → golden_retriever_dog_beach.jpg
```

---

## Workflow

```
User query (e.g. "gym treadmill")
    │
    v
search_images_v2.py
    │  1. Query expansion → 3-5 variations
    │  2. Multi-source search (Bing, Sogou, Unsplash, Pexels, ...)
    │  3. Perceptual hash dedup (same image, different URL → filtered)
    │  4. Download with size filter (Large/Wallpaper)
    │
    v
./downloads/{query_slug}/
    ├── img_001.jpg
    ├── img_002.jpg
    ├── ...
    └── manifest.json
    │
    v
auto_rename.py (or AI agent with image tool)
    │  Vision AI analyzes each image
    │  Generates descriptive filename
    │
    v
Files renamed by content:
  img_001.jpg → treadmill_running_machine.jpg
  img_002.jpg → gym_fitness_weights.jpg
```

---

## Configuration

### Optional: Set API Keys for High-Quality Sources

```bash
# Unsplash (free, 50 req/hr) — https://unsplash.com/developers
$env:UNSPLASH_ACCESS_KEY = "your_key"

# Pexels (free, 200 req/month) — https://www.pexels.com/api/
$env:PEXELS_API_KEY = "your_key"

# SerpAPI (free tier: 100 searches/month) — https://serpapi.com
$env:SERPAPI_KEY = "your_key"
```

### Vision API Key (for auto_rename.py)

```bash
# OpenRouter-compatible API key (for vision model)
$env:OPENROUTER_API_KEY = "your-key"
# Supports: Claude, GPT-4V, Gemini Vision, etc.
```

---

## CLI Reference

### search_images_v2.py

| Argument | Description |
|----------|-------------|
| `query` | Search query (required) |
| `--max N` | Max images to download (default: 20) |
| `-o, --output DIR` | Output directory (default: ./downloads) |
| `--size S` | Bing size filter: Small/Medium/Large/Wallpaper (default: Large) |
| `--no-expand` | Disable query expansion |

### auto_rename.py

| Argument | Description |
|----------|-------------|
| `folder` | Folder containing images (required) |
| `--dry-run` | Preview without renaming |
| `--delay N` | Delay between API calls in seconds (default: 0.5) |
| `--api-key KEY` | Override API key |

---

## Image Sources

| Source | Key needed | Quality | Notes |
|--------|------------|---------|-------|
| Bing Images | No | Medium-High | Primary source, works in China |
| Sogou Images | No | Medium | China alternative |
| Google Images (SerpAPI) | Yes (free tier) | High | 100 searches/month |
| Unsplash API | Yes (free) | High | 50 requests/hour |
| Pexels API | Yes (free) | High | 200 requests/month |
| Flickr CC | No | Medium | Creative Commons only |

---

## File Structure

```
image-agent/
├── SKILL.md                      <- AI agent skill metadata
├── README.md                     <- This file
├── requirements.txt              <- Python dependencies
└── scripts/
    ├── search_images_v2.py       <- Enhanced search + download
    ├── auto_rename.py            <- Fully automated vision rename
    └── rename_by_vision.py      <- Manifest generator (agent-assisted)
```

---

## Troubleshooting

### "No images found" or too few results
- Try `--no-expand` if query expansion is returning unrelated images
- Try a more specific query
- Check if Bing is accessible in your region

### "Same images downloaded repeatedly"
- This is fixed in v2 via perceptual hash deduplication
- Use `search_images_v2.py` (not the old `search_images.py`)
- Try `--size Wallpaper` for more variety

### Vision API not working in auto_rename.py
- Set `$env:OPENROUTER_API_KEY` to a valid key
- Or use the AI agent with the `image-agent` skill (built-in vision, no extra key needed)

---

## License

MIT
