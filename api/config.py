# aztech-api/api/config.py — AzTech API Server Configuration

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI = "mongodb+srv://aztech:ayazahmed1122@cluster0.mhuaw3q.mongodb.net/aztech_api?retryWrites=true&w=majority"

# ── Admin Web Dashboard Credentials ───────────────────────────────────────────
ADMIN_USERNAME = "aztech"
ADMIN_PASSWORD = "1729"
ADMIN_PANEL_SECRET = "aztech_admin_secret_2024"

# ── Config Loader Functions (previously in config_loader.py) ──────────────────
def get_config(key=None):
    """Get config from MongoDB. Returns full config dict if key is None."""
    from pymongo import MongoClient
    mongo = MongoClient(MONGO_URI)
    db = mongo["aztech_api"]
    config_col = db["config"]
    
    # Default config if MongoDB is empty
    DEFAULT_CONFIG = {
        "BOT_TOKEN": BOT_TOKEN if 'BOT_TOKEN' in dir() else "8300130062:AAH8X-VHdFCAtMV30ypiReXfZKgpRCVZEbs",
        "ADMIN_ID": ADMIN_ID,
        "UPI_ID": UPI_ID if 'UPI_ID' in dir() else "aztech7@axl",
        "APIS": APIS,
        "PLANS": PLANS,
    }
    
    config = config_col.find_one({"_id": "bot_config"})
    
    if not config:
        # Initialize with defaults if not exists
        config_col.insert_one({**DEFAULT_CONFIG, "_id": "bot_config"})
        config = DEFAULT_CONFIG
    
    if key:
        return config.get(key)
    return config

def get_api_url():
    """Get API base URL from MongoDB (fresh fetch every time)"""
    url = get_config("API_BASE_URL")
    return url if url else "http://localhost:8000"

def update_config(key, value):
    """Update config in MongoDB (previously in update_config.py)"""
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

# ── Admin Config ─────────────────────────────────────────────────────────────
ADMIN_ID = 6670166083  # Admin Telegram ID - unlimited access

# ── Bot Config (for MongoDB loader defaults) ──────────────────────────────────
BOT_TOKEN = "8300130062:AAH8X-VHdFCAtMV30ypiReXfZKgpRCVZEbs"
UPI_ID = "aztech7@axl"
QR_IMAGE_URL = "https://i.ibb.co/VWWVVfrD/qr.jpg"
BOT_IMAGE_URL = "https://i.ibb.co/40V7Nsm/fb78eb26-49e7-4ce4-9593-2fbf632fa023.png"
CHANNEL_ID = -1002901487490
CHANNEL_LINK = "https://t.me/aztechshub"
# NOTE: API_BASE_URL is loaded dynamically from MongoDB via get_api_url()

# ── Upstream APIs ─────────────────────────────────────────────────────────────
PHONE_API_ENDPOINT = "https://yttttttt.anshapi.workers.dev/"
PHONE_API_KEY      = "DARKOSINT"
IMAGE_API_URL      = "https://aztech-image-api.mdayaz1729.workers.dev"

# ── Tor proxy for DDG searches ────────────────────────────────────────────────
TOR_PROXY = "socks5://127.0.0.1:9050"   # set to None to disable

# ── Available APIs ────────────────────────────────────────────────────────────
# Users can purchase any 1, 2 or all 3 APIs independently.
# Each API has its own daily limit and price.
APIS = {
    "movie_search": {
        "name":          "🎬 Movie Search",
        "description":   "Search TeraBox & Google Drive for movies/web series",
        "price_per_day": 10,       # ₹ per day
        "daily_limit":   200,      # requests/day (paid)
        "free_limit":    5,        # requests/day (free trial)
        "endpoint":      "GET /search?q=<movie>&source=terabox|gdrive|both",
    },
    "image_gen": {
        "name":          "🎨 Image Generation",
        "description":   "Generate images via Stable Diffusion XL Lightning",
        "price_per_day": 15,
        "daily_limit":   100,
        "free_limit":    3,
        "endpoint":      "POST /generate  body: {prompt, width, height, steps}",
    },
    "phone_lookup": {
        "name":          "📱 Phone Lookup",
        "description":   "Indian mobile number intelligence & carrier info",
        "price_per_day": 20,
        "daily_limit":   50,
        "free_limit":    2,
        "endpoint":      "GET /lookup?number=<10digit>",
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
