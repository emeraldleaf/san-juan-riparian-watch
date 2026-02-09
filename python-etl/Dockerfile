FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: one-shot full run (backwards compatible)
# Override with ETL_MODE=scheduled for long-lived service
CMD ["python", "entrypoint.py"]
