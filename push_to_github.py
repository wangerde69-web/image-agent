#!/usr/bin/env python3
"""
Push image-agent files to GitHub using gh CLI token.
Bypasses git push (which fails due to network issues in China).
"""
import subprocess
import base64
import json
import os
import re

REPO = "wangerde69-web/image-agent"
BRANCH = "master"
GH_TOKEN_CMD = ["gh", "api", "user", "--jq", ".login"]

def run(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()

def gh_api(method, path, data=None):
    cmd = ["gh", "api", "-X", method, f"repos/{REPO}/{path}"]
    if data:
        cmd += ["--input", "-"]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate(input=json.dumps(data))
        if proc.returncode != 0:
            raise RuntimeError(f"gh api failed: {stderr}")
        return json.loads(stdout) if stdout else {}
    else:
        return json.loads(run(cmd))

def get_sha(path):
    return run(["gh", "api", f"repos/{REPO}/contents/{path}", "--ref", BRANCH, "--jq", ".sha"])

def create_blob(content_bytes):
    data = {"content": base64.b64encode(content_bytes).decode(), "encoding": "base64"}
    return gh_api("POST", "git/blobs", data)["sha"]

def get_tree_sha(commit_sha):
    return run(["gh", "api", f"repos/{REPO}/git/commits/{commit_sha}", "--jq", ".tree.sha"])

def create_tree(blob_items, base_tree_sha):
    tree = [{"path": path, "mode": "100644", "type": "blob", "sha": sha} for path, sha in blob_items]
    return gh_api("POST", "git/trees", {"base_tree": base_tree_sha, "tree": tree})["sha"]

def create_commit(message, tree_sha, parent_sha):
    return gh_api("POST", "git/commits", {
        "message": message,
        "tree": tree_sha,
        "parents": [parent_sha]
    })["sha"]

def update_ref(new_sha):
    subprocess.run(["gh", "api", "-X", "PATCH", f"repos/{REPO}/git/refs/heads/{BRANCH}",
                   "--input", "-"], input=json.dumps({"sha": new_sha}), text=True)

def push_dir(base_path):
    # Get current branch tip
    branch = gh_api("GET", f"git/ref/heads/{BRANCH}")
    commit_sha = branch["object"]["sha"]
    print(f"Current commit: {commit_sha}")

    # Get current tree
    tree_sha = get_tree_sha(commit_sha)
    print(f"Current tree: {tree_sha}")

    # Build file list (exclude .git, test_downloads)
    blob_items = []
    exclude_dirs = {".git", "test_downloads", "node_modules", "__pycache__"}
    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, base_path).replace(os.sep, "/")
            # Skip .git files
            if ".git" in rel:
                continue
            print(f"  Adding: {rel}")
            with open(fpath, "rb") as f:
                content = f.read()
            blob_sha = create_blob(content)
            blob_items.append((rel, blob_sha))

    # Create new tree
    new_tree_sha = create_tree(blob_items, tree_sha)
    print(f"New tree: {new_tree_sha}")

    # Create commit
    new_commit_sha = create_commit(
        "feat: add v2 search with query expansion + perceptual dedup + auto_rename\n\n"
        "- search_images_v2.py: multi-source search with query expansion + pHash dedup\n"
        "- auto_rename.py: vision-based file renaming via API\n"
        "- Updated SKILL.md, README.md, requirements.txt",
        new_tree_sha,
        commit_sha
    )
    print(f"New commit: {new_commit_sha}")

    # Update ref
    update_ref(new_commit_sha)
    print("Done! Pushed to GitHub.")

if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    push_dir(os.path.abspath(base))
