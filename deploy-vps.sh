#!/bin/bash

# Configuration
VPS_HOST="genplus"
REMOTE_DIR="~/nanobot"

echo "🚀 Deploying to $VPS_HOST..."

# 1. Sync Code (exclude git, venv, pycache)
echo "📦 Syncing files..."
rsync -avz --exclude '.git' \
    --exclude '__pycache__' \
    --exclude 'workspace' \
    --exclude 'bridge/node_modules' \
    --exclude 'bridge/dist' \
    . $VPS_HOST:$REMOTE_DIR

# 2. Restart Docker Service
echo "🔄 Restarting bot..."
ssh $VPS_HOST "cd $REMOTE_DIR && docker compose up -d --build"

echo "✅ Done! Bot updated."
