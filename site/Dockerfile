# Production image for efc-site (Cloud Run, efc-prod).
#
# `gcloud run deploy --source site` builds this file when it exists, so the
# deploy workflow needs no change. The image adds the Antigravity CLI, which
# runs the embedded agent on Gemini 3.8 Flash (see agent/README.md).

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    AGY_CLI_DISABLE_AUTO_UPDATE=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Antigravity CLI 1.4.6 for Linux x64, pinned by URL and sha256. The sha512 of
# this tarball matches the official release manifest
# (antigravity.google/cli/install.sh -> manifests/linux_amd64.json). The install
# is root-owned and read-only, so the CLI can never update itself.
# Downloaded and checked with Python rather than `ADD --checksum`, which needs
# BuildKit; Cloud Build's default Docker builder may not have it.
ARG AGY_URL=https://storage.googleapis.com/antigravity-public/antigravity-cli/1.4.6-4884751325200384/linux-x64/cli_linux_x64.tar.gz
ARG AGY_SHA256=513c74ad3e70323839a65d8dccc6f9977b0903e5facd914cbb06be283c2bb640
RUN python -c "import hashlib, sys, urllib.request; data = urllib.request.urlopen(sys.argv[1], timeout=300).read(); digest = hashlib.sha256(data).hexdigest(); sys.exit('agy checksum mismatch: ' + digest) if digest != sys.argv[2] else open('/tmp/agy.tgz', 'wb').write(data)" "$AGY_URL" "$AGY_SHA256" \
    && mkdir -p /opt/agy && tar -xzf /tmp/agy.tgz -C /opt/agy && rm /tmp/agy.tgz \
    && chown -R root:root /opt/agy && chmod -R a-w /opt/agy \
    && ln -s /opt/agy/antigravity /usr/local/bin/agy \
    && HOME=/tmp/agy-version agy --version && rm -rf /tmp/agy-version

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . ./

# The web process runs unprivileged; the agent's HOME and scratch space live
# under /tmp, which Cloud Run backs with memory.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin efc
USER efc

EXPOSE 8080
CMD exec gunicorn -b :$PORT -w 1 --threads 16 --timeout 180 app:app
