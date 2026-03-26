# update_url.py - Update the API_BASE_URL in MongoDB
# Run this after starting the tunnel to update the public URL

import sys
import os

# Add api folder to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

from config import update_config

def main():
    url = input("Enter new Cloudflare URL: ").strip()
    
    if not url:
        print("❌ No URL provided")
        return
    
    if not url.startswith("http"):
        url = "https://" + url
    
    update_config("API_BASE_URL", url)
    print(f"✅ API_BASE_URL updated to: {url}")

if __name__ == "__main__":
    main()
