import httpx
import re

r = httpx.get("https://static.naukimg.com/s/5/105/j/app_v467.min.js")
text = r.text

matches = [m.start() for m in re.finditer(r'\buc\b', text)]
print("Matches found:", len(matches))
for m in matches[:10]:
    snippet = text[max(0, m-150):min(len(text), m+250)]
    if "method" in snippet or "url" in snippet or "post" in snippet or "http" in snippet or "data" in snippet:
        print("--- SNIPPET ---")
        print(snippet)