Docksmith
A lightweight, content-addressable container engine built from scratch.

Features
Filesystem Isolation: Uses chroot and Linux namespaces.
Content-Addressable Storage: Layers are stored as SHA-256 hashes.
Build Caching: Deterministic builds with [CACHE HIT] logic.

How to Run
Import Base Image: python3 import_base.py
Build an Image: python3 docksmith.py build -t myapp:latest sample/
Run a Container: python3 docksmith.py run myapp:latest
