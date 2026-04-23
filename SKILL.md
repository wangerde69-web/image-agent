# ImageAgent Skill

**What it does**: Given a search query, automatically:
1. Searches the internet for relevant images (multiple free sources)
2. Downloads them to a local folder
3. Uses a vision AI model to analyze each image's content
4. Renames each file based on what it contains

**Trigger phrases**: 
- "搜索下载图片" / "search and download images"
- "根据内容给图片命名" / "rename images by content"
- "找一些关于 X 的图片" / "find images about X"
- "download and rename images"

---

## Architecture

```
image-agent/
├── SKILL.md              ← This file (skill metadata + usage instructions)
├── scripts/
│   ├── search_images.py  ← Core: search + download images
│   └── rename_by_vision.py ← Uses agent's vision tool to rename files
├── README.md
└── requirements.txt
```

## Pipeline

```
User query → search_images.py → download to ./downloads/{query}/ 
         → rename_by_vision.py (uses agent's image tool) 
         → files renamed by content
```

## Image Search Sources (in priority order)

1. **Wikipedia Commons** — No API key, CC-licensed, good variety
2. **Unsplash API** — Free tier (50 req/hr), high quality, needs `UNSPLASH_ACCESS_KEY`
3. **Pexels API** — Free tier (200 req/mo), high quality, needs `PEXELS_API_KEY`
4. **DuckDuckGo Images** — No API key, scraping-based, fallback

## 视觉重命名（Vision Rename）

这部分由 Agent（我）来完成。当图片下载完成后：

1. 运行 `python scripts/rename_by_vision.py <文件夹>` 生成 `rename_manifest.json`
2. 我用 vision 模型分析每张图片的内容
3. 根据内容自动重命名文件

**Agent 操作示例**：
```
我：搜索并下载"gym equipment"图片
Agent：运行 search_images.py，下载到 ./downloads/gym_equipment/
Agent：运行 rename_by_vision.py 生成清单
Agent：用 vision 模型分析 img_001.jpg → 跑步机照片
Agent：Rename-Item img_001.jpg → treadmill_running_machine.jpg
（对每张图重复）
```

**注意**：Vision rename 需要 Agent 配置了支持图像分析的模型（如 Claude、Gemini 等）。如果模型不支持图像分析，Agent 会跳过重命名步骤。

## Environment

- **Python**: 3.8+
- **OS**: Windows, Linux, macOS
- **No GPU required** (vision model runs via agent's image tool, not locally)
