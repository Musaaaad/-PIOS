FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts
COPY seeds ./seeds
# Verified schema/seed SQL, required by scripts/bootstrap_db.py for first-boot
# database provisioning on managed platforms.
COPY sql ./sql
RUN pip install --no-cache-dir . \
    && chmod +x ./scripts/render_entrypoint.sh
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
