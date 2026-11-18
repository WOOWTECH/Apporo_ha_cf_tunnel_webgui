# ── Stage 1: Build the Web GUI frontend (arch-independent static files) ──
# BUILDPLATFORM keeps this stage native when cross-building for aarch64.
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend-build

WORKDIR /build
# Strict, lockfile-pinned, no lifecycle scripts — a desynced lockfile must
# fail the build loudly rather than fall back to unpinned resolution.
COPY webgui/frontend/package.json webgui/frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY webgui/frontend/ ./
RUN npm run build

# ── Stage 2: Add-on runtime ──────────────────────────────────────────────
FROM ghcr.io/hassio-addons/base:21.0.1

# Set S6 verbosity level
ENV S6_VERBOSITY="1"

# Setup base
ARG BUILD_ARCH="amd64"

# renovate: datasource=repology depName=yq packageName=alpine_3_24/yq-go versioning=loose
ARG YQ_VERSION="4.53.3-r2"
# renovate: datasource=github-releases depName=cloudflared packageName=cloudflare/cloudflared versioning=loose
ARG CLOUDFLARED_VERSION="2026.7.3"

# Copy root filesystem
COPY rootfs /

# Run the script that installs cloudflared
RUN ["/build.sh"]

# Install the Web GUI backend and its Python runtime
COPY webgui/backend /opt/webgui/backend
COPY --from=frontend-build /build/dist /opt/webgui/static
RUN ["/build-webgui.sh"]

CMD ["/run.sh"]

# Build arguments. home-assistant/builder passes only BUILD_ARCH, BUILD_FROM
# and BUILD_VERSION (and sets the io.hass.* labels from config.yaml itself),
# so name, description and repository default to this add-on's own values.
ARG BUILD_DATE
ARG BUILD_DESCRIPTION="Connect an Apporo Security Access (Cloudflare Tunnel) to Home Assistant without opening ports, with a Web GUI"
ARG BUILD_NAME="Apporo CF Tunnel Web"
ARG BUILD_REF
ARG BUILD_REPOSITORY="WOOWTECH/Apporo_ha_cf_tunnel_webgui"
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    maintainer="Apporo <info@apporo.ai>" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Apporo" \
    org.opencontainers.image.authors="Apporo <info@apporo.ai>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"
