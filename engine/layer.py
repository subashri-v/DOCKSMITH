import os
import tarfile
import hashlib
import io

DOCKSMITH_DIR = os.path.expanduser("~/.docksmith")
LAYERS_DIR = os.path.join(DOCKSMITH_DIR, "layers")

def compute_sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def make_layer_tar(files: dict, symlinks: dict = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        all_paths = sorted(set(list(files.keys()) + list((symlinks or {}).keys())))
        for arcpath in all_paths:
            if symlinks and arcpath in symlinks:
                info = tarfile.TarInfo(name=arcpath)
                info.type   = tarfile.SYMTYPE
                info.linkname = symlinks[arcpath]
                info.mtime  = 0
                tar.addfile(info)
            else:
                # --- Ensure these four lines are indented inside the 'else' ---
                content, mode = files[arcpath] 
                info = tarfile.TarInfo(name=arcpath)
                info.size  = len(content)
                info.mode = mode  # This is the fix for the Permission Denied error!
                info.mtime = 0
                tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def store_layer(tar_bytes: bytes) -> tuple[str, int]:
    """Stores tar bytes, returns (digest, size)."""
    digest = compute_sha256(tar_bytes)
    hex_   = digest.replace("sha256:", "")
    os.makedirs(LAYERS_DIR, exist_ok=True)
    path = os.path.join(LAYERS_DIR, hex_ + ".tar")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(tar_bytes)
    return digest, len(tar_bytes)

def extract_layer(digest: str, target_dir: str):
    """Extract a stored layer into target_dir."""
    hex_  = digest.replace("sha256:", "")
    path  = os.path.join(LAYERS_DIR, hex_ + ".tar")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Layer not found on disk: {digest}")
    with tarfile.open(path, "r") as tar:
        tar.extractall(path=target_dir)

def collect_dir_files(src_dir: str) -> dict:
    files    = {} # Change this to store (content, mode)
    symlinks = {}
    for root, dirs, filenames in os.walk(src_dir, followlinks=False):
        for fname in sorted(filenames):
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, src_dir)
            if os.path.islink(abs_path):
                symlinks[rel_path] = os.readlink(abs_path)
            else:
                try:
                    mode = os.stat(abs_path).st_mode # Get permissions
                    with open(abs_path, "rb") as f:
                        files[rel_path] = (f.read(), mode) # Store as tuple
                except (PermissionError, OSError):
                    pass
    return files, symlinks