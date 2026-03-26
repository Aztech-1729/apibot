# 🚀 AzTech API Marketplace

<div align="center">

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4.svg)](https://core.telegram.org/bots)
[![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248.svg)](https://www.mongodb.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**A production-ready API monetization platform with Telegram storefront and FastAPI backend**

<p align="center">
  <a href="#key-features">Key Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#installation">Installation</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#api-reference">API Reference</a>
</p>
</div>

---

## 📋 Overview

AzTech API Marketplace is a complete, production-grade solution for monetizing APIs through a Telegram bot interface. The platform enables users to purchase individual API access or subscription plans, with automatic license management, usage tracking, and admin controls.

### Unique Value Proposition
- **Hybrid Model**: Offer both pay-per-day API access AND unlimited subscription plans
- **Instant Delivery**: Automated API key provisioning upon payment confirmation
- **Flexible Pricing**: Configure pricing and limits per API independently
- **Admin Dashboard**: Built-in Telegram admin panel for manual approval and user management
- **Usage Analytics**: Real-time tracking of API calls and user behavior

---

## 🎯 Key Features

### For API Consumers
- ✅ **Free Tier**: Try before you buy with limited daily requests
- ✅ **À La Carte**: Purchase 1, 2, or all 3 APIs independently
- ✅ **Subscriptions**: Weekly/Monthly unlimited access plans
- ✅ **Instant Access**: API keys activated immediately after payment
- ✅ **Self-Service**: Check usage, view docs, and manage subscriptions via bot commands
- ✅ **Secure Payments**: UPI-based payments with screenshot verification

### For Administrators
- ✅ **Manual Approval**: Review payment screenshots before activation
- ✅ **User Management**: Grant/revoke access to specific users
- ✅ **Broadcasting**: Send announcements to all users
- ✅ **Real-time Analytics**: Monitor API usage and revenue
- ✅ **Configurable Pricing**: Adjust prices and limits without code changes

---

## 🏗️ Architecture

```
┌─────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│                 │       │                  │       │                 │
│  Telegram Bot   │──────▶│  FastAPI Server  │──────▶│  External APIs  │
│  (Python)       │       │  (Python)        │       │  - Movie DB     │
│                 │◀──────│                  │◀──────│  - Image Gen    │
│  /start, /buy   │       │  Rate Limiting   │       │  - Phone Lookup │
│  /admin, etc.   │       │  API Keys        │       │                 │
└─────────────────┘       └──────────────────┘       └─────────────────┘
                                  │
                                  │
                                  ▼
                        ┌──────────────────┐
                        │                  │
                        │  MongoDB Atlas   │
                        │  - Users         │
                        │  - API Keys      │
                        │  - Subscriptions │
                        │  - Usage Logs    │
                        │                  │
                        └──────────────────┘
```

### Technology Stack
- **Backend**: FastAPI (ASGI, Pydantic, AsyncIO)
- **Frontend**: Telegram Bot API (python-telegram-bot)
- **Database**: MongoDB Atlas (cloud-hosted NoSQL)
- **Payments**: UPI (Unified Payments Interface - India)
- **Proxy**: Tor (optional, for anonymity)
- **Tunneling**: ngrok/Cloudflare (for webhook exposure)

---

## 📦 Prerequisites

### System Requirements
- Python 3.8 or higher
- pip (Python package manager)
- MongoDB Atlas account (free tier sufficient)
- Telegram Bot Token (from @BotFather)
- UPI ID (for receiving payments)
- Tor Browser (optional, for DDG searches)

### Dependencies
```bash
# Core dependencies (install automatically via requirements.txt)
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-telegram-bot==20.7
pymongo==4.6.0
pydantic==2.5.0
requests==2.31.0
python-dotenv==1.0.0
```

---

## 🚀 Installation

### Step 1: Clone and Setup
```bash
cd /path/to/APIS BOT/
cd aztech-api
```

### Step 2: Configure MongoDB
Update **both** configuration files with your MongoDB credentials:

**File**: `api/config.py` and `bot/config.py`
```python
MONGO_URI = "mongodb+srv://username:password@cluster0.xxx.mongodb.net/"
```

> **Security Tip**: Use environment variables or a `.env` file in production

### Step 3: Install API Server
```bash
cd api
pip install -r requirements.txt
```

### Step 4: Install Telegram Bot
```bash
cd ../bot
pip install -r requirements.txt
```

---

## ⚙️ Configuration

### API Server Configuration (api/config.py)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `MONGO_URI` | string | ✅ | MongoDB connection string |
| `API_BASE_URL` | string | ✅ | Public URL of your API server |
| `TOR_PROXY` | string | ❌ | SOCKS5 proxy for anonymous searches (e.g., "socks5://127.0.0.1:9050") |

### Telegram Bot Configuration (bot/config.py)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `BOT_TOKEN` | string | ✅ | Telegram bot token from @BotFather |
| `ADMIN_ID` | int | ✅ | Telegram user ID of the administrator |
| `UPI_ID` | string | ✅ | UPI ID for receiving payments (format: user@bank) |
| `API_BASE_URL` | string | ✅ | Same as API server URL |
| `MONGO_URI` | string | ✅ | Same MongoDB connection string |

### Pricing Configuration

Edit **both** `config.py` files to modify pricing and limits:

```python
# Individual API Pricing
APIS = {
    "movie_search": {
        "price_per_day": 10,      # Price in INR
        "daily_limit": 200,       # Paid user limit
        "free_limit": 5,          # Free tier limit
        "name": "🎬 Movie Search",
        "description": "Search movies across multiple sources"
    },
    "image_gen": {
        "price_per_day": 15,
        "daily_limit": 100,
        "free_limit": 3,
        "name": "🎨 Image Generation",
        "description": "Generate AI images from text prompts"
    },
    "phone_lookup": {
        "price_per_day": 20,
        "daily_limit": 50,
        "free_limit": 2,
        "name": "📱 Phone Lookup",
        "description": "Get detailed information about phone numbers"
    }
}

# Subscription Plans
PLANS = {
    "weekly": {
        "name": "📅 Weekly Unlimited",
        "price": 99,              # Weekly price
        "duration_days": 7,
        "daily_limit": 999999   # Effectively unlimited
    },
    "monthly": {
        "name": "📆 Monthly Unlimited",
        "price": 299,             # Monthly price
        "duration_days": 30,
        "daily_limit": 999999
    }
}
```

---

## 🖥️ Running the Application

### Development Mode

**Terminal 1: Start API Server**
```bash
cd api
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2: Start Telegram Bot**
```bash
cd bot
python bot.py
```

### Production Mode

**API Server with multiple workers:**
```bash
cd api
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level info
```

**Recommended: Use a process manager**
```bash
# Install pm2 or supervisor
npm install -g pm2

# Start with pm2
pm2 start "uvicorn main:app --host 0.0.0.0 --