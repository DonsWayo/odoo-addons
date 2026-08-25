#!/bin/bash
set -e

mkdir -p /mnt/extra-addons

# When ./odoogit is bind-mounted for development, use the live source as-is.
# Otherwise materialise the copy baked into the image.
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
