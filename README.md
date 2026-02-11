<div align="center">
  <img src="nanobot_logo.png" alt="GenBot" width="500">
  <h1>GenBot 🦉: Your Agentic AI Assistant</h1>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker">
  </p>
</div>

🦉 **GenBot** is an advanced, multi-user AI agent based on [nanobot](https://github.com/HKUDS/nanobot). It extends the ultra-lightweight core with powerful enterprise-grade features.

⚡️ **Key Enhancements**:
- **Multi-User System**: Guest/User/Admin permission levels with isolated memory.
- **Specialized Agents**: 
  - `/vision` (Pollinations)
  - `/code` (Qwen)
  - `/search` (Perplexity) 
  - `/image` (Imagen)
- **Interactive UI**: Telegram buttons, inline keyboards, and rich formatting.
- **Agentic Core**: Autonomous tool use, self-correction, and background tasks.

## 📢 News

- **2026-02-11** 👥 **Multi-User System Launched**: GenBot now supports 3-level permissions (Guest, User, Admin) and per-user memory isolation. Admin commands added to Telegram.
- **2026-02-10** 👁️ **Specialized Models**: Added `/vision` for image analysis and `/code` for superior programming capabilities.
- **2026-02-09** 💬 **Expanded Channels**: Direct integration with Telegram, Slack, Email, and QQ.

## ✨ Features

<table align="center">
  <tr align="center">
    <th><p align="center">👥 Multi-User System</p></th>
    <th><p align="center">👁️ Vision & Image</p></th>
    <th><p align="center">🚀 Code Expert</p></th>
    <th><p align="center">🌐 Deep Search</p></th>
  </tr>
  <tr>
    <td align="center">Guest/User/Admin Roles<br>Per-User Memory</td>
    <td align="center">Analyze Images<br>Generate Art</td>
    <td align="center">Write & Debug Code<br>Qwen Integration</td>
    <td align="center">Real-time Web Search<br>Perplexity Powered</td>
  </tr>
</table>

## 👥 Multi-User & Permissions

GenBot supports a secure 3-level permission system:

- **Guest** (Default): 
  - Basic chat only
  - Rate limited (20 msgs/day)
  - **No tool access**
- **User**: 
  - Verified member
  - Higher rate limit (200 msgs/day)
  - Access to safe tools (Search, Image Gen, etc.)
- **Admin**: 
  - Full system access
  - Unlimited usage
  - User management

### User Management Commands (Admin only)
Manage your users directly from Telegram:

- `/grant <chat_id> [user|admin]` — Upgrade a user's permission
- `/revoke <chat_id>` — Downgrade a user to Guest
- `/users` — List all registered users & statistics

### Configuration
To set the initial Owner/Admin:

1. Chat with your bot to auto-create a Guest profile.
2. Edit `~/.nanobot/users/_config.json`:
   ```json
   {
     "owner_chat_ids": ["YOUR_TELEGRAM_CHAT_ID"],
     "default_role": "guest",
     "guest_daily_limit": 20,
     "auto_create_guest": true
   }
   ```
3. Restart the bot.

## 🤖 Specialized Commands

GenBot includes specialized modes for specific tasks:

| Command | Model/Provider | Description |
|---------|----------------|-------------|
| `/vision <image>` | Pollinations | Analyze images and answer questions |
| `/code <prompt>` | Qwen-2.5-Coder | Expert coding assistance |
| `/search <query>` | Perplexity | Deep web search and research |
| `/image <prompt>` | Imagen/SDXL | Generate high-quality images |
| `/model <name>` | Any | Switch the current session's model |

## 📦 Install & Deploy

### Quick Start with Docker (Recommended)

```bash
# 1. Clone
git clone https://github.com/dothesung/nanobot.git
cd genbot

# 2. Build
docker build -t genbot .

# 3. Initialize Config
docker run -v ~/.nanobot:/root/.nanobot --rm genbot onboard

# 4. Edit Config (Add keys)
# Add your Telegram Token and API Keys (OpenRouter, etc.)
nano ~/.nanobot/config.json

# 5. Run Gateway
docker run -d \
  --name genbot \
  --restart always \
  -v ~/.nanobot:/root/.nanobot \
  -p 18790:18790 \
  genbot gateway
```

### Local Installation

```bash
# Install dependencies
pip install -e .

# Initialize
nanobot onboard

# Run
nanobot gateway
```

## ⚙️ Configuration

Config file: `~/.nanobot/config.json`

### Telegram Setup
```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": [] 
    }
  }
}
```
> **Note**: `allowFrom` is optional. If empty, the Multi-User system handles access control (auto-creating Guests).

## 📁 Project Structure

```
nanobot/
├── agent/          # 🧠 Core agent logic & Context Builder
├── users/          # 👥 User Management & Permissions (New!)
├── channels/       # 📱 Telegram, Slack, etc.
├── skills/         # 🎯 Bundled skills
├── tools/          # 🛠️ Built-in tools (Vision, Search...)
├── config/         # ⚙️ Configuration loader
└── cli/            # 🖥️ Command line interface
```

## 🤝 Contribute

GenBot is an open project. Feel free to submit PRs!

## ⭐ Credits
Based on [nanobot](https://github.com/HKUDS/nanobot).
