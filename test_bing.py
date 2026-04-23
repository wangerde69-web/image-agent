import requests, re, json
from urllib.parse import unquote

url = "https://cn.bing.com/images/async?q=%E8%B7%91%E6%AD%A5%E6%9C%BA&first=0&count=5"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
resp = requests.get(url, headers=headers, timeout=15)
html = resp.text
urls_raw = re.findall(r'mediaurl=(https?[^&"<\s]+)', html)
print(f"Found {len(urls_raw)} URLs")
for i, u in enumerate(urls_raw[:5]):
    decoded = unquote(unquote(u))
    print(f"[{i+1}] {decoded[:100]}")
    try:
        r2 = requests.get(decoded, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        ct = r2.headers.get("Content-Type","?")
        sz = len(r2.content)
        print(f"    -> {ct} | {sz//1024}KB | OK" if sz > 5000 else f"    -> too small: {sz}B")
    except Exception as e:
        print(f"    -> FAIL: {e}")
