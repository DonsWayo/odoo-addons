#!/bin/bash
set -e

mkdir -p /mnt/extra-addons

# Always sync module from image (idempotent)
rm -rf /mnt/extra-addons/git_hosting
cp -r /opt/git_hosting /mnt/extra-addons/
chown -R odoo:odoo /mnt/extra-addons

exec /entrypoint.sh "$@"
