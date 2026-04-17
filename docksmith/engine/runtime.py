import os
import subprocess
import tempfile
import shutil

from engine.layer import extract_layer

def assemble_rootfs(layers: list, tmpdir: str):
    """Extract all layers in order into tmpdir."""
    for layer in layers:
        extract_layer(layer["digest"], tmpdir)

def run_container(manifest: dict, cmd_override: list = None,
                  env_overrides: dict = None) -> int:
    """
    Assemble rootfs, isolate process, run command.
    Returns exit code.
    """
    config  = manifest.get("config", {})
    layers  = manifest.get("layers", [])
    img_env = {}
    for item in config.get("Env", []):
        k, _, v = item.partition("=")
        img_env[k] = v
    if env_overrides:
        img_env.update(env_overrides)

    workdir = config.get("WorkingDir", "/")
    cmd     = cmd_override or config.get("Cmd")
    if not cmd:
        raise ValueError("No CMD defined and no command provided.")

    tmpdir = tempfile.mkdtemp(prefix="docksmith_")
    try:
        assemble_rootfs(layers, tmpdir)
        _ensure_dirs(tmpdir)
        exit_code = _run_isolated(tmpdir, cmd, img_env, workdir)
        return exit_code
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def _ensure_dirs(rootfs: str):
    """Ensure minimum required dirs exist inside rootfs."""
    for d in ["proc", "sys", "dev", "tmp", "etc"]:
        os.makedirs(os.path.join(rootfs, d), exist_ok=True)
    
    # --- ADD THIS LINE ---
    # Copy host DNS settings so 'apk' can resolve URLs
    if os.path.exists("/etc/resolv.conf"):
        shutil.copy("/etc/resolv.conf", os.path.join(rootfs, "etc/resolv.conf"))
        
def _run_isolated(rootfs: str, cmd: list, env: dict, workdir: str) -> int:
    """
    Use unshare + chroot for isolation.
    unshare --mount --pid --fork --map-root-user chroot <rootfs> <cmd>
    """
    env_list = [f"{k}={v}" for k, v in env.items()]
    env_list.append(f"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")

    # Build the command to run inside chroot
    inner_cmd = []
    if workdir and workdir != "/":
        # Use sh -c to cd first
        shell_cmd = f"cd {workdir} && exec " + " ".join(
            _shell_quote(c) for c in cmd
        )
        inner_cmd = ["sh", "-c", shell_cmd]
    else:
        inner_cmd = cmd

    full_cmd = [
        "unshare",
        "--mount",
        "--pid",
        "--fork",
        "--map-root-user",
        "chroot",
        rootfs,
    ] + inner_cmd

    result = subprocess.run(
        full_cmd,
        env=dict(item.split("=", 1) for item in env_list if "=" in item),
    )
    return result.returncode

def _shell_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)