FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

# Install build dependencies & Node.js 20
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
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
RUN npm install && npm run build && \
    rm -rf node_modules src

# Final Stage
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install Runtime dependencies & Node.js 20
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    nodejs \
    gh \
    libgtk-3-0 libasound2 libdbus-glib-1-2 libx11-xcb1 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages
COPY --from=builder /app/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/bridge/dist /app/bridge/dist
COPY --from=builder /app/bridge/package.json /app/bridge/package.json

# Copy source code
COPY nanobot/ nanobot/
COPY pyproject.toml README.md LICENSE ./
COPY bridge/ bridge/

# Link nanobot command
RUN ln -s /usr/local/lib/python3.11/site-packages/bin/nanobot /usr/local/bin/nanobot

# Create config & data directories
RUN mkdir -p /root/.nanobot /root/.nanobot/workspace

# Set Python path
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages
ENV PATH="/usr/local/bin:${PATH}"

# Install Camoufox browser (must be after packages are copied)
RUN python3 -m camoufox fetch


# Gateway default port
EXPOSE 18790

ENTRYPOINT ["python3", "-m", "nanobot"]
CMD ["gateway"]
