#!/usr/bin/env python3
import argparse
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys

import jinja2

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
DEBIAN = os.path.join(REPO, "debian")
TEMPLATES = os.path.join(DEBIAN, "templates")
BUILD_ROOT = os.path.join(REPO, "build")
OUTDIR = os.path.join(BUILD_ROOT, "dist")
STAGING = os.path.join(BUILD_ROOT, "staging")
ASSETS_DIR = "/var/lib/scripturesstudio/assets"
COMMON_GLOB = "back*.jpg back*.mp4".split()
CHAPTER_RE = re.compile(r"^(\d{3})\.(jpg|mp3|mp4)$")
VERSION = "1.0"
MAINTAINER = "Reuben Institute <reubeninstitute@gmail.com>"

JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES),
    keep_trailing_newline=True,
)


def discover_chapters():
    chapters = {}
    for name in os.listdir(REPO):
        m = CHAPTER_RE.match(name)
        if m:
            chapters.setdefault(m.group(1), []).append(name)
    return chapters


def discover_common_files():
    files = []
    for pattern in COMMON_GLOB:
        files.extend(os.path.basename(p) for p in glob.glob(os.path.join(REPO, pattern)))
    return sorted(set(files))


def write_control(pkg_root, pkg, description, depends=None):
    debian_dir = os.path.join(pkg_root, "DEBIAN")
    os.makedirs(debian_dir, exist_ok=True)
    os.chmod(debian_dir, 0o755)

    size_kb = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, files in os.walk(pkg_root)
        if "DEBIAN" not in dirpath.split(os.sep)
        for f in files
    ) // 1024

    rendered = JINJA_ENV.get_template("control.j2").render(
        pkg=pkg,
        version=VERSION,
        maintainer=MAINTAINER,
        size_kb=size_kb,
        depends=depends or [],
        description=description,
    )
    control = os.path.join(debian_dir, "control")
    with open(control, "w") as fh:
        fh.write(rendered)
    os.chmod(control, 0o644)
    return debian_dir


def embed_scripts(debian_dir):
    for name in ("bump-version.sh", "fast-build.sh"):
        src = os.path.join(DEBIAN, name)
        dst = os.path.join(debian_dir, name)
        shutil.copy(src, dst)
        os.chmod(dst, 0o755)


def write_lintian_override(pkg_root, pkg):
    overrides_dir = os.path.join(pkg_root, "usr", "share", "lintian", "overrides")
    os.makedirs(overrides_dir, exist_ok=True)
    os.chmod(os.path.join(pkg_root, "usr"), 0o755)
    os.chmod(os.path.join(pkg_root, "usr", "share"), 0o755)
    os.chmod(os.path.join(pkg_root, "usr", "share", "lintian"), 0o755)
    os.chmod(overrides_dir, 0o755)

    override_file = os.path.join(overrides_dir, pkg)
    with open(override_file, "w") as fh:
        fh.write(f"{pkg}: unknown-control-file [bump-version.sh]\n")
        fh.write(f"{pkg}: unknown-control-file [fast-build.sh]\n")
    os.chmod(override_file, 0o644)


def write_md5sums(pkg_root):
    debian_dir = os.path.join(pkg_root, "DEBIAN")
    lines = []
    for dirpath, _, files in os.walk(pkg_root):
        if "DEBIAN" in dirpath.split(os.sep):
            continue
        for f in sorted(files):
            path = os.path.join(dirpath, f)
            rel = os.path.relpath(path, pkg_root)
            with open(path, "rb") as fh:
                digest = hashlib.md5(fh.read()).hexdigest()
            lines.append(f"{digest}  {rel}\n")
    md5sums = os.path.join(debian_dir, "md5sums")
    with open(md5sums, "w") as fh:
        fh.writelines(sorted(lines))
    os.chmod(md5sums, 0o644)


def build_deb(pkg_root, pkg):
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"{pkg}_{VERSION}_all.deb")
    env = dict(os.environ, TMPDIR=OUTDIR)
    subprocess.run(
        ["dpkg-deb", "-b", "-Zgzip", "-z1", pkg_root, out], check=True, env=env
    )
    shutil.rmtree(pkg_root)
    return out


def stage_files(pkg_root, filenames):
    assets_dir = pkg_root + ASSETS_DIR
    os.makedirs(assets_dir, exist_ok=True)
    for name in filenames:
        shutil.copy(os.path.join(REPO, name), os.path.join(assets_dir, name))


def build_chapter_package(chapter, filenames):
    pkg = f"scripturesstudio-assets-{chapter}"
    pkg_root = os.path.join(STAGING, pkg)
    if os.path.exists(pkg_root):
        shutil.rmtree(pkg_root)

    stage_files(pkg_root, filenames)

    kinds = "/".join(sorted(os.path.splitext(f)[1].lstrip(".") for f in filenames))
    description = (
        f"Psalms video assets for psalm {chapter} ({kinds})\n"
        f" Cover image, music track, and/or background video used by\n"
        f" ScripturesStudio to produce psalm {chapter}'s video."
    )
    debian_dir = write_control(pkg_root, pkg, description)
    embed_scripts(debian_dir)
    write_lintian_override(pkg_root, pkg)
    write_md5sums(pkg_root)
    return build_deb(pkg_root, pkg), pkg


def build_common_package(filenames):
    pkg = "scripturesstudio-assets-common"
    pkg_root = os.path.join(STAGING, pkg)
    if os.path.exists(pkg_root):
        shutil.rmtree(pkg_root)

    stage_files(pkg_root, filenames)

    description = (
        "Shared background assets for ScripturesStudio\n"
        " Background fog videos and cover images not tied to a specific\n"
        " psalm chapter."
    )
    debian_dir = write_control(pkg_root, pkg, description)
    embed_scripts(debian_dir)
    write_lintian_override(pkg_root, pkg)
    write_md5sums(pkg_root)
    return build_deb(pkg_root, pkg), pkg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("chapter", nargs="?", help="e.g. 001 -- build only this chapter")
    args = parser.parse_args()

    chapters = discover_chapters()
    if not chapters:
        sys.exit(f"No NNN.jpg/mp3/mp4 files found in {REPO} -- nothing to build.")

    built = []

    if args.chapter:
        if args.chapter not in chapters:
            sys.exit(f"No files found for chapter={args.chapter}")
        out, pkg = build_chapter_package(args.chapter, chapters[args.chapter])
        built.append(pkg)
        print(f"built {out}")
    else:
        common = discover_common_files()
        if common:
            out, pkg = build_common_package(common)
            built.append(pkg)
            print(f"built {out}")
        for chapter in sorted(chapters):
            out, pkg = build_chapter_package(chapter, chapters[chapter])
            built.append(pkg)
            print(f"built {out}")

    print(f"\n{len(built)} packages built")


if __name__ == "__main__":
    main()
