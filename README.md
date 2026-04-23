# ImageAgent

**AI-powered image search, download, and content-based renaming.**

给定一个搜索词，自动从全网搜索图片 → 下载到本地 → 用视觉 AI 分析每张图的内容 → 按内容自动重命名文件。

---

## 功能特点

- 🔍 **多源搜索**：Wikipedia Commons（免 key）、Unsplash、Pexels（需免费 API key）、DuckDuckGo（备选）
- ⬇️ **批量下载**：自动去重，按需限制数量，带进度显示
- 👁️ **视觉重命名**：用视觉模型分析图片内容，自动生成描述性文件名
- 📦 **零配置起步**：无 API Key 也能用（Wikipedia Commons + DuckDuckGo 兜底）
- 🌐 **全平台**：Windows (PowerShell)、Linux、macOS

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 搜索并下载图片（免 Key）

```bash
python scripts/search_images.py "gym fitness equipment" --max 20 -o ./downloads
```

### 3. 视觉分析 + 自动重命名

```bash
python scripts/rename_by_vision.py ./downloads/gym_fitness_equipment
```

然后把 `rename_manifest.json` 的内容发给 AI 助手（也就是这个 skill 的主人），让它用视觉模型分析每张图并重命名。

### 4. 一键全自动（下载 + 重命名）

```bash
python scripts/search_images.py "gym fitness equipment" --max 20 -o ./downloads --auto-rename
```

---

## 可选：配置高质量图片源

### Unsplash（免费 Key，50 req/hr）

1. 去 https://unsplash.com/developers 注册 App，获取 Access Key
2. 设置环境变量：
   ```bash
   # Windows PowerShell
   $env:UNSPLASH_ACCESS_KEY="your_key_here"
   
   # Linux / macOS
   export UNSPLASH_ACCESS_KEY="your_key_here"
   ```

### Pexels（免费 Key，200 req/月）

1. 去 https://www.pexels.com/api/ 注册，获取 API Key
2. 设置环境变量：
   ```bash
   $env:PEXELS_API_KEY="your_key_here"
   ```

---

## 工作流程

```
用户输入搜索词
    │
    ▼
search_images.py
    │  ① Wikipedia Commons（无 Key）
    │  ② Unsplash（有 Key 时）
    │  ③ Pexels（有 Key 时）
    │  ④ DuckDuckGo（备选兜底）
    │
    ▼
下载到 ./downloads/{query_slug}/
    │
    ▼
rename_by_vision.py → 生成 rename_manifest.json
    │
    ▼
Agent 用视觉模型分析每张图内容
    │
    ▼
按内容重命名文件
例: img_001.jpg → treadmill_running_machine.jpg
```

---

## 命令行参数

### search_images.py

| 参数 | 说明 |
|------|------|
| `query` | 搜索词（必填） |
| `--max N` | 最多下载 N 张（默认 20） |
| `--output/-o` | 输出目录（默认 ./downloads） |
| `--auto-rename` | 下载完后自动执行重命名流程 |
| `--quiet/-q` | 静默模式 |

### rename_by_vision.py

| 参数 | 说明 |
|------|------|
| `folder` | 图片文件夹路径（必填） |
| `--output/-o` | manifest 输出路径 |

---

## 文件结构

```
image-agent/
├── SKILL.md                      ← Skill 元数据（AI 使用说明）
├── scripts/
│   ├── search_images.py          ← 搜索 + 下载核心脚本
│   └── rename_by_vision.py       ← 生成清单（重命名由 Agent 执行）
├── requirements.txt              ← Python 依赖
└── README.md                     ← 本文件
```

---

## 图片来源说明

| 来源 | 需要 Key | 图片质量 | 授权 |
|------|---------|---------|------|
| Wikipedia Commons | ❌ | 中高 | CC 各种协议 |
| Unsplash | ✅ 免费 | 高 | Unsplash License |
| Pexels | ✅ 免费 | 高 | Pexels License |
| DuckDuckGo | ❌ | 中 | 取决于来源站 |

---

## License

MIT
