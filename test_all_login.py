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
        r_init = await client.get("https://www.naukri.com/nlogin/login")
        
        # Test 1: central-login-services with username & password
        p1 = {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}
        r1 = await client.post("https://www.naukri.com/central-login-services/v1/login", json=p1)
        print("Test 1 (central-login JSON):", r1.status_code, r1.text[:200])

        # Test 2: loginapi/v5/login with form data
        p2 = {"USERNAME": Config.NAUKRI_EMAIL, "PASSWORD": Config.NAUKRI_PASSWORD, "ISLOGINBYEMAIL": "1"}
        r2 = await client.post("https://www.naukri.com/loginapi/v5/login", data=p2)
        print("Test 2 (loginapi/v5 Form):", r2.status_code, r2.text[:200])

        # Test 3: loginapi/v3/login with form data
        p3 = {"USERNAME": Config.NAUKRI_EMAIL, "PASSWORD": Config.NAUKRI_PASSWORD, "ISLOGINBYEMAIL": "1"}
        r3 = await client.post("https://www.naukri.com/loginapi/v3/login", data=p3)
        print("Test 3 (loginapi/v3 Form):", r3.status_code, r3.text[:200])

        # Check cookies after all
        cookies = [c.name for c in client.cookies.jar]
        print("Cookies present:", cookies)

asyncio.run(test())