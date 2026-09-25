#!/bin/sh
# Build scripturesstudio-assets_<version>_all.deb
# Usage: packaging/deb/build.sh
set -eu

cd "$(dirname "$0")/../.."
REPO_ROOT="$(pwd)"
VERSION="0.$(git rev-list --count HEAD)"
sed -i "s/^Version: .*/Version: $VERSION/" packaging/deb/control

PKG_DIR="$REPO_ROOT/debian-pkg"
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN" "$PKG_DIR/var/lib/scripturesstudio/assets"
cp packaging/deb/control "$PKG_DIR/DEBIAN/control"
cp *.jpg *.mp3 *.mp4 "$PKG_DIR/var/lib/scripturesstudio/assets/"
dpkg-deb --build --root-owner-group "$PKG_DIR" "scripturesstudio-assets_${VERSION}_all.deb"
rm -rf "$PKG_DIR"
echo "Built scripturesstudio-assets_${VERSION}_all.deb"
