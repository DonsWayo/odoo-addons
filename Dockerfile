FROM odoo:19

USER root
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --break-system-packages GitPython==3.1.59
USER odoo

# every addon folder at the repo root; add a module and this keeps working
COPY dw_git /opt/addons/dw_git
COPY entrypoint.sh /custom-entrypoint.sh
ENTRYPOINT ["/custom-entrypoint.sh"]
CMD ["odoo"]
