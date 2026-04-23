import sys, re, requests

url = "https://image.baidu.com/search/index?word=%E8%B7%91%E6%AD%A5%E6%9C%BA&pn=0"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.baidu.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
resp = requests.get(url, headers=headers, timeout=15)
html = resp.text
print("HTML length:", len(html))

# Try multiple URL patterns
for pat in [r'"middleUrl":"([^"]+)"', r'"thumbURL":"([^"]+)"', r'"hoverURL":"([^"]+)"', r'src="(https?://[^"]+\.jpg)"']:
    m = re.findall(pat, html)
    print(f"Pattern {pat[:30]}...: {len(m)} matches")
    if m:
        print("  First:", m[0][:80])
