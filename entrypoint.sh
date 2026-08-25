#!/bin/bash
set -e

mkdir -p /mnt/extra-addons

# When ./dw_git is bind-mounted for development, use the live source as-is.
# Otherwise materialise the copy baked into the image.
# Drop addons that no longer ship in the image and are not bind-mounted.
# Without this a renamed or removed module lingers in the volume and Odoo
# keeps seeing a phantom addon.
for stale in /mnt/extra-addons/*; do
    [ -d "$stale" ] || continue
    name=$(basename "$stale")
    if [ ! -d "/opt/addons/$name" ] && ! grep -q " /mnt/extra-addons/$name " /proc/mounts 2>/dev/null; then
        echo "entrypoint: pruning stale addon $name"
        rm -rf "$stale"
    fi
done

for src in /opt/addons/*; do
    name=$(basename "$src")
    if grep -q " /mnt/extra-addons/$name " /proc/mounts 2>/dev/null; then
        echo "entrypoint: $name is bind-mounted - using live source"
    else
        rm -rf "/mnt/extra-addons/$name"
        cp -r "$src" /mnt/extra-addons/
        chown -R odoo:odoo "/mnt/extra-addons/$name"
    fi
done

exec /entrypoint.sh "$@"
