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
        "Clientid": "d301720d52264e63bb1326396001e4f3",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        await client.get("https://www.naukri.com/nlogin/login")
        
        payloads = [
            {"USERNAME": Config.NAUKRI_EMAIL, "PASSWORD": Config.NAUKRI_PASSWORD, "ISLOGINBYEMAIL": True},
            {"USERNAME": Config.NAUKRI_EMAIL, "PASSWORD": Config.NAUKRI_PASSWORD, "ISLOGINBYEMAIL": "true"},
            {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD, "isLoginByEmail": True},
            {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD, "isLoginByEmail": "true"}
        ]

        for i, p in enumerate(payloads):
            r = await client.post("https://www.naukri.com/loginapi/v5/login", json=p)
            print(f"Payload {i} -> Status: {r.status_code}")
            print("Response:", r.text[:300])
            if r.status_code == 200:
                print("LOGIN SUCCEEDED!")
                break

asyncio.run(test())