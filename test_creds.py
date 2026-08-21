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
        r = await client.post("https://www.naukri.com/central-login-services/v0/credentials", json=payload)
        print("Status:", r.status_code)
        print("Headers:", dict(r.headers))
        print("Response:", r.text)

asyncio.run(test())