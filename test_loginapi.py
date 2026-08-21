import asyncio
import httpx
from src.config import Config

async def test():
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
        await client.get("https://www.naukri.com/nlogin/login")
        payload = {
            "username": Config.NAUKRI_EMAIL,
            "password": Config.NAUKRI_PASSWORD
        }
        for ep in ["https://www.naukri.com/loginapi/v3/login", "https://www.naukri.com/loginapi/v5/login"]:
            r = await client.post(ep, json=payload)
            print(f"Endpoint: {ep} -> Status: {r.status_code}")
            print("Response:", r.text[:300])

asyncio.run(test())