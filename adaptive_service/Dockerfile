FROM ghcr.io/astral-sh/uv:0.9.30-python3.11-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY adaptive_service/requirements.txt /app/requirements.txt
RUN uv pip install --system -r /app/requirements.txt
COPY adaptive_service /app

EXPOSE 8010
CMD ["python", "-m", "uvicorn", "edubrain_adaptive.api:app", "--host", "0.0.0.0", "--port", "8010"]

