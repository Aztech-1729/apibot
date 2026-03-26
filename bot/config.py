# bot/config.py — AzTech API Marketplace Bot

# ── Bot ───────────────────────────────────────────────────────────────────────
BOT_TOKEN    = "8300130062:AAH8X-VHdFCAtMV30ypiReXfZKgpRCVZEbs"          # @BotFather
ADMIN_ID     = 6670166083               # Your Telegram user ID

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI    = "mongodb+srv://aztech:ayazahmed1122@cluster0.mhuaw3q.mongodb.net/aztech_api?retryWrites=true&w=majority"

# ── Admin Web Dashboard Credentials ───────────────────────────────────────────
ADMIN_USERNAME = "aztech"
ADMIN_PASSWORD = "1729"

# ── Config Loader Functions (previously in config_loader.py) ──────────────────
def get_config(key=None):
    """Get config from MongoDB. Returns full config dict if key is None."""
    from pymongo import MongoClient
    mongo = MongoClient(MONGO_URI)
    db = mongo["aztech_api"]
    config_col = db["config"]
    
    config = config_col.find_one({"_id": "bot_config"})
    
    if not config:
        # Initialize with defaults if not exists
        default_config = {
            "_id": "bot_config",
            "BOT_TOKEN": BOT_TOKEN,
            "ADMIN_ID": ADMIN_ID,
            "UPI_ID": UPI_ID,
            "QR_IMAGE_URL": QR_IMAGE_URL,
            "CHANNEL_ID": CHANNEL_ID,
            "CHANNEL_LINK": CHANNEL_LINK,
            "APIS": APIS,
            "PLANS": PLANS,
        }
        config_col.insert_one(default_config)
        config = default_config
    
    if key:
        return config.get(key)
    return config

def get_api_url():
    """Get API base URL from MongoDB (fresh fetch every time)"""
    url = get_config("API_BASE_URL")
    return url if url else "http://localhost:8000"

def update_config(key, value):
    """Update config in MongoDB"""
    from pymongo import MongoClient
    mongo = MongoClient(MONGO_URI)
    db = mongo["aztech_api"]
    config_col = db["config"]
    
    config_col.update_one(
        {"_id": "bot_config"},
        {"$set": {key: value}},
        upsert=True
    )
    return True

# ── Payment ───────────────────────────────────────────────────────────────────
UPI_ID       = "aztech7@axl"
QR_IMAGE_URL = "https://i.ibb.co/VWWVVfrD/qr.jpg"

# ── Bot Header Image ──────────────────────────────────────────────────────────
BOT_IMAGE_URL = "https://i.ibb.co/40V7Nsm/fb78eb26-49e7-4ce4-9593-2fbf632fa023.png"

# ── Channel (force join) ──────────────────────────────────────────────────────
CHANNEL_ID   = -1002901487490
CHANNEL_LINK = "https://t.me/aztechshub"

# ── API Server base URL ───────────────────────────────────────────────────────
# NOTE: API_BASE_URL is now loaded dynamically from MongoDB via get_api_url()
# Run "python update_url.py" to update the tunnel URL in MongoDB

# ── APIs for sale ─────────────────────────────────────────────────────────────
# Users can buy any 1, 2, or all 3 independently per day
APIS = {
    "movie_search": {
        "name":          "🎬 Movie Search",
        "description":   "Search TeraBox & Google Drive for movies/web series",
        "price_per_day": 10,
        "daily_limit":   200,
        "free_limit":    5,
    },
    "image_gen": {
        "name":          "🎨 Image Generation",
        "description":   "Generate AI images via Stable Diffusion XL",
        "price_per_day": 15,
        "daily_limit":   100,
        "free_limit":    3,
    },
    "phone_lookup": {
        "name":          "📱 Phone Lookup",
        "description":   "Indian mobile number intelligence & carrier info",
        "price_per_day": 20,
        "daily_limit":   50,
        "free_limit":    2,
    },
}

# ── Subscription Plans ─────────────────────────────────────────────────────────
# Weekly and Monthly unlimited plans for all APIs
PLANS = {
    "weekly": {
        "name": "📅 Weekly Unlimited",
        "price": 99,
        "duration_days": 7,
        "description": "Unlimited access to all 3 APIs for 7 days",
        "daily_limit": 999999,  # Effectively unlimited
    },
    "monthly": {
        "name": "📆 Monthly Unlimited",
        "price": 299,
        "duration_days": 30,
        "description": "Unlimited access to all 3 APIs for 30 days",
        "daily_limit": 999999,  # Effectively unlimited
    },
}