# run.py — Start all AzTech services
# 1. Start API server
# 2. Start Cloudflare tunnel
# 3. Update MongoDB with tunnel URL
# 4. Start Telegram bot

import os
import sys
import time
import subprocess
import signal
import re
import threading
import random

# Configuration
MONGO_URI = "mongodb+srv://aztech:ayazahmed1122@cluster0.mhuaw3q.mongodb.net/aztech_api?retryWrites=true&w=majority"

processes = []

def print_banner():
    print("=" * 50)
    print("   AzTech API + Telegram Bot Launcher")
    print("=" * 50)
    print()

def kill_processes():
    # Optional: uncomment to kill existing processes
    # print("[1/5] Cleaning up old processes...")
    # os.system("taskkill /F /IM python.exe 2>nul")
    # os.system("taskkill /F /IM cloudflared.exe 2>nul")
    # print("   Done.")
    print("[1/5] Starting services...")
    print()

def start_api_server():
    print("[2/5] Starting API server...")
    
    api_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api")
    
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=api_dir,
        stdout=open("api.log", "w"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
        env={**os.environ, "WEB_ROOT": os.path.dirname(os.path.abspath(__file__))}
    )
    processes.append(proc)
    
    print("   Waiting for API to start...")
    time.sleep(3)
    print("   ✅ API server started!")
    print()

def start_tunnel():
    print("[3/5] Starting Cloudflare Tunnel...")
    
    # Try to delete old file, handle gracefully if in use
    tunnel_filename = "tunnel_url.txt"
    try:
        if os.path.exists(tunnel_filename):
            try:
                os.remove(tunnel_filename)
            except (PermissionError, OSError):
                # File is locked, use unique filename
                timestamp = str(int(time.time()))
                random_suffix = str(random.randint(1000, 9999))
                tunnel_filename = f"tunnel_url_{timestamp}_{random_suffix}.txt"
    except Exception:
        pass
    
    os.environ["TUNNEL_FILE"] = tunnel_filename
    tunnel_file = tunnel_filename
    
    # Use cmd /c to run npx on Windows
    proc = subprocess.Popen(
        ["cmd", "/c", f"npx cloudflared tunnel --url http://localhost:8000"],
        stdout=open(tunnel_file, "w"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    processes.append(proc)
    
    print("   Waiting for tunnel URL...")
    tunnel_url = None
    
    tunnel_file = os.environ.get("TUNNEL_FILE", "tunnel_url.txt")
    
    for i in range(20):
        time.sleep(2)
        
        if os.path.exists(tunnel_file):
            with open(tunnel_file, "r") as f:
                content = f.read()
                match = re.search(r'https://[a-zA-Z0-9.-]+trycloudflare\.com', content)
                if match:
                    tunnel_url = match.group(0)
                    break
    
    print()
    return tunnel_url

def update_mongodb(tunnel_url):
    print("[4/5] Updating MongoDB...")
    
    if not tunnel_url:
        print("   ❌ No tunnel URL")
        return False
    
    try:
        from api.config import update_config
        update_config("API_BASE_URL", tunnel_url)
        print(f"   ✅ {tunnel_url}")
        print()
        return True
    except Exception as e:
        print(f"   ⚠️ Error updating MongoDB: {e}")
        # Fallback: try direct MongoDB update
        try:
            from pymongo import MongoClient
            mongo = MongoClient(MONGO_URI)
            db = mongo["aztech_api"]
            config_col = db["config"]
            config_col.update_one(
                {"_id": "bot_config"},
                {"$set": {"API_BASE_URL": tunnel_url}},
                upsert=True
            )
            print(f"   ✅ {tunnel_url}")
            print()
            return True
        except Exception as e2:
            print(f"   ❌ Failed: {e2}")
            return False

def start_bot():
    print("[4/5] Starting Telegram Bot...")
    
    bot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot")
    
    proc = subprocess.Popen(
        [sys.executable, "bot.py"],
        cwd=bot_dir,
        stdout=open("bot.log", "w"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    processes.append(proc)
    
    print("   ✅ Bot started!")
    print()

def main():
    print_banner()
    
    try:
        kill_processes()
        start_api_server()
        tunnel_url = start_tunnel()
        
        if tunnel_url:
            update_mongodb(tunnel_url)
        else:
            print("[4/5] WARNING: No tunnel URL")
        
        start_bot()
        
        print("=" * 50)
        print("   All services started!")
        print("=" * 50)
        print()
        print("   API Server:      http://localhost:8000")
        print("   Admin Panel:     http://localhost:8000/admin")
        print("   Bot:             @AzTechAPIBot")
        if tunnel_url:
            print(f"   Public URL:      {tunnel_url}")
            print(f"   Admin URL:       {tunnel_url}/admin")
        print()
        print("   Admin Login:     aztech / 1729")
        print()
        print("   Press Ctrl+C to exit")
        print()
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        for p in processes:
            try:
                p.terminate()
            except:
                pass

if __name__ == "__main__":
    main()