FROM node:22-alpine AS frontend-assets

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY app ./app
RUN npm run copy-icons

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY --from=frontend-assets /build/app/static/vendor ./app/static/vendor
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "-m", "app", "serve", "--host", "0.0.0.0", "--port", "8000"]
