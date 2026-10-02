FROM node:20-alpine AS build

LABEL maintainer="Alejandria" \
      description="Alejandria Frontend - Tu biblioteca digital"

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies (ci uses lock file for faster, deterministic installs)
RUN npm ci && npm cache clean --force

# Copy source code
COPY . .

# Build app
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
# NB: 127.0.0.1 (no localhost) — BusyBox wget resuelve localhost→::1 y nginx
# solo escucha IPv4 → el check fallaba siempre.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
