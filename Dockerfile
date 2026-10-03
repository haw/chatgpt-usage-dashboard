FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY config ./config
RUN pip install --no-cache-dir .

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /app/data \
    && chown -R app:app /app

USER app

EXPOSE 8000
CMD ["python", "-m", "app", "serve", "--host", "0.0.0.0", "--port", "8000"]
