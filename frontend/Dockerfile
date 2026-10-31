# 1. Build Angular (configuration production : API sur la même origine)
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# --ignore-scripts : aucun script postinstall de dépendance exécuté (le build n'en a pas besoin)
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY angular.json tsconfig.json tsconfig.app.json ./
COPY src ./src
RUN npm run build -- --configuration production

# 2. Service statique + relais /api vers le conteneur de l'API
#    Variante officielle sans privilèges de nginx : utilisateur nginx (uid 101), port 8080
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
USER nginx
EXPOSE 8080
