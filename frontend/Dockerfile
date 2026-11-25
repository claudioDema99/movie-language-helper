# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
RUN npm run build

FROM caddy:2-alpine AS runtime
COPY --from=build /build/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/docker-entrypoint.sh /usr/local/bin/movie-helper-entrypoint
RUN chmod 0555 /usr/local/bin/movie-helper-entrypoint
EXPOSE 80 443
ENTRYPOINT ["movie-helper-entrypoint"]
