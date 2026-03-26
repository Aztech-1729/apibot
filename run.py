import os
import sys
import time
import subprocess
import re
import signal

MONGO_URI = "mongodb+srv://aztech:ayazahmed1122@cluster0.mhuaw3q.mongodb.net/aztech_api?retryWrites=true&w=majority"

processes = []

def print_banner():
    print("=" * 50)
    print("   AzTech API + Telegram Bot Launcher")
    print("=" * 50)
    print()

def start_api():
    print("[1/4] Starting API server...")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=open("api.log", "w"),
        stderr=subprocess.STDOUT
    )
    processes.append(proc)

    # Wait until API is ready
    import requests
    for _ in range(10):
        try:
            r = requests.get("http://127.0.0.1:8000/health")
            if r.status_code == 200:
                print("   ✅ API ready!")
                print()
                return
        except:
            pass
        time.sleep(1)

    print("   ⚠️ API may not be ready yet\n")


def start_tunnel():
    print("[2/4] Starting Cloudflare tunnel...")

    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    processes.append(proc)

    tunnel_url = None

    for _ in range(30):
        line = proc.stdout.readline()
        if line:
            print(line.strip())
            match = re.search(r'https://[a-zA-Z0-9.-]+trycloudflare\.com', line)
            if match:
                tunnel_url = match.group(0)
                break

    print()
    return tunnel_url


def update_mongo(url):
    print("[3/4] Updating MongoDB...")

    try:
        from pymongo import MongoClient
        mongo = MongoClient(MONGO_URI)
        db = mongo["aztech_api"]

        db["config"].update_one(
            {"_id": "bot_config"},
            {"$set": {"API_BASE_URL": url}},
            upsert=True
        )

        print(f"   ✅ Updated: {url}\n")

    except Exception as e:
        print(f"   ❌ Mongo error: {e}\n")


def start_bot():
    print("[4/4] Starting bot...")

    proc = subprocess.Popen(
        [sys.executable, "bot/bot.py"],
        stdout=open("bot.log", "w"),
        stderr=subprocess.STDOUT
    )
    processes.append(proc)

    print("   ✅ Bot started!\n")


def main():
    print_banner()

    try:
        start_api()
        tunnel_url = start_tunnel()

        if tunnel_url:
            update_mongo(tunnel_url)
        else:
            print("⚠️ Tunnel URL not found\n")

        start_bot()

        print("=" * 50)
        print("   🚀 ALL SERVICES RUNNING")
        print("=" * 50)
        print()

        print("Local API:   http://127.0.0.1:8000")
        print("Admin:       http://127.0.0.1:8000/admin")

        if tunnel_url:
            print(f"Public URL:  {tunnel_url}")
            print(f"Admin URL:   {tunnel_url}/admin")

        print("\nPress CTRL+C to stop\n")

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
