FROM odoo:19

USER root
# Browser tours need a real Chrome that HttpCase can drive, plus
# websocket-client to talk to it. Without EITHER, Odoo silently skips every
# tour and still reports "0 failed" — the browser layer reads as passing
# while never having run. That was true of this image for its whole life.
#
# Ubuntu's `chromium` package is a snap stub that cannot run in a container,
# and Google ships no arm64 Linux build, so Chrome is installed only on
# amd64 (which is what CI runs). On arm64 the tours skip — `make browser`
# says so out loud rather than leaving it to be discovered.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
         apt-get install -y --no-install-recommends wget gnupg ca-certificates \
         && wget -qO- https://dl.google.com/linux/linux_signing_key.pub \
              | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
         && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
http://dl.google.com/linux/chrome/deb/ stable main" \
              > /etc/apt/sources.list.d/google-chrome.list \
         && apt-get update \
         && apt-get install -y --no-install-recommends google-chrome-stable ; \
       fi \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --break-system-packages \
         GitPython==3.1.59 websocket-client==1.8.0 coverage==7.6.10
USER odoo

# every addon folder at the repo root; add a module and this keeps working
COPY dw_git /opt/addons/dw_git
COPY entrypoint.sh /custom-entrypoint.sh
ENTRYPOINT ["/custom-entrypoint.sh"]
CMD ["odoo"]
