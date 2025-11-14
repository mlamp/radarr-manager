FROM python:3.12-slim

LABEL maintainer="radarr-manager"
LABEL description="CLI tool for discovering and syncing blockbuster movies with Radarr"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy all files needed for installation
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir -e .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash radarr && \
    chown -R radarr:radarr /app
USER radarr

# Set entrypoint
ENTRYPOINT ["radarr-manager"]

# Default command (can be overridden)
CMD ["--help"]