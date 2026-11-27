FROM python:3.11-slim
LABEL org.opencontainers.image.version="0.1.0" io.trueflag.release-contract="trueflag.release.v1"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CSV_STAGING_ROOT=/app/runtime/csv-staging
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN pip install --no-cache-dir --no-deps . && useradd --create-home --uid 10001 trueflag \
    && mkdir -p /app/runtime/csv-staging && chown 10001:10001 /app/runtime/csv-staging \
    && chmod 700 /app/runtime/csv-staging
USER trueflag
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
