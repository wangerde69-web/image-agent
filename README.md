# ImageAgent

AI-powered image search, download, and content-based renaming.

Given a search query, automatically search the web for images -> download to local folder -> use vision AI to analyze each image's content -> rename files based on what they contain.

---

## Features

- Multi-source search: Bing Images (works in China), Unsplash API, Pexels API, Sogou, Wikipedia
- Batch download with automatic deduplication
- Vision-based auto-rename via AI model
- Zero-config start: works without API keys (Bing and Wikipedia are free)
- Cross-platform: Windows (PowerShell), Linux, macOS

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Search and download images (no API key needed)

```bash
python scripts/search_images.py "gym treadmill" --max 20 -o ./downloads
```

### 3. Generate rename manifest

```bash
python scripts/rename_by_vision.py ./downloads/gym_treadmill
```

### 4. Let AI rename by vision (give manifest to agent)

Share the `rename_manifest.json` with your AI agent, which will:
- Analyze each image using vision model
- Rename files by content
- Example: `img_001.jpg` -> `treadmill_running_machine.jpg`

### 5. One-command full pipeline

```bash
python scripts/search_images.py "gym treadmill" --max 20 -o ./downloads --auto-rename
```

---

## Optional: Configure High-Quality Sources

### Unsplash (free API key, 50 req/hr)

1. Get a key at https://unsplash.com/developers
2. Set environment variable:
   ```bash
   # Windows PowerShell
   $env:UNSPLASH_ACCESS_KEY="your_key_here"
   
   # Linux / macOS
   export UNSPLASH_ACCESS_KEY="your_key_here"
   ```

### Pexels (free API key, 200 req/month)

1. Get a key at https://www.pexels.com/api/
2. Set environment variable:
   ```bash
   $env:PEXELS_API_KEY="your_key_here"
   ```

---

## Workflow

```
User query
    |
    v
search_images.py
    |  1. Bing Images (primary - works in China)
    |  2. Sogou Images (China alternative)
    |  3. Unsplash (high quality, needs API key)
    |  4. Pexels (high quality, needs API key)
    |  5. Wikipedia Commons (international fallback)
    |
    v
Downloaded to ./downloads/{query_slug}/
    |
    v
rename_by_vision.py -> generates rename_manifest.json
    |
    v
Agent analyzes each image with vision model
    |
    v
Files renamed by content
Example: img_001.jpg -> treadmill_running_machine.jpg
```

---

## CLI Arguments

### search_images.py

| Argument      | Description                      |
|---------------|----------------------------------|
| `query`       | Search query (required)          |
| `--max N`     | Max images to download (default: 20) |
| `--output/-o` | Output directory (default: ./downloads) |
| `--auto-rename` | Also run vision rename after download |

### rename_by_vision.py

| Argument      | Description                      |
|---------------|----------------------------------|
| `folder`      | Folder containing images (required) |
| `--output/-o` | Manifest output path            |

---

## File Structure

```
image-agent/
鈹溾攢鈹€ SKILL.md                      <- Agent skill metadata
鈹溾攢鈹€ scripts/
鈹?  鈹溾攢鈹€ search_images.py           <- Search + download engine
鈹?  鈹斺攢鈹€ rename_by_vision.py        <- Manifest generator (AI does rename)
鈹溾攢鈹€ requirements.txt              <- Python dependency (requests)
鈹斺攢鈹€ README.md                     <- This file
```

---

## Image Sources

| Source            | Needs Key | Quality | Notes                      |
|-------------------|-----------|---------|----------------------------|
| Bing Images       | No        | Medium  | Works well in China        |
| Sogou Images      | No        | Medium  | China alternative          |
| Unsplash API      | Yes (free)| High    | International              |
| Pexels API        | Yes (free)| High    | International              |
| Wikipedia Commons | No        | Medium  | Often blocked in China     |

---

## License

MIT
