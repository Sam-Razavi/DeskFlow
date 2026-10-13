FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npx ng build --configuration production \
    # The CSP allows the build's one inline script by hash, which has to be computed from the output.
    && node scripts/csp-hash.mjs dist/frontend/browser/index.html > /app/csp.envsh

FROM nginx:1.29-alpine
# The official image renders /etc/nginx/templates/*.template with envsubst at startup.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=755 docker/ipv6.envsh /docker-entrypoint.d/16-ipv6.envsh
COPY --from=build --chmod=755 /app/csp.envsh /docker-entrypoint.d/17-csp.envsh
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
ENV PORT=80 API_UPSTREAM=http://api:8000 NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
EXPOSE 80
