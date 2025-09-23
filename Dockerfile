# Use a slim Python base for small footprint
FROM python:3.12-slim

WORKDIR /app

# Copy requirements separately to leverage Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app

# Default environment values (can be overridden)
ENV BLUOS_PORT=11000 \
    POLL_INTERVAL=3 \
    LOG_LEVEL=INFO

# Run the service
CMD ["python", "-u", "app/main.py"]
