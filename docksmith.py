#!/usr/bin/env python3
import sys
import argparse

def cmd_build(args):
    from engine.builder import build
    name, _, tag = args.tag.partition(":")
    tag = tag or "latest"
    build(args.context, name, tag, no_cache=args.no_cache)

def cmd_images(args):
    from engine.image import list_images
    images = list_images()
    print(f"{'NAME':<20} {'TAG':<15} {'ID':<15} {'CREATED'}")
    for m in images:
        short_id = m.get("digest", "")
        short_id = short_id[7:19] if short_id.startswith("sha256:") else short_id[:12]
        print(f"{m['name']:<20} {m['tag']:<15} {short_id:<15} {m.get('created','')}")

def cmd_rmi(args):
    from engine.image import delete_image
    name, _, tag = args.name_tag.partition(":")
    tag = tag or "latest"
    delete_image(name, tag)
    print(f"Deleted {args.name_tag}")

def cmd_run(args):
    from engine.image import load_image
    from engine.runtime import run_container
    name, _, tag = args.name_tag.partition(":")
    tag = tag or "latest"
    manifest = load_image(name, tag)
    env_overrides = {}
    for item in (args.env or []):
        k, _, v = item.partition("=")
        env_overrides[k] = v
    cmd_override = args.cmd or None
    exit_code = run_container(manifest, cmd_override, env_overrides)
    print(f"Container exited with code {exit_code}")
    sys.exit(exit_code)

def main():
    parser = argparse.ArgumentParser(prog="docksmith")
    sub = parser.add_subparsers(dest="command")

    # build
    p_build = sub.add_parser("build")
    p_build.add_argument("-t", dest="tag", required=True)
    p_build.add_argument("--no-cache", action="store_true")
    p_build.add_argument("context", nargs="?", default=".")
    p_build.set_defaults(func=cmd_build)

    # images
    p_images = sub.add_parser("images")
    p_images.set_defaults(func=cmd_images)

    # rmi
    p_rmi = sub.add_parser("rmi")
    p_rmi.add_argument("name_tag")
    p_rmi.set_defaults(func=cmd_rmi)

    # run
    p_run = sub.add_parser("run")
    p_run.add_argument("name_tag")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER, default=None)
    p_run.add_argument("-e", dest="env", action="append")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)

if __name__ == "__main__":
    main()