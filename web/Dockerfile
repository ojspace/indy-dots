FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# Vite inlines env vars at build time. VITE_GATEWAY_URL defaults to ""
# (same-origin: the app falls back to fetch("/api/...")).
ARG VITE_GATEWAY_URL=""
ENV VITE_GATEWAY_URL=$VITE_GATEWAY_URL
# NOTE: VITE_AUTH_TOKEN is intentionally NOT baked in — the dashboard
# prompts for the token at runtime (stored in localStorage only).
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx alpine runs master as root (needed to bind + write /var/cache/nginx)
# but workers drop to the unprivileged 'nginx' user — keep it that way.
EXPOSE 3000

HEALTHCHECK --interval=20s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:3000/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
