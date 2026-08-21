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
        # Pre-fetch cookies
        await client.get("https://www.naukri.com/nlogin/login")
        
        # Test central-login-services/v1/login
        payload = {
            "username": Config.NAUKRI_EMAIL,
            "password": Config.NAUKRI_PASSWORD
        }
        
        print("Testing central-login-services/v1/login...")
        r = await client.post("https://www.naukri.com/central-login-services/v1/login", json=payload)
        print("Status:", r.status_code)
        print("Resp:", r.text[:300])

        if r.status_code == 200:
            print("\nSUCCESS! Testing Profile Fetch...")
            p_resp = await client.get("https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/profiles")
            print("Profile Status:", p_resp.status_code)
            print("Profile Data:", p_resp.text[:300])

asyncio.run(test())