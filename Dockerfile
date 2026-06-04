FROM python:3.11-slim

# Avoid writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements_api.txt /app/
RUN pip install --no-cache-dir -r requirements_api.txt

# Create a non-root user and change ownership
RUN useradd -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Copy source code
COPY --chown=appuser:appuser . /app/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
