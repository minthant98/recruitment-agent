FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create necessary directories
RUN mkdir -p attachments outputs credentials

# Expose port
EXPOSE 8000

# Start command — web UI only, no Gmail polling
CMD ["uvicorn", "ui.app:app", "--host", "0.0.0.0", "--port", "8000"]