FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./

# Пока frontend-команда не добавила Vue-проект, пустой package.json не должен
# блокировать проверку backend Compose-контура. При наличии scripts.build
# выполняется обычная production-сборка Vue/Vite.
RUN if node -e "try { const p=require('./package.json'); process.exit(p.scripts?.build ? 0 : 1) } catch { process.exit(1) }"; then \
        if [ -f package-lock.json ]; then npm ci; else npm install; fi; \
    fi

COPY . .

RUN if node -e "try { const p=require('./package.json'); process.exit(p.scripts?.build ? 0 : 1) } catch { process.exit(1) }"; then \
        npm run build; \
    else \
        mkdir -p dist; \
        printf '%s\n' \
          '<!doctype html><html lang="ru"><meta charset="utf-8">' \
          '<title>Pizza Analysis</title>' \
          '<body><h1>Frontend ещё не добавлен</h1>' \
          '<p>Vue 3 container is ready; add frontend sources and npm build script.</p></body></html>' \
          > dist/index.html; \
    fi

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

