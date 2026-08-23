FROM odoo:19

USER root
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --break-system-packages GitPython==3.1.44 websocket-client
USER odoo

COPY odoogit /opt/odoogit
COPY entrypoint.sh /custom-entrypoint.sh
ENTRYPOINT ["/custom-entrypoint.sh"]
CMD ["odoo"]
