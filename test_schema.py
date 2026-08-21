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

    payloads = [
        {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD},
        {"loginDetails": {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}},
        {"user": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD},
        {"email": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}
    ]

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        await client.get("https://www.naukri.com/nlogin/login")
        for p in payloads:
            r = await client.post("https://www.naukri.com/central-login-services/v1/login", json=p)
            print(f"Payload keys: {list(p.keys())} -> Status: {r.status_code}")
            print("Response:", r.text[:250])
            if r.status_code == 200:
                print("LOGIN SUCCESSFUL!")
                break

asyncio.run(test())