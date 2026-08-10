# ⚠ SECURITY — read before building (purocoach-incident-2026-08-06.md):
# do NOT build this image on the compromised host until it is rebuilt; a build
# runs npm install. The .npmrc mitigations still apply inside the container:
# lifecycle scripts are disabled and every package resolves to pre-incident
# versions (before=2026-08-01). After the first clean build, generate
# package-lock.json and switch the install line to: npm ci --ignore-scripts
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json .npmrc ./
RUN npm install --ignore-scripts
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
# Direct binary invocation: `npm run` is disabled by ignore-scripts (on purpose).
RUN node_modules/.bin/tsc --noEmit && node_modules/.bin/vite build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
