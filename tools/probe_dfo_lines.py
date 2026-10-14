"""Probe: what does a DailyFaceoff line-combinations page carry in its embedded data? Prints structure only."""
import json, re, sys
import requests

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.dailyfaceoff.com/teams/washington-capitals/line-combinations"
r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "text/html"})
print("status", r.status_code, "bytes", len(r.text))
m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.S)
if not m:
    print("no __NEXT_DATA__; first 1500 chars of body text:")
    print(re.sub(r"<[^>]+>", " ", r.text)[:1500])
    sys.exit(0)
d = json.loads(m.group(1))
pp = d.get("props", {}).get("pageProps", {})
print("pageProps keys:", list(pp.keys()))

def walk(x, path="", depth=0):
    if depth > 4:
        return
    if isinstance(x, dict):
        for k, v in list(x.items())[:40]:
            if isinstance(v, (dict, list)):
                print(f"{path}.{k}: {type(v).__name__} len={len(v)}")
                walk(v, f"{path}.{k}", depth + 1)
            else:
                print(f"{path}.{k} = {str(v)[:80]!r}")
    elif isinstance(x, list) and x:
        print(f"{path}[0]: {type(x[0]).__name__}")
        walk(x[0], f"{path}[0]", depth + 1)

walk(pp, "pageProps")
