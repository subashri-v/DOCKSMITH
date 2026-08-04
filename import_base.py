import os, json, tarfile, hashlib, io, subprocess, shutil, tempfile

DOCKSMITH_DIR = os.path.expanduser("~/.docksmith")
IMAGES_DIR = os.path.join(DOCKSMITH_DIR, "images")
LAYERS_DIR = os.path.join(DOCKSMITH_DIR, "layers")
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(LAYERS_DIR, exist_ok=True)

# Pull via docker if available, else use skopeo
import subprocess
tmp = tempfile.mkdtemp()
try:
    subprocess.run(["skopeo", "copy",
        "docker://alpine:3.18",
        f"oci:{tmp}/alpine:3.18"], check=True)
    # Convert OCI layers to docksmith layers
    with open(f"{tmp}/alpine/index.json") as f:
        index = json.load(f)
    digest = index["manifests"][0]["digest"].replace("sha256:", "")
    with open(f"{tmp}/alpine/blobs/sha256/{digest}") as f:
        mf = json.load(f)

    layers_out = []
    for l in mf["layers"]:
        ldigest = l["digest"].replace("sha256:", "")
        src = f"{tmp}/alpine/blobs/sha256/{ldigest}"
        with open(src, "rb") as f:
            data = f.read()
        dest = os.path.join(LAYERS_DIR, ldigest + ".tar")
        with open(dest, "wb") as f:
            f.write(data)
        layers_out.append({
            "digest": "sha256:" + ldigest,
            "size": len(data),
            "createdBy": "alpine base layer"
        })

    manifest = {
        "name": "alpine", "tag": "3.18",
        "digest": "",
        "created": "2024-01-01T00:00:00+00:00",
        "config": {"Env": [], "Cmd": ["/bin/sh"], "WorkingDir": ""},
        "layers": layers_out
    }
    tmp2 = dict(manifest); tmp2["digest"] = ""
    digest_val = "sha256:" + hashlib.sha256(
        json.dumps(tmp2, sort_keys=True).encode()).hexdigest()
    manifest["digest"] = digest_val
    with open(os.path.join(IMAGES_DIR, "alpine_3.18.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("alpine:3.18 imported successfully.")
finally:
    shutil.rmtree(tmp)
