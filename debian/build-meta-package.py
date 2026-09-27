#!/usr/bin/env python3
import hashlib
import os
import shutil
import subprocess

import jinja2

from bootstrap import (
    DEBIAN,
    MAINTAINER,
    OUTDIR,
    STAGING,
    TEMPLATES,
    VERSION,
    discover_chapters,
    discover_common_files,
)

JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES),
    keep_trailing_newline=True,
)


def write_control(pkg_root, pkg, depends, description):
    debian_dir = os.path.join(pkg_root, "DEBIAN")
    os.makedirs(debian_dir, exist_ok=True)
    os.chmod(debian_dir, 0o755)

    depends_list = [f"{d} (= {VERSION})" for d in depends]
    rendered = JINJA_ENV.get_template("control-meta.j2").render(
        pkg=pkg,
        version=VERSION,
        maintainer=MAINTAINER,
        depends=depends_list,
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


def main():
    chapters = discover_chapters()
    if not chapters:
        raise SystemExit("No chapter files found -- nothing to build a meta package from.")

    depends = sorted(f"scripturesstudio-assets-{c}" for c in chapters)
    if discover_common_files():
        depends.insert(0, "scripturesstudio-assets-common")

    pkg = "scripturesstudio-assets"
    pkg_root = os.path.join(STAGING, pkg)
    if os.path.exists(pkg_root):
        shutil.rmtree(pkg_root)
    os.makedirs(pkg_root, exist_ok=True)
    os.chmod(pkg_root, 0o755)

    debian_dir = write_control(
        pkg_root,
        pkg,
        depends,
        "Complete video/audio/image assets for ScripturesStudio\n"
        " Depends on every per-chapter psalm asset package (plus shared\n"
        " backgrounds), pinned to its exact built version.",
    )
    embed_scripts(debian_dir)
    write_md5sums(pkg_root)
    out = build_deb(pkg_root, pkg)
    print(f"built {out}")


if __name__ == "__main__":
    main()
