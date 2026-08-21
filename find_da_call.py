import httpx
import re

r = httpx.get("https://static.naukimg.com/s/5/105/j/app_v467.min.js")
text = r.text

matches = [m.start() for m in re.finditer(r'[\(,\s=]Da[\),;\s]', text)]
print("Total Da references:", len(matches))
for m in matches:
    snippet = text[max(0, m-200):min(len(text), m+300)]
    if any(k in snippet for k in ["post", "ajax", "fetch", "http", "axios", "data", "json", "login"]):
        print("--- SNIPPET ---")
        print(snippet)