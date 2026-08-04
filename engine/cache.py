import os
import json
import hashlib

DOCKSMITH_DIR = os.path.expanduser("~/.docksmith")
CACHE_DIR  = os.path.join(DOCKSMITH_DIR, "cache")
LAYERS_DIR = os.path.join(DOCKSMITH_DIR, "layers")

def _cache_index_path():
    return os.path.join(CACHE_DIR, "index.json")

def load_index() -> dict:
    p = _cache_index_path()
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}

def save_index(index: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_index_path(), "w") as f:
        json.dump(index, f, indent=2)

def compute_cache_key(prev_digest: str, instruction: str,
                      workdir: str, env: dict,
                      copy_hashes: list = None) -> str:
    h = hashlib.sha256()
    h.update(prev_digest.encode())
    h.update(instruction.encode())
    h.update(workdir.encode())
    # ENV: sorted key order
    env_str = "&".join(f"{k}={v}" for k, v in sorted(env.items()))
    h.update(env_str.encode())
    # COPY: file hashes in sorted path order
    if copy_hashes:
        for fhash in copy_hashes:
            h.update(fhash.encode())
    return h.hexdigest()

def lookup(key: str) -> str | None:
    """Returns layer digest if cache hit and layer file exists, else None."""
    index = load_index()
    digest = index.get(key)
    if digest is None:
        return None
    hex_ = digest.replace("sha256:", "")
    layer_path = os.path.join(LAYERS_DIR, hex_ + ".tar")
    if not os.path.exists(layer_path):
        return None
    return digest

def store(key: str, digest: str):
    index = load_index()
    index[key] = digest
    save_index(index)