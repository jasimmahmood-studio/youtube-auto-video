FROM python:3.11-slim

# Install FFmpeg with libass (subtitle support)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libass-dev fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Set up Montserrat font
RUN python scripts/setup_fonts.py || true

# Default: run the daily pipeline
CMD ["python", "scripts/run_daily.py"]
