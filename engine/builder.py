import os
import glob
import json
import time
import hashlib
import shutil
import tempfile

from engine import image as img_mod
from engine import layer as lyr_mod
from engine import cache as cache_mod
from engine import runtime as rt_mod
from datetime import datetime, timezone

def parse_docksmithfile(path: str) -> list:
    """Returns list of (lineno, instruction, args)."""
    instructions = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            instr = parts[0].upper()
            args  = parts[1] if len(parts) > 1 else ""
            valid = {"FROM", "COPY", "RUN", "WORKDIR", "ENV", "CMD"}
            if instr not in valid:
                raise SyntaxError(f"Line {lineno}: Unknown instruction '{instr}'")
            instructions.append((lineno, instr, args))
    return instructions

def build(context_dir: str, name: str, tag: str, no_cache: bool = False):
    img_mod.init_dirs()
    dsfile = os.path.join(context_dir, "Docksmithfile")
    if not os.path.exists(dsfile):
        raise FileNotFoundError(f"No Docksmithfile found in {context_dir}")

    instructions = parse_docksmithfile(dsfile)

    # Build state
    base_manifest = None
    layers        = []
    config        = {"Env": [], "Cmd": None, "WorkingDir": ""}
    env           = {}
    workdir       = ""
    prev_digest   = ""
    cache_busted  = no_cache
    step_total    = len(instructions)
    start_total   = time.time()

    all_cache_hits = not no_cache

    for step_idx, (lineno, instr, args) in enumerate(instructions, 1):
        print(f"Step {step_idx}/{step_total} : {instr} {args}", end="", flush=True)

        # ── FROM ──────────────────────────────────────────────────────────
        if instr == "FROM":
            base_name, _, base_tag = args.partition(":")
            base_tag = base_tag or "latest"
            base_manifest = img_mod.load_image(base_name, base_tag)
            layers = list(base_manifest.get("layers", []))
            cfg    = base_manifest.get("config", {})
            env    = {}
            for item in cfg.get("Env", []):
                k, _, v = item.partition("=")
                env[k] = v
            workdir = cfg.get("WorkingDir", "")
            config  = {"Env": list(cfg.get("Env", [])),
                       "Cmd": cfg.get("Cmd"),
                       "WorkingDir": workdir}
            prev_digest = base_manifest["digest"]
            print()  # newline, no cache status for FROM
            continue

        # ── WORKDIR ───────────────────────────────────────────────────────
        if instr == "WORKDIR":
            workdir = args
            config["WorkingDir"] = workdir
            
            # --- ADD THIS LOGIC ---
            # Create a new layer that just contains the directory
            tar_bytes = lyr_mod.make_layer_tar({f"{workdir.lstrip('/')}/.keep": (b"", 0o644)})
            digest, size = lyr_mod.store_layer(tar_bytes)
            
            layers.append({
                "digest": digest,
                "size": size,
                "createdBy": f"WORKDIR {args}"
            })
            prev_digest = digest
            # ----------------------
            print()
            continue

        # ── ENV ───────────────────────────────────────────────────────────
        if instr == "ENV":
            k, _, v = args.partition("=")
            env[k.strip()] = v.strip()
            # Rebuild Env list
            config["Env"] = [f"{k}={v}" for k, v in env.items()]
            print()
            continue

        # ── CMD ───────────────────────────────────────────────────────────
        if instr == "CMD":
            config["Cmd"] = json.loads(args)
            print()
            continue

        # ── COPY ──────────────────────────────────────────────────────────
        if instr == "COPY":
            t0 = time.time()
            src_pattern, _, dest = args.partition(" ")
            dest = dest.strip()

            # Collect matching source files
            matched = sorted(glob.glob(
                os.path.join(context_dir, src_pattern), recursive=True
            ))
            src_files = {}
            for abspath in matched:
                if os.path.isfile(abspath):
                    rel = os.path.relpath(abspath, context_dir)
                    # --- UPDATE THESE LINES ---
                    mode = os.stat(abspath).st_mode
                    with open(abspath, "rb") as f:
                        src_files[rel] = (f.read(), mode) # Store as tuple

            # Hash source files for cache key
            copy_hashes = []
            for rel in sorted(src_files.keys()):
                # --- UPDATE THIS LINE: Add [0] to get the content bytes ---
                h = hashlib.sha256(src_files[rel][0]).hexdigest()
                copy_hashes.append(h)

            cache_key = cache_mod.compute_cache_key(
                prev_digest, f"COPY {args}", workdir, env, copy_hashes
            )

            cached_digest = None if cache_busted else cache_mod.lookup(cache_key)
            if cached_digest:
                elapsed = time.time() - t0
                print(f" [CACHE HIT] {elapsed:.2f}s")
                prev_digest = cached_digest
                # Find and append layer
                layers.append({
                    "digest": cached_digest,
                    "size": os.path.getsize(
                        os.path.join(img_mod.LAYERS_DIR,
                                     cached_digest.replace("sha256:", "") + ".tar")
                    ),
                    "createdBy": f"COPY {args}"
                })
            else:
                cache_busted = True
                # Build tar delta
                tar_files = {}
                for rel, tuple_data in src_files.items():
                    archive_path = os.path.join(dest.lstrip("/"), rel).lstrip("/")
                    # --- UPDATE THIS LINE ---
                    tar_files[archive_path] = tuple_data # Passing (content, mode)


                tar_bytes = lyr_mod.make_layer_tar(tar_files)
                digest, size = lyr_mod.store_layer(tar_bytes)
                if not no_cache:
                    cache_mod.store(cache_key, digest)
                elapsed = time.time() - t0
                print(f" [CACHE MISS] {elapsed:.2f}s")
                prev_digest = digest
                layers.append({
                    "digest": digest,
                    "size": size,
                    "createdBy": f"COPY {args}"
                })
            continue

        # ── RUN ───────────────────────────────────────────────────────────
        if instr == "RUN":
            t0 = time.time()
            cache_key = cache_mod.compute_cache_key(
                prev_digest, f"RUN {args}", workdir, env
            )

            cached_digest = None if cache_busted else cache_mod.lookup(cache_key)
            if cached_digest:
                elapsed = time.time() - t0
                print(f" [CACHE HIT] {elapsed:.2f}s")
                prev_digest = cached_digest
                layers.append({
                    "digest": cached_digest,
                    "size": os.path.getsize(
                        os.path.join(img_mod.LAYERS_DIR,
                                     cached_digest.replace("sha256:", "") + ".tar")
                    ),
                    "createdBy": f"RUN {args}"
                })
            else:
                cache_busted = True
                # Assemble current rootfs
                tmpdir = tempfile.mkdtemp(prefix="docksmith_build_")
                try:
                    rt_mod.assemble_rootfs(layers, tmpdir)
                    rt_mod._ensure_dirs(tmpdir)

                    # Snapshot before
                    before_files, before_links = lyr_mod.collect_dir_files(tmpdir)

                    # Run command in isolation
                    run_env = dict(env)
                    run_env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
                    exit_code = rt_mod._run_isolated(
                        tmpdir, ["sh", "-c", args], run_env, workdir
                    )
                    if exit_code != 0:
                        raise RuntimeError(f"RUN failed with exit code {exit_code}: {args}")

                    # Snapshot after — delta only
                    after_files, after_links = lyr_mod.collect_dir_files(tmpdir)

                    delta_files = {
                        path: tuple_data 
                        for path, tuple_data in after_files.items()
                        if path not in before_files or before_files[path] != tuple_data
                    }
                    delta_links = {
                        path: target
                        for path, target in after_links.items()
                        if path not in before_links or before_links[path] != target
                    }

                    tar_bytes = lyr_mod.make_layer_tar(delta_files, delta_links)
                    digest, size = lyr_mod.store_layer(tar_bytes)
                    if not no_cache:
                        cache_mod.store(cache_key, digest)

                    elapsed = time.time() - t0
                    print(f" [CACHE MISS] {elapsed:.2f}s")
                    prev_digest = digest
                    layers.append({
                        "digest": digest,
                        "size": size,
                        "createdBy": f"RUN {args}"
                    })
                finally:
                    shutil.rmtree(tmpdir, ignore_errors=True)
            continue

    # ── Save final manifest ───────────────────────────────────────────────
    from datetime import datetime, timezone
    created_time = None
    
    # Requirement: Preserved on cache-hit rebuilds 
    if all_cache_hits:
        try:
            # Look up the image that already exists on disk [cite: 19]
            old_manifest = img_mod.load_image(name, tag)
            created_time = old_manifest.get("created")
        except Exception:
            # If the image doesn't exist yet, we'll fall through to 'now'
            pass

    # If it's a CACHE MISS or first build, use current time 
    if not created_time:
        created_time = datetime.now(timezone.utc).isoformat()

    manifest = {
        "name":    name,
        "tag":     tag,
        "digest":  "", # Keep empty for hash calculation [cite: 70]
        "created": created_time,
        "config":  config,
        "layers":  layers,
    }
    
    # This will now produce the same hash every time if hits occur 
    digest = img_mod.save_image(manifest)
    elapsed_total = time.time() - start_total
    short = digest[7:19]
    print(f"\nSuccessfully built {short} {name}:{tag} ({elapsed_total:.2f}s)")
    return digest