# Dockerfile

# Use the official Python image from Docker Hub
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
# Add this environment variable to disable Chrome sandbox (needed in Docker)
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Set build-time variables
ARG ENVIRONMENT=production
ENV ENVIRONMENT=${ENVIRONMENT}

# Set the working directory in the container
WORKDIR /app

# Install system dependencies - add all necessary Playwright dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    build-essential \
    netcat-openbsd \
    curl \
    # Playwright required dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libxcursor1 \
    libxi6 \
    libxtst6 \
    fonts-liberation \
    xvfb \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright and browsers with proper permissions
RUN mkdir -p /ms-playwright && \
    pip install playwright && \
    playwright install chromium && \
    chmod -R 777 /ms-playwright

# Verify Installation
RUN python3.10 -m pip list > /app/pip_list.txt

# Copy the application code
COPY . /app/

# Create a non-root user (optional but recommended)
RUN adduser --disabled-password --gecos '' appuser

RUN mkdir -p /app/media/rag_documents
RUN chown -R appuser:appuser /app/media
RUN chown -R appuser:appuser /ms-playwright

USER appuser

# Expose port 8080
EXPOSE 8080
ENV PORT 8080

# Copy the entrypoint script
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
