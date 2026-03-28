FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Install dependencies first (better layer caching)
COPY pyproject.toml .
RUN uv pip install --system -e . --no-cache

# Copy source
COPY . .

# Web dashboard port
EXPOSE 8080

CMD ["python3.11", "scripts/run_agent.py"]
