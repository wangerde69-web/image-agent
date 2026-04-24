#!/usr/bin/env python3
import subprocess, base64, json, os, tempfile

REPO = "wangerde69-web/image-agent"
BRANCH = "master"

def gh_run(method, path, data=None, jq=None):
    cmd = ["gh", "api", "-X", method, f"repos/{REPO}/{path}"]
    if jq:
        cmd += ["--jq", jq]
    if data is not None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            tmp = f.name
        try:
            cmd += ["--input", tmp]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, err = p.communicate()
            if p.returncode != 0:
                raise RuntimeError(f"{method} {path}: {err}")
            return json.loads(out) if out else {}
        finally:
            try:
                os.unlink(tmp)
            except:
                pass
    else:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = p.communicate()
        if p.returncode != 0:
            raise RuntimeError(f"{method} {path}: {err}")
        txt = out.strip()
        if txt.startswith(("{", "[")):
            return json.loads(txt)
        return txt

def create_blob(content_bytes):
    return gh_run("POST", "git/blobs", {"content": base64.b64encode(content_bytes).decode(), "encoding": "base64"})["sha"]

LOCAL_DIR = "C:/Users/Administrator/clawd/image-agent"

# Get HEAD
commit_sha = gh_run("GET", "git/ref/heads/master", jq=".object.sha")
tree_sha = gh_run("GET", f"git/commits/{commit_sha}", jq=".tree.sha")
print(f"Current commit: {commit_sha}")
print(f"Current tree: {tree_sha}")

# Get current tree entries (for reference)
current_tree = gh_run("GET", f"git/trees/{tree_sha}")
current_files = {t["path"]: t["sha"] for t in current_tree["tree"] if t["type"] == "blob"}
print(f"Current files: {list(current_files.keys())}")

# Collect ALL files to push (include dotfiles manually)
exclude_dirs = {".git", "test_downloads", "node_modules", "__pycache__"}
files_to_push = {}  # path -> local_path

# Walk directory
for root, dirs, files in os.walk(LOCAL_DIR):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for fname in files:
        fpath = os.path.join(root, fname)
        rel = os.path.relpath(fpath, LOCAL_DIR).replace(os.sep, "/")
        if ".git" in rel or rel == "push_to_github.py":
            continue
        files_to_push[rel] = fpath

# Also add .gitignore manually
gitignore_path = os.path.join(LOCAL_DIR, ".gitignore")
if os.path.exists(gitignore_path):
    files_to_push[".gitignore"] = gitignore_path

print(f"Files to push: {list(files_to_push.keys())}")

# Create blobs and build tree entries
new_entries = []
for path in sorted(files_to_push.keys()):
    local_path = files_to_push[path]
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            content = f.read()
        blob_sha = create_blob(content)
        new_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})
        print(f"  + {path}")
    else:
        print(f"  ! {path} (not found, skipping)")

print(f"Total entries: {len(new_entries)}")
new_tree = gh_run("POST", "git/trees", {"base_tree": tree_sha, "tree": new_entries})
new_tree_sha = new_tree["sha"]
print(f"New tree: {new_tree_sha}")

new_commit = gh_run("POST", "git/commits", {
    "message": (
        "feat: add v2 search with query expansion + perceptual dedup + auto_rename\n\n"
        "- search_images_v2.py: multi-source search with query expansion + pHash dedup\n"
        "- auto_rename.py: vision-based file renaming via API\n"
        "- Updated SKILL.md, README.md, requirements.txt, .gitignore"
    ),
    "tree": new_tree_sha,
    "parents": [commit_sha]
})
new_commit_sha = new_commit["sha"]
print(f"New commit: {new_commit_sha}")

gh_run("PATCH", "git/refs/heads/master", {"sha": new_commit_sha})
print("Pushed to GitHub!")
