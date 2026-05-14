FROM python:3.12-slim-bookworm

RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Install build deps and clean apt cache (api-pgd pattern)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps in a separate layer for caching
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY . .

RUN chmod +x /app/scripts/entrypoint.sh \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["/app/scripts/entrypoint.sh"]
