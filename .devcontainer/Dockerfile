FROM python:3.11-slim

# Set up work directory
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
curl \
     build-essential \
     libpq-dev \
     postgresql-client \
     && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy only dependency files first for caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies (including the project in editable mode)
RUN uv sync --no-dev

# Copy the rest of the source code
COPY . .

# Expose FastAPI default port
EXPOSE 8000

# Default command to run the application
COPY entrypoint.sh /entrypoint.sh
CMD ["/entrypoint.sh"]
