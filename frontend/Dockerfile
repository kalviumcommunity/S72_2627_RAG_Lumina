# Build stage
FROM node:22-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml* frontend/package-lock.json* ./

RUN if [ -f pnpm-lock.yaml ]; then corepack enable && pnpm install --frozen-lockfile; \
    else npm ci; fi

COPY frontend/ ./

RUN npm run build

# Serve stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

RUN cat <<'EOF' > /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Interactive API documentation (linked from the account menu).
    location /docs {
        proxy_pass http://api:8000/docs;
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://api:8000/api/;
        # Answers stream as server-sent events: pass them through as they arrive.
        proxy_buffering off;
        proxy_read_timeout 120s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
