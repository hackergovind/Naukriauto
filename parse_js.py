import httpx
import re

r = httpx.get("https://static.naukimg.com/s/5/105/j/app_v467.min.js")
text = r.text

# Search for login url / endpoints
patterns = [
    r'https?://[^\s"\'`]+',
    r'/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-/]+login[a-zA-Z0-9_\-/]*',
    r'/central-login-services/[^\s"\'`]+',
    r'/gateway/v\d+/[^\s"\'`]+',
    r'url\s*:\s*["\']([^"\']+)["\']'
]

found = set()
for pat in patterns:
    for m in re.finditer(pat, text):
        found.add(m.group(0))

print("Total matches:", len(found))
for item in sorted(found):
    if any(k in item.lower() for k in ["login", "auth", "profile", "password", "resume", "gateway"]):
        print(item)