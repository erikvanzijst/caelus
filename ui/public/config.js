// Runtime-config placeholder.
//
// In the container this file is regenerated from the pod env at startup
// (docker-entrypoint.d/50-runtime-config.sh). In local `vite dev`/`vite build`
// it stays empty, so the app falls back to Vite's build-time import.meta.env
// (.env / .env.local). Having it here keeps the index.html <script src> from
// 404-ing during local development. See src/config.ts.
window.__ENV__ = {};
