# Dockerfile
FROM python:3.12-slim

# Prevent python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (add others if you need: libpq-dev, gcc, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    default-libmysqlclient-dev \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
  && pip install -r /app/requirements.txt

# Copy the rest of your project
COPY . /app

WORKDIR /app/iqs_site

# Create dirs (optional but helpful)
RUN mkdir -p /app/staticfiles /app/media

# You can expose 8000 for local testing
EXPOSE 8000

# Default command (override in docker-compose if you want)
CMD ["gunicorn", "iqs_site.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
