import requests, re, json

# Test 360 image search
url = "https://image.so.com/v?q=%E8%B7%91%E6%AD%A5%E6%9C%BA&sn=0&pn=20"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://image.so.com/",
}
try:
    resp = requests.get(url, headers=headers, timeout=15)
    print("Status:", resp.status_code, "Length:", len(resp.text))
    data = resp.json()
    print("Keys:", list(data.keys()))
    items = data.get("list", [])
    print("Items count:", len(items))
    if items:
        print("First item keys:", list(items[0].keys()))
        print("First thumb:", items[0].get("thumb", "")[:80])
        print("First img:", items[0].get("img", "")[:80])
except Exception as e:
    print("Error:", e)
    print("Response text (first 200):", resp.text[:200])
