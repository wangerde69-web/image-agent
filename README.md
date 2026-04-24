# 🖼️ Image Agent

> Search web images → Download with cross-session dedup → Auto-rename by vision AI

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

**Problem this solves:** Search engines keep returning the same popular images.
This tool gets genuinely diverse images AND never re-downloads visually similar ones.

## Features

- 🌐 **Multi-source search**: Bing + Baidu + Sogou + Reddit + Tumblr + Pixiv + Unsplash + Pexels + Flickr CC
- 🗑️ **Cross-session perceptual dedup**: Persistent hash DB tracks ALL downloaded images across searches
- 🏷️ **Domain diversity**: Max 3 images per domain — ensures genuinely different sources
- 🤖 **Vision AI rename**: Auto-rename files by analyzing their visual content
- 🔄 **Query permutation**: Not just synonyms — generates genuinely different queries

## Installation

```bash
pip install requests imagehash Pillow
```

Optional API keys (for higher quality image sources):
```bash
export UNSPLASH_ACCESS_KEY="your_key"       # unsplash.com/developers
export PEXELS_API_KEY="your_key"           # pexels.com/api
export SERPAPI_KEY="your_key"              # serpapi.com (100/month free)
```

## Quick Start

### Search + Download

```bash
# Basic usage (20 images)
python scripts/search_images_v3.py "golden retriever" --max 20 -o ./downloads

# Maximum diversity: scan existing folders first (recommended!)
python scripts/search_images_v3.py "健身房器材" --max 30 -o ./downloads --scan-existing

# Single query, no expansion
python scripts/search_images_v3.py "city night" --max 20 --no-expand -o ./downloads
```

### Auto-rename by Vision

**Recommended**: Ask the AI agent to rename — it has a built-in vision tool (Claude Sonnet, free).

Or via script:
```bash
# Preview
python scripts/auto_rename.py ./downloads/golden_retriever --dry-run

# Auto-rename (needs vision-capable API key)
python scripts/auto_rename.py ./downloads/golden_retriever --delay 1.0
```

> ⚠️ **Note**: aicodee.com's MiniMax models do NOT support image input. For vision rename,
> use the agent's built-in `image` tool or an OpenRouter key with Claude/GPT-4V.

## v3 vs v2 — What's Fixed

| Problem | v2 | v3 |
|---------|----|----|
| Same images on every search | Bing returns same popular images | Multi-source + Baidu + Reddit |
| Re-downloads similar images | Only within-batch dedup | Persistent hash DB, cross-session |
| Bing pagination stuck | Same results | Randomized offsets + time filters |
| Query expansion too narrow | Just synonyms | Semantic query permutation |
| Limited sources | Bing + Sogou | 10 sources: Bing + Baidu + Sogou + Reddit + Tumblr + Pixiv + APIs |

## Architecture

```
search_images_v3.py (main script)
    │
    ├── PersistentHashDB       ← ~/.cache/image-agent/hashdb.json
    ├── DomainDiversityFilter  ← max 3 per domain
    ├── Bing + Baidu + Sogou   ← Chinese search engines
    ├── Reddit + Tumblr + Pixiv← User-generated content (very different!)
    └── API sources           ← Unsplash + Pexels + SerpAPI + Flickr CC
    │
    ▼
auto_rename.py (OR: use agent's `image` tool)
    └── Vision AI → rename by content
```

## How the "Same Images" Problem is Solved

**Layer 1 — Persistent Hash DB**: Every downloaded image is hashed (pHash) and stored.
The next time you search anything, visually similar images are skipped.

**Layer 2 — Domain Diversity**: Bing might return 20 images from the same 3 sites.
v3 limits to 3 per domain.

**Layer 3 — Baidu + Reddit**: These sources return completely different photos than Bing.
Reddit especially — real user photos from real gyms, cars, dogs, etc.

**Layer 4 — Query Permutation**: Instead of just synonyms, generates queries like
"gym close up", "gym real photo", "gym stock photo" — each returning different images.

## API Keys (Optional)

| Service | Free Tier | Sign Up |
|---------|-----------|---------|
| Unsplash | 50 req/hour | unsplash.com/developers |
| Pexels | 200 req/month | pexels.com/api |
| SerpAPI | 100 searches/month | serpapi.com |
| Flickr | No key needed | — |

## License

MIT — free to use, modify, distribute.
