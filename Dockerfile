# Multi-stage-ish simple Dockerfile for Render deployment
# - Uses slim Python image
# - Installs system deps required for psycopg / building wheels
# - Installs Python deps from requirements.txt
# - Copies the app and runs uvicorn on the port Render provides via $PORT

FROM python:3.12-slim

# Prevents Python from writing pyc files and enables unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for building some packages (psycopg)
# Keep image small by cleaning apt lists
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install before copying the full source to leverage Docker cache
COPY requirements.txt ./

# Upgrade pip and install Python dependencies
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . /app

# Create a non-root user for better security and set ownership
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

# Expose default port; Render will provide PORT env var at runtime
EXPOSE 8000

# Use the PORT env var if provided by the hosting platform (Render sets PORT); fallback to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]

