# api/main.py — AzTech FastAPI Server with Admin Dashboard

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles  
from fastapi.middleware.wsgi import WSGIMiddleware
from pymongo import MongoClient
from ddgs import DDGS
from flask import Flask, render_template, request as flask_request, redirect as flask_redirect

import os
import re
import httpx
import secrets
import hashlib
from datetime import datetime, timezone, timedelta

from config import (
    MONGO_URI, TOR_PROXY, PHONE_API_ENDPOINT, PHONE_API_KEY, IMAGE_API_URL,
    APIS, PLANS, ADMIN_ID, get_api_url, get_config, update_config,
    ADMIN_USERNAME, ADMIN_PASSWORD
)

API_BASE_URL = get_api_url()

# MongoDB
mongo = MongoClient(MONGO_URI)
db = mongo["aztech_api"]
users = db["users"]
usage = db["usage"]
orders = db["orders"]
config_col = db["config"]

# Get the correct template folder path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_ROOT = os.environ.get("WEB_ROOT", os.path.dirname(BASE_DIR))
WEB_DIR = os.path.join(WEB_ROOT, 'web')
TEMPLATE_DIR = os.path.join(WEB_DIR, 'templates')

# ── Flask Admin Dashboard ─────────────────────────────────────────────────────
admin_app = Flask(__name__, template_folder=TEMPLATE_DIR)
admin_app.jinja_env.globals.update(min=min)

def percentage_filter(numerator, denominator):
    """Calculate percentage with division by zero protection"""
    if denominator == 0:
        return 0
    return round((numerator / denominator) * 100)

admin_app.jinja_env.filters['percentage'] = percentage_filter

def generate_token(username, password):
    """Generate a simple auth token"""
    data = f"{username}:{password}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]

ADMIN_TOKEN = generate_token(ADMIN_USERNAME, ADMIN_PASSWORD)

# ── Admin Routes ─────────────────────────────────────────────────────────────

def require_admin(f):
    """Decorator to require admin auth via token"""
    def decorator(*args, **kwargs):
        token = flask_request.args.get('token') or flask_request.form.get('token')
        if token != ADMIN_TOKEN:
            return render_template('login.html', error="Invalid token")
        return f(*args, **kwargs)
    decorator.__name__ = f.__name__
    return decorator

@admin_app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if flask_request.method == 'POST':
        username = flask_request.form.get('username')
        password = flask_request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            token = generate_token(username, password)
            return flask_redirect(f'/admin/dashboard?token={token}')
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

def get_token():
    return flask_request.args.get('token') or flask_request.form.get('token')

def check_admin():
    token = get_token()
    return token == ADMIN_TOKEN

@admin_app.route('/')
def admin_root():
    if not check_admin():
        return flask_redirect('/admin/login')
    return flask_redirect('/admin/dashboard')

@admin_app.route('/dashboard')
@require_admin
def admin_dashboard():
    total_users = users.count_documents({})
    paid_users = users.count_documents({"plan": {"$in": ["paid", "weekly", "monthly"]}})
    free_users = users.count_documents({"plan": "free"})
    pending_orders = orders.count_documents({"status": "pending"})
    
    t = datetime.now(timezone.utc).date().isoformat()
    today_usage = list(usage.find({"date": t}))
    
    usage_stats = {}
    config = get_config()
    for api_id, meta in config.get("APIS", {}).items():
        total = sum(doc.get(api_id, 0) for doc in today_usage)
        usage_stats[api_id] = {"name": meta.get("name", api_id), "total": total, "limit": meta.get("daily_limit", 0)}
    
    recent_users = list(users.find().sort("joined", -1).limit(10))
    recent_orders = list(orders.find().sort("created_at", -1).limit(5))
    
    token = get_token()
    return render_template('dashboard.html', 
                         total_users=total_users, paid_users=paid_users, free_users=free_users,
                         pending_orders=pending_orders, usage_stats=usage_stats,
                         recent_users=recent_users, recent_orders=recent_orders, token=token)

@admin_app.route('/users')
@require_admin
def admin_users():
    all_users = list(users.find().sort("joined", -1))
    token = get_token()
    return render_template('users.html', users=all_users, token=token)

@admin_app.route('/user/<user_id>')
@require_admin
def admin_user_detail(user_id):
    from bson import ObjectId
    user = users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return render_template('login.html', error="User not found")
    usage_history = list(usage.find({"api_key": user.get("api_key")}).sort("date", -1).limit(30))
    token = get_token()
    return render_template('user_detail.html', user=user, usage_history=usage_history, token=token)

@admin_app.route('/user/create', methods=['POST'])
@require_admin
def admin_create_user():
    name = flask_request.form.get('name')
    telegram_id = flask_request.form.get('telegram_id')
    plan = flask_request.form.get('plan')
    apis = flask_request.form.getlist('apis')
    
    api_key = "aztech_" + secrets.token_hex(16)
    
    user_data = {
        "telegram_id": int(telegram_id),
        "name": name,
        "api_key": api_key,
        "plan": plan,
        "apis": apis,
        "active": True,
        "joined": datetime.now(timezone.utc),
    }
    
    if plan in ["weekly", "monthly"]:
        config = get_config()
        duration = config.get("PLANS", {}).get(plan, {}).get("duration_days", 7)
        user_data["expires_at"] = datetime.now(timezone.utc) + timedelta(days=duration)
    elif plan == "paid":
        user_data["expires_at"] = datetime.now(timezone.utc) + timedelta(hours=24)
    
    users.insert_one(user_data)
    token = get_token()
    return flask_redirect(f'/admin/users?token={token}')

@admin_app.route('/user/<user_id>/edit', methods=['POST'])
@require_admin
def admin_edit_user(user_id):
    from bson import ObjectId
    plan = flask_request.form.get('plan')
    apis = flask_request.form.getlist('apis')
    active = flask_request.form.get('active') == 'on'
    
    update_data = {"plan": plan, "apis": apis, "active": active}
    
    if plan in ["weekly", "monthly"]:
        config = get_config()
        duration = config.get("PLANS", {}).get(plan, {}).get("duration_days", 7)
        update_data["expires_at"] = datetime.now(timezone.utc) + timedelta(days=duration)
    elif plan == "paid":
        update_data["expires_at"] = datetime.now(timezone.utc) + timedelta(hours=24)
    elif plan == "free":
        update_data["expires_at"] = None
        update_data["apis"] = []
    
    users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    token = get_token()
    return flask_redirect(f'/admin/user/{user_id}?token={token}')

@admin_app.route('/user/<user_id>/delete')
@require_admin
def admin_delete_user(user_id):
    from bson import ObjectId
    users.delete_one({"_id": ObjectId(user_id)})
    token = get_token()
    return flask_redirect(f'/admin/users?token={token}')

@admin_app.route('/user/<user_id>/reset-key')
@require_admin
def admin_reset_key(user_id):
    from bson import ObjectId
    new_key = "aztech_" + secrets.token_hex(16)
    users.update_one({"_id": ObjectId(user_id)}, {"$set": {"api_key": new_key}})
    token = get_token()
    return flask_redirect(f'/admin/user/{user_id}?token={token}')

@admin_app.route('/user/<user_id>/toggle')
@require_admin
def admin_toggle_user(user_id):
    from bson import ObjectId
    user = users.find_one({"_id": ObjectId(user_id)})
    if user:
        new_status = not user.get("active", True)
        users.update_one({"_id": ObjectId(user_id)}, {"$set": {"active": new_status}})
    token = get_token()
    return flask_redirect(f'/admin/user/{user_id}?token={token}')

@admin_app.route('/apikeys')
@require_admin
def admin_apikeys():
    all_users = list(users.find({"api_key": {"$exists": True}}).sort("joined", -1))
    token = get_token()
    return render_template('apikeys.html', users=all_users, token=token)

@admin_app.route('/apikey/<api_key>/toggle')
@require_admin
def admin_toggle_key(api_key):
    user = users.find_one({"api_key": api_key})
    if user:
        new_status = not user.get("active", True)
        users.update_one({"api_key": api_key}, {"$set": {"active": new_status}})
    token = get_token()
    return flask_redirect(f'/admin/apikeys?token={token}')

@admin_app.route('/usage')
@require_admin
def admin_usage():
    days = int(flask_request.args.get('days', 7))
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    usage_data = list(usage.find({"date": {"$gte": start_date.date().isoformat()}}).sort("date", 1))
    
    daily_usage = {}
    for doc in usage_data:
        date = doc.get("date")
        if date not in daily_usage:
            daily_usage[date] = {}
        for api_id in ["movie_search", "image_gen", "phone_lookup"]:
            daily_usage[date][api_id] = daily_usage[date].get(api_id, 0) + doc.get(api_id, 0)
    
    all_users = list(users.find())
    user_usage = []
    for user in all_users:
        doc = usage.find_one({"api_key": user.get("api_key"), "date": datetime.now(timezone.utc).date().isoformat()}) or {}
        total = sum(doc.get(a, 0) for a in ["movie_search", "image_gen", "phone_lookup"])
        user_usage.append({"name": user.get("name"), "telegram_id": user.get("telegram_id"), "plan": user.get("plan", "free"), "used": total})
    
    user_usage.sort(key=lambda x: x["used"], reverse=True)
    token = get_token()
    return render_template('usage.html', daily_usage=daily_usage, user_usage=user_usage[:50], days=days, token=token)

@admin_app.route('/test-api', methods=['GET', 'POST'])
@require_admin
def admin_test_api():
    test_result = None
    if flask_request.method == 'POST':
        api_key = flask_request.form.get('api_key')
        endpoint = flask_request.form.get('endpoint')
        params = flask_request.form.get('params')
        
        try:
            start_time = datetime.now()
            # Use localhost for internal API calls to avoid tunnel issues
            base_url = "http://localhost:8000"
            
            if endpoint == 'search':
                url = f"{base_url}/search"
                resp = httpx.get(url, params={"q": params or "test", "source": "terabox", "max_results": 5}, headers={"x-api-key": api_key}, timeout=30)
            elif endpoint == 'generate':
                url = f"{base_url}/generate"
                resp = httpx.post(url, params={"prompt": params or "sunset", "width": 512, "height": 512, "steps": 4}, headers={"x-api-key": api_key}, timeout=60)
            elif endpoint == 'lookup':
                url = f"{base_url}/lookup"
                resp = httpx.get(url, params={"number": params or "9876543210"}, headers={"x-api-key": api_key}, timeout=30)
            elif endpoint == 'usage':
                url = f"{base_url}/usage"
                resp = httpx.get(url, headers={"x-api-key": api_key}, timeout=30)
            elif endpoint == 'health':
                url = f"{base_url}/health"
                resp = httpx.get(url, timeout=10)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            if resp:
                try:
                    data = resp.json()
                    test_result = {"status_code": resp.status_code, "elapsed": f"{elapsed:.2f}s", "data": data}
                except:
                    test_result = {"status_code": resp.status_code, "elapsed": f"{elapsed:.2f}s", "content": resp.text[:500]}
        except httpx.ConnectError as e:
            test_result = {"error": "Cannot connect to API server. Make sure the server is running on localhost:8000", "details": str(e)}
        except Exception as e:
            test_result = {"error": str(e)}
    
    api_keys = [(u.get("api_key"), f"{u.get('name')} ({u.get('telegram_id')})") for u in users.find({"api_key": {"$exists": True}})]
    token = get_token()
    return render_template('test_api.html', test_result=test_result, api_keys=api_keys, token=token)

@admin_app.route('/orders')
@require_admin
def admin_orders():
    status_filter = flask_request.args.get('status', 'all')
    if status_filter == 'all':
        all_orders = list(orders.find().sort("created_at", -1))
    else:
        all_orders = list(orders.find({"status": status_filter}).sort("created_at", -1))
    
    token = get_token()
    return render_template('orders.html', orders=all_orders, status_filter=status_filter,
                         pending=orders.count_documents({"status": "pending"}),
                         approved=orders.count_documents({"status": "approved"}),
                         rejected=orders.count_documents({"status": "rejected"}), token=token)

@admin_app.route('/order/<order_id>/<action>')
@require_admin
def admin_order_action(order_id, action):
    order = orders.find_one({"order_id": order_id})
    if order:
        if action == "approve":
            tid = order["telegram_id"]
            plan_type = order.get("plan_type")
            
            if plan_type:
                config = get_config()
                plan = config.get("PLANS", {}).get(plan_type, {})
                duration = plan.get("duration_days", 7)
                users.update_one({"telegram_id": tid}, {"$set": {
                    "apis": list(config.get("APIS", {}).keys()),
                    "plan": plan_type,
                    "expires_at": datetime.now(timezone.utc) + timedelta(days=duration),
                    "active": True,
                }})
            else:
                apis = order.get("apis", [])
                users.update_one({"telegram_id": tid}, {"$set": {
                    "apis": apis,
                    "plan": "paid",
                    "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
                    "active": True,
                }})
            orders.update_one({"order_id": order_id}, {"$set": {"status": "approved"}})
        elif action == "reject":
            orders.update_one({"order_id": order_id}, {"$set": {"status": "rejected"}})
    
    token = get_token()
    return flask_redirect(f'/admin/orders?token={token}')

@admin_app.route('/settings', methods=['GET', 'POST'])
@require_admin
def admin_settings():
    config = get_config()
    
    if flask_request.method == 'POST':
        update_config("UPI_ID", flask_request.form.get('upi_id'))
        update_config("QR_IMAGE_URL", flask_request.form.get('qr_url'))
        update_config("CHANNEL_LINK", flask_request.form.get('channel_link'))
        update_config("API_BASE_URL", flask_request.form.get('api_base_url'))
        token = get_token()
        return flask_redirect(f'/admin/settings?token={token}')
    
    token = get_token()
    return render_template('settings.html', config=config, token=token)

# ── FastAPI Setup ─────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    users.create_index("api_key", unique=True)
    users.create_index("telegram_id", unique=True)
    usage.create_index([("api_key", 1), ("date", 1)])
    yield

app = FastAPI(
    title="AzTech API",
    description="🚀 Movie Search · Image Generation · Phone Lookup — by AzTech + Admin Panel",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files directory - use WEB_ROOT env or parent directory to find web folder
WEB_ROOT = os.environ.get("WEB_ROOT", os.path.dirname(BASE_DIR))
WEB_DIR = os.path.join(WEB_ROOT, 'web')
STATIC_DIR = os.path.join(WEB_DIR, "static")
TEMPLATE_DIR = os.path.join(WEB_DIR, 'templates')
# app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")  # Disabled for now

# Mount Flask admin at /admin
app.mount("/admin", WSGIMiddleware(admin_app))

# ── Helpers ───────────────────────────────────────────────────────────────────

def check_and_count(api_key: str, api_id: str):
    user = users.find_one({"api_key": api_key})
    if not user:
        raise HTTPException(401, "Invalid API key")
    if not user.get("active", True):
        raise HTTPException(403, "API key disabled. Contact @AzTechDeveloper")

    if user.get("telegram_id") == ADMIN_ID:
        t = datetime.now(timezone.utc).date().isoformat()
        doc = usage.find_one({"api_key": api_key, "date": t}) or {}
        used = doc.get(api_id, 0)
        usage.update_one({"api_key": api_key, "date": t}, {"$inc": {api_id: 1}, "$setOnInsert": {"api_key": api_key, "date": t}}, upsert=True)
        return {"user": user, "used": used + 1, "limit": 999999, "remaining": 999999, "is_admin": True}

    purchased = user.get("apis", [])
    is_free = user.get("plan") == "free"
    is_weekly = user.get("plan") == "weekly"
    is_monthly = user.get("plan") == "monthly"

    if not (is_weekly or is_monthly):
        if api_id not in purchased and not is_free:
            raise HTTPException(403, f"You haven't purchased the {APIS[api_id]['name']} API. Buy it via @AzTechAPIBot")

    if is_weekly or is_monthly:
        limit = PLANS[user.get("plan")]["daily_limit"]
    else:
        limit = APIS[api_id]["free_limit"] if is_free else APIS[api_id]["daily_limit"]
    
    t = datetime.now(timezone.utc).date().isoformat()
    doc = usage.find_one({"api_key": api_key, "date": t}) or {}
    used = doc.get(api_id, 0)

    if used >= limit:
        raise HTTPException(429, {"error": "Daily limit reached", "used": used, "limit": limit, "plan": user.get("plan"), "reset": "midnight UTC", "upgrade": "Contact @AzTechAPIBot"})

    usage.update_one({"api_key": api_key, "date": t}, {"$inc": {api_id: 1}, "$setOnInsert": {"api_key": api_key, "date": t}}, upsert=True)
    return {"user": user, "used": used, "limit": limit, "remaining": limit - used - 1}

# ── Filters ───────────────────────────────────────────────────────────────────

TERABOX_DOMAINS = ["terabox.com","1024terabox.com","teraboxapp.com","freeterabox.com","4funbox.com","mirrobox.com","nephobox.com","terafileshare.com","momerybox.com","tibibox.com","teraboxlink.com","teraboxmovie.in","teraboxpro.com","terabox-sharer.com","bdupload.net","uploadbuzz.net","linkbnk.net","gdtot.com","terashare.me","hypershare.net"]
VALID_TB_PATHS = [r"/s/[a-zA-Z0-9_-]+",r"/sharing/link\?.*surl=[a-zA-Z0-9_-]+",r"/sharing/\?surl=[a-zA-Z0-9_-]+",r"/[a-z]+/sharing/link\?.*surl=[a-zA-Z0-9_-]+"]
GDRIVE_PATTERNS = [r"/file/d/[a-zA-Z0-9_-]+",r"/drive/folders/[a-zA-Z0-9_-]+",r"id=[a-zA-Z0-9_-]+"]
JUNK_WORDS = ["login","sign in","sign up","cloud storage","free storage","pricing","plans","about us","user center","download searching","searching app","searching video","searching: everything","0 file","file (s) including are shared from","how to","what is searching","why is searching","earn online","400 million","free cloud","biggest free"]
STOP_WORDS = {"of","the","a","an","in","on","at","to","and","or","is","are"}

def _is_valid_tb(url):
    return any(d in url.lower() for d in TERABOX_DOMAINS) and any(re.search(p, url, re.I) for p in VALID_TB_PATHS)

def _is_valid_gd(url):
    return "drive.google.com" in url.lower() and any(re.search(p, url, re.I) for p in GDRIVE_PATTERNS)

def _is_junk(title):
    return any(j in title.lower() for j in JUNK_WORDS)

def _matches(title, snippet, query):
    """
    Check if result is relevant to query.
    Handles DDG's joined words issue (e.g. 'ManofSteel' instead of 'Man of Steel')
    by checking both normal and space-stripped versions.
    """
    words = [w for w in query.lower().split() if w not in STOP_WORDS and len(w) > 2]
    if not words: return True
    
    # Normal check — words with spaces
    combined_normal = (title + " " + snippet).lower()
    
    # Nospace check — handles 'ManofSteel', 'manofsteel' etc.
    combined_nospace = combined_normal.replace(" ", "")
    
    for word in words:
        # Must appear in either normal OR nospace version
        if word not in combined_normal and word not in combined_nospace:
            return False
    
    return True

def _clean(title):
    for s in [" - Share Files Online & Send Larges Files with Searching"," - Share Files Online & Send Large Files with Searching"," - Searching","- Searching", " | Searching"]:
        title = title.replace(s, "")
    return title.split(" - ")[0].strip() if " - " in title else title.strip()

def _filter_tb(raw, query):
    out, seen = [], set()
    for i, r in enumerate(raw, 1):
        url, title, snip = r.get("href",""), r.get("title",""), r.get("body","")
        if not _is_valid_tb(url) or _is_junk(title) or not _matches(title, snip, query): continue
        surl = (re.search(r'surl=([a-zA-Z0-9_-]+)', url) or type('',(),{'group':lambda s,n:url})()).group(1)
        if surl in seen: continue
        seen.add(surl)
        out.append({"position":i,"title":_clean(title),"link":url,"snippet":snip,"source":"TeraBox"})
    return out

def _filter_gd(raw, query):
    out, seen = [], set()
    for i, r in enumerate(raw, 1):
        url, title, snip = r.get("href",""), r.get("title",""), r.get("body","")
        if not _is_valid_gd(url) or _is_junk(title) or not _matches(title, snip, query): continue
        m = re.search(r'/(?:file/d|folders)/([a-zA-Z0-9_-]+)', url)
        key = m.group(1) if m else url
        if key in seen: continue
        seen.add(key)
        out.append({"position":i,"title":_clean(title),"link":url,"snippet":snip,"source":"GoogleDrive"})
    return out

# ── API Routes ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "AzTech API", "admin": "/admin", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

@app.get("/search", tags=["Movie Search"])
def movie_search(q: str = Query(...), source: str = Query("terabox"), max_results: int = Query(10, ge=1, le=20), x_api_key: str = Header(...)):
    info = check_and_count(x_api_key, "movie_search")
    results = []
    proxy_error = None
    
    try:
        # Use ddgs without proxy (proxy might not be available)
        ddgs = DDGS(timeout=20)
        
        if source in ("terabox", "both"):
            try:
                # Search for actual file links with /s/ or sharing/link patterns
                raw = list(ddgs.text(f"{q} terabox.com/s/", region="wt-wt", safesearch="off", max_results=30))
                print(f"[DEBUG] Raw results: {len(raw)}")
                filtered = _filter_tb(raw, q)
                print(f"[DEBUG] Filtered results: {len(filtered)}")
                results += filtered
            except Exception as e:
                print(f"[DEBUG] First search failed: {e}")
                # Fallback to site search
                try:
                    raw = list(ddgs.text(f"{q} terabox.com sharing", region="wt-wt", safesearch="off", max_results=30))
                    print(f"[DEBUG] Fallback raw results: {len(raw)}")
                    filtered = _filter_tb(raw, q)
                    print(f"[DEBUG] Fallback filtered results: {len(filtered)}")
                    results += filtered
                except Exception as e2:
                    print(f"[DEBUG] Fallback also failed: {e2}")
        if source in ("gdrive", "both"):
            try:
                raw = list(ddgs.text(f"site:drive.google.com {q}", region="wt-wt", safesearch="off", max_results=30))
                results += _filter_gd(raw, q)
            except Exception as e:
                try:
                    raw = list(ddgs.text(f"{q} google drive link", region="wt-wt", safesearch="off", max_results=30))
                    results += _filter_gd(raw, q)
                except:
                    pass
    except Exception as e:
        # Return error info if search completely fails
        return {"success": False, "error": f"Search failed: {str(e)}", "query": q, "source": source, "count": 0, "remaining": info["remaining"], "results": []}
    
    return {"success": True, "query": q, "source": source, "count": len(results[:max_results]), "remaining": info["remaining"], "results": results[:max_results]}

@app.post("/generate", tags=["Image Generation"])
async def generate_image(prompt: str = Query(...), width: int = Query(512), height: int = Query(512), steps: int = Query(4), x_api_key: str = Header(...)):
    info = check_and_count(x_api_key, "image_gen")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(IMAGE_API_URL, json={"prompt": prompt, "width": width, "height": height, "steps": steps})
        if resp.status_code != 200:
            raise HTTPException(502, f"Image API error: {resp.text[:200]}")
        
        # Convert image to base64 for JSON response
        import base64
        image_b64 = base64.b64encode(resp.content).decode('utf-8')
        return {"success": True, "prompt": prompt, "image": image_b64, "remaining": info["remaining"]}
    except httpx.TimeoutException:
        raise HTTPException(504, "Image generation timed out")

@app.get("/lookup", tags=["Phone Lookup"])
async def phone_lookup(number: str = Query(...), x_api_key: str = Header(...)):
    if not re.match(r"^[6-9]\d{9}$", number):
        raise HTTPException(400, "Invalid number")
    info = check_and_count(x_api_key, "phone_lookup")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(PHONE_API_ENDPOINT, params={"key": PHONE_API_KEY, "num": number})
        if resp.status_code != 200:
            raise HTTPException(502, f"Phone API error")
        data = resp.json()
        # Replace credit username from external API
        if isinstance(data, dict) and "credit" in data:
            data["credit"] = "@aztechdeveloper"
    except httpx.TimeoutException:
        raise HTTPException(504, "Phone lookup timed out")
    return {"success": True, "number": number, "remaining": info["remaining"], "data": data}

@app.get("/usage", tags=["Usage"])
def get_usage(x_api_key: str = Header(...)):
    user = users.find_one({"api_key": x_api_key})
    if not user:
        raise HTTPException(401, "Invalid API key")

    if user.get("telegram_id") == ADMIN_ID:
        t = datetime.now(timezone.utc).date().isoformat()
        doc = usage.find_one({"api_key": x_api_key, "date": t}) or {}
        stats = {api_id: {"name": meta["name"], "purchased": True, "used": doc.get(api_id, 0), "limit": "unlimited", "remaining": "unlimited"} for api_id, meta in APIS.items()}
        return {"api_key": x_api_key[-6:] + "...", "plan": "admin", "date": t, "purchased_apis": list(APIS.keys()), "usage": stats, "is_admin": True}

    t = datetime.now(timezone.utc).date().isoformat()
    doc = usage.find_one({"api_key": x_api_key, "date": t}) or {}
    purchased = user.get("apis", [])
    plan = user.get("plan", "free")
    stats = {api_id: {"name": meta["name"], "purchased": api_id in purchased or plan == "free", "used": doc.get(api_id, 0), "limit": meta["free_limit"] if plan == "free" else (meta["daily_limit"] if api_id in purchased else 0), "remaining": max(0, (meta["free_limit"] if plan == "free" else meta["daily_limit"]) - doc.get(api_id, 0))} for api_id, meta in APIS.items()}
    return {"api_key": x_api_key[-6:] + "...", "plan": plan, "date": t, "purchased_apis": purchased, "usage": stats}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)