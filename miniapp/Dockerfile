# Mini App Dockerfile (build → nginx serve)
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps
COPY package.json pnpm-lock.yaml* ./
RUN npm install -g pnpm && pnpm install --frozen-lockfile || pnpm install

# Build
COPY . .
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm build

# --- Serve stage ---
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
