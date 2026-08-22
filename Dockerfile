FROM odoo:19

# Copy the git_hosting module to a temporary location
COPY git_hosting /opt/git_hosting

# Copy custom entrypoint
COPY entrypoint.sh /custom-entrypoint.sh

# Use custom entrypoint
ENTRYPOINT ["/custom-entrypoint.sh"]
CMD ["odoo", "--dev=all", "--log-level=info"]
