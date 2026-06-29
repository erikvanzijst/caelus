# Keycloak with the Freepod theme baked in.
#
# The custom login/account/email theme (theme/freepod/) is ~22 files / ~400KB
# of CSS, fonts, logo and FreeMarker templates — too much to ride along in a
# ConfigMap mount, so we bake it into the image instead. Themes are read from
# /opt/keycloak/themes at runtime, so a plain COPY is all that's needed (no
# `kc.sh build` required, and build-time DB/feature options stay untouched).
#
# Build + push with: ./scripts/build-images.sh --keycloak
FROM quay.io/keycloak/keycloak:24.0

COPY theme/freepod /opt/keycloak/themes/freepod
