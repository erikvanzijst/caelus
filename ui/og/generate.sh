#!/usr/bin/env bash
#
# Rasterize the Freepod social preview card (og/og-image.html) to the shipped
# PNG asset (public/og-image.png). Run after editing the HTML template.
#
# Requires a Chrome/Chromium binary. Renders at exactly 1200x630 with a scale
# factor of 1, which is the canonical Open Graph "summary_large_image" size.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="file://${here}/og-image.html"
out="${here}/../public/og-image.png"

# Find a headless browser.
chrome=""
for candidate in google-chrome chromium chromium-browser google-chrome-stable; do
  if command -v "$candidate" >/dev/null 2>&1; then
    chrome="$candidate"
    break
  fi
done
if [[ -z "$chrome" ]]; then
  echo "error: no Chrome/Chromium binary found on PATH" >&2
  exit 1
fi

"$chrome" \
  --headless \
  --no-sandbox \
  --hide-scrollbars \
  --force-device-scale-factor=1 \
  --window-size=1200,630 \
  --default-background-color=00000000 \
  --screenshot="$out" \
  "$src" >/dev/null 2>&1

echo "wrote $out"
