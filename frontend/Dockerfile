FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npx ng build --configuration production

FROM nginx:1.29-alpine
# The official image renders /etc/nginx/templates/*.template with envsubst at startup.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
ENV PORT=80 API_UPSTREAM=http://api:8000 NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
EXPOSE 80
