#!/bin/bash
set -e

mkdir -p /mnt/extra-addons

# Always sync module from image (idempotent)
rm -rf /mnt/extra-addons/odoogit
cp -r /opt/odoogit /mnt/extra-addons/
chown -R odoo:odoo /mnt/extra-addons

exec /entrypoint.sh "$@"
