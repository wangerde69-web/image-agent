#!/usr/bin/env python3
import subprocess, base64, json, os, tempfile

REPO = "wangerde69-web/image-agent"

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

# Get current HEAD
commit_sha = gh_run("GET", "git/ref/heads/master", jq=".object.sha")
tree_sha = gh_run("GET", f"git/commits/{commit_sha}", jq=".tree.sha")
current_tree = gh_run("GET", f"git/trees/{tree_sha}")
current_files = {t["path"]: t["sha"] for t in current_tree["tree"] if t["type"] == "blob"}
print("Current files:", list(current_files.keys()))

# Files to remove from remote
to_remove = {"push_to_github.py", "push_final.py"}

# Collect local files (excluding helpers)
exclude_dirs = {".git", "test_downloads", "node_modules", "__pycache__"}
files_to_upload = {}

for root, dirs, files in os.walk(LOCAL_DIR):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for fname in files:
        fpath = os.path.join(root, fname)
        rel = os.path.relpath(fpath, LOCAL_DIR).replace(os.sep, "/")
        if rel.startswith("push_") or rel in to_remove:
            continue
        if ".git" in rel:
            continue
        files_to_upload[rel] = fpath

gitignore_path = os.path.join(LOCAL_DIR, ".gitignore")
if os.path.exists(gitignore_path):
    files_to_upload[".gitignore"] = gitignore_path

# Build new tree entries
new_entries = []

# Add all local files
for path in sorted(files_to_upload.keys()):
    local_path = files_to_upload[path]
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            content = f.read()
        blob_sha = create_blob(content)
        new_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})
        print(f"  + {path}")

# Keep current files that aren't being replaced AND aren't removed
for path, sha in sorted(current_files.items()):
    if path in files_to_upload:
        continue  # replaced by local version above
    if path in to_remove:
        print(f"  - {path} (removed)")
        continue  # don't include = deleted
    new_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
    print(f"  = {path} (kept)")

print(f"Total entries: {len(new_entries)}")
new_tree = gh_run("POST", "git/trees", {"base_tree": tree_sha, "tree": new_entries})
new_tree_sha = new_tree["sha"]
print(f"New tree: {new_tree_sha}")

new_commit = gh_run("POST", "git/commits", {
    "message": "chore: remove push helper scripts from repo",
    "tree": new_tree_sha,
    "parents": [commit_sha]
})
new_commit_sha = new_commit["sha"]
print(f"New commit: {new_commit_sha}")

gh_run("PATCH", "git/refs/heads/master", {"sha": new_commit_sha})
print("Done!")
