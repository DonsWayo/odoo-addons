#!/bin/bash
set -e

mkdir -p /mnt/extra-addons

# When ./odoogit is bind-mounted for development, use the live source as-is.
# Otherwise materialise the copy baked into the image.
if grep -q " /mnt/extra-addons/odoogit " /proc/mounts 2>/dev/null; then
    echo "entrypoint: odoogit is bind-mounted — using live source"
else
    rm -rf /mnt/extra-addons/odoogit
    cp -r /opt/odoogit /mnt/extra-addons/
    chown -R odoo:odoo /mnt/extra-addons
fi

exec /entrypoint.sh "$@"
