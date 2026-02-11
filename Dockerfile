FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git nodejs npm && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies (cached)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p nanobot bridge && touch nanobot/__init__.py && \
    uv pip install --system --no-cache --target /app/site-packages . && \
    rm -rf nanobot bridge

# Build Bridge
COPY bridge/ bridge/
WORKDIR /app/bridge
RUN npm ci && npm run build && \
    rm -rf node_modules src

# Final Stage
FROM python:3.11-slim-bookworm

WORKDIR /app

# Copy installed packages
COPY --from=builder /app/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/bridge/dist /app/bridge/dist
COPY --from=builder /app/bridge/package.json /app/bridge/package.json

# Copy source code
COPY nanobot/ nanobot/
COPY pyproject.toml README.md LICENSE ./
COPY bridge/ bridge/

# Runtime dependencies (Node for bridge)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    # Link nanobot command
    ln -s /usr/local/lib/python3.11/site-packages/bin/nanobot /usr/local/bin/nanobot

# Create config & data directories
RUN mkdir -p /root/.nanobot /root/.nanobot/workspace

# Set Python path
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages
ENV PATH="/usr/local/bin:${PATH}"

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["python3", "-m", "nanobot"]
CMD ["gateway"]
