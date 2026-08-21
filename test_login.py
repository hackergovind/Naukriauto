import asyncio
import httpx
from src.config import Config

async def main():
    endpoints = [
        ("https://www.naukri.com/nlogin/login", "POST_JSON"),
        ("https://auth.naukri.com/v1/login", "POST_JSON"),
        ("https://www.naukri.com/gateway/v1/auth/login", "POST_JSON"),
        ("https://www.naukri.com/napi/v1/auth/login", "POST_JSON"),
        ("https://www.naukri.com/nlogin/v1/login", "POST_JSON"),
        ("https://login.naukri.com/nlogin/login", "POST_JSON"),
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.naukri.com",
        "Referer": "https://www.naukri.com/nlogin/login",
        "Appid": "106",
        "Systemid": "106",
        "Clientid": "d301720d52264e63bb1326396001e4f3"
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # Get base cookies
        await client.get("https://www.naukri.com/nlogin/login")
        print("Base cookies set:", [c.name for c in client.cookies.jar])

        payload = {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}
        
        for url, mtype in endpoints:
            try:
                r = await client.post(url, json=payload, timeout=10.0)
                print(f"URL: {url} -> Status: {r.status_code}, Type: {r.headers.get('content-type')}")
                if r.status_code < 400:
                    print("Response:", r.text[:200])
            except Exception as e:
                print(f"URL: {url} -> Error: {e}")

asyncio.run(main())