# ImageAgent Skill

**Search the web for images, download them, and rename by AI vision analysis.**

## What it does

1. Given a search query, search multiple sources (Bing, Sogou, Unsplash, Pexels, Wikipedia)
2. Download images to a local folder with automatic deduplication
3. Generate a rename manifest (JSON)
4. Use vision AI model to analyze each image's content
5. Rename files by what they actually contain

**Trigger phrases**:
- "鎼滅储涓嬭浇鍥剧墖" / "search and download images"
- "鎵句竴浜涘叧浜?X 鐨勫浘鐗? / "find images about X"
- "download images for [topic]"
- "鏍规嵁鍐呭缁欏浘鐗囧懡鍚? / "rename images by content"

## Architecture

```
image-agent/
  scripts/
    search_images.py      <- Multi-source search + download (Bing primary)
    rename_by_vision.py   <- Generate manifest for AI rename
  requirements.txt        <- requests
  SKILL.md               <- This file
  README.md              <- Full documentation
```

## Search Sources (in priority order)

| Source              | Key needed | Best for                 |
|---------------------|-------------|--------------------------|
| Bing Images         | No          | Works in China, 50+/page |
| Sogou Images        | No          | China alternative        |
| Unsplash API        | Yes (free)  | High quality, international |
| Pexels API          | Yes (free)  | High quality, international |
| Wikipedia Commons   | No          | CC-licensed, often blocked in China |

## Setup

```bash
# Install dependency
pip install -r requirements.txt

# Optional: set API keys for high-quality sources
$env:UNSPLASH_ACCESS_KEY = "your_key"
$env:PEXELS_API_KEY = "your_key"
```

## Usage Flow

```bash
# Step 1: Search and download
python scripts/search_images.py "gym treadmill" --max 20 -o ./downloads

# Step 2: Generate manifest
python scripts/rename_by_vision.py ./downloads/gym_treadmill

# Step 3: Give manifest to AI agent
# Agent reads manifest -> analyzes each image with vision model -> renames files
```

## For Agent Use

When user asks to search/download/rename images:
1. Run `search_images.py` with the query
2. Run `rename_by_vision.py` on the output folder
3. Read the `rename_manifest.json`
4. Use `image` tool to analyze each image
5. Use `exec` tool to rename files: `Rename-Item -Path "<old>" -NewName "<new>"`
