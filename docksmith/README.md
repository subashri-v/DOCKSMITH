# Docksmith
A lightweight, content-addressable container engine built from scratch.

## Features
* **Filesystem Isolation:** Uses `chroot` and Linux namespaces.
* **Content-Addressable Storage:** Layers are stored as SHA-256 hashes.
* **Build Caching:** Deterministic builds with [CACHE HIT] logic.

## How to Run
1. **Import Base Image:** `python3 import_base.py`
2. **Build an Image:** `python3 docksmith.py build -t myapp:latest sample/`
3. **Run a Container:**
   `python3 docksmith.py run myapp:latest`