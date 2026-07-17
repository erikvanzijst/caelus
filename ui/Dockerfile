FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Runtime config (window.__ENV__) is not baked here: Terraform renders config.js
# into the caelus-ui-config ConfigMap and mounts it at
# /usr/share/nginx/html/config.js. The image stays env-agnostic. See
# tf/app/caelus/{configmap,deployment-ui}.tf and ui/public/config.js (dev stub).

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
