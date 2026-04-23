#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

"""
Prepare a folder of images for vision-based renaming.
Outputs a manifest JSON, then the agent uses its `image` tool to 
analyze each image and rename files based on content.

Usage:
    python scripts/rename_by_vision.py ./downloads/gym_fitness_equipment
    
The agent will then:
    1. Read the manifest
    2. For each image, use `image` tool to analyze content
    3. Rename the file based on what the vision model sees
"""

import argparse
import json
import os
import sys
from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def scan_folder(folder_path: Path) -> list[dict]:
    """Return list of image entries with path, name, size."""
    images = []
    for f in sorted(folder_path.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            images.append({
                "index": len(images) + 1,
                "filename": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
            })
    return images


def main():
    parser = argparse.ArgumentParser(
        description="Scan a folder of images and prepare a manifest for vision-based renaming."
    )
    parser.add_argument("folder", help="Path to folder containing images")
    parser.add_argument("--output", "-o", help="Output manifest path (default: <folder>/rename_manifest.json)")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"❌ Error: {folder} is not a directory or does not exist.")
        sys.exit(1)

    images = scan_folder(folder)
    if not images:
        print(f"❌ No images found in {folder}")
        print(f"   Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    manifest = {
        "folder": str(folder),
        "total": len(images),
        "images": images,
        "instructions": (
            "For each image, use the `image` tool to analyze its content. "
            "Then rename the file to a descriptive name based on what you see. "
            "Example: 'img_001.jpg' → 'treadmill_running_machine.jpg'. "
            "Use the `exec` tool to run: "
            "Rename-Item -Path 'C:\\path\\to\\img_001.jpg' -NewName 'treadmill_running_machine.jpg' "
            "(Windows PowerShell syntax)."
        ),
    }

    output_path = Path(args.output) if args.output else folder / "rename_manifest.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n📋 Found {len(images)} images in {folder}")
    print(f"📄 Manifest: {output_path}")
    print("\n🔄 Next step — give this manifest to the agent to rename by vision:")
    print(f"   python scripts/rename_by_vision.py {folder}\n")
    print("Images:")
    for img in images:
        size_kb = img["size_bytes"] / 1024
        print(f"  [{img['index']:2d}] {img['filename']} ({size_kb:.1f} KB)")

    print(f"\n✅ Manifest ready. Copy the content of {output_path} to the agent,")
    print("   or share the folder path so the agent can scan and rename.")


if __name__ == "__main__":
    main()
