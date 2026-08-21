import asyncio
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from src.config import Config, logger

class NaukriClient:
    def __init__(self):
        self.session_file = Config.SESSION_FILE_PATH
        self.auth_token: Optional[str] = None
        self.base_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Appid": "106",
            "Systemid": "106",
            "Clientid": "d301720d52264e63bb1326396001e4f3",
            "Origin": "https://www.naukri.com",
            "Referer": "https://www.naukri.com/mnjuser/profile"
        }

    def _load_saved_session(self) -> tuple[dict, Optional[str]]:
        """Load saved cookies and auth token safely."""
        if self.session_file.exists():
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        cookies = data.get("cookies", data)
                        token = data.get("token")
                        if isinstance(cookies, dict):
                            return cookies, token
            except Exception as e:
                logger.warning("Failed to load saved session: {}", e)
        return {}, None

    def _extract_cookies_safely(self, client: httpx.AsyncClient) -> dict:
        """Extract cookies from client.cookies.jar safely avoiding CookieConflict."""
        cookies = {}
        try:
            for cookie in client.cookies.jar:
                cookies[cookie.name] = cookie.value
        except Exception:
            pass
        return cookies

    def _save_session(self, cookies: dict, token: Optional[str] = None):
        """Save session cookies and token to session.json."""
        try:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "cookies": cookies,
                "token": token or self.auth_token
            }
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info("Saved updated session to {}", self.session_file)
        except Exception as e:
            logger.warning("Could not save session: {}", e)

    def _get_auth_headers(self) -> dict:
        headers = dict(self.base_headers)
        if self.auth_token:
            token_val = self.auth_token if self.auth_token.startswith("Bearer ") else f"Bearer {self.auth_token}"
            headers["Authorization"] = token_val
            headers["X-Token"] = self.auth_token
        return headers

    async def _login(self, client: httpx.AsyncClient) -> bool:
        """Perform login to Naukri using credentials."""
        logger.info("Authenticating with Naukri for: {}", Config.NAUKRI_EMAIL)
        
        # Step 1: Pre-fetch cookies / CSRF
        try:
            await client.get(
                "https://www.naukri.com/nlogin/login",
                headers=self.base_headers,
                timeout=15.0
            )
        except Exception:
            pass

        # Step 2: Login endpoints
        login_targets = [
            {
                "url": "https://www.naukri.com/nlogin/login",
                "json": {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}
            },
            {
                "url": "https://auth.naukri.com/v1/login",
                "json": {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}
            },
            {
                "url": "https://www.naukri.com/gateway/v1/auth/login",
                "json": {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}
            },
            {
                "url": "https://www.naukri.com/nlogin/login",
                "data": {"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD}
            }
        ]

        last_error = ""
        login_success = False

        for target in login_targets:
            try:
                h = dict(self.base_headers)
                if "json" in target:
                    h["Content-Type"] = "application/json"
                    resp = await client.post(target["url"], json=target["json"], headers=h, timeout=20.0)
                else:
                    h["Content-Type"] = "application/x-www-form-urlencoded"
                    resp = await client.post(target["url"], data=target["data"], headers=h, timeout=20.0)

                logger.info("Login attempt to {} returned HTTP {}", target["url"], resp.status_code)

                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                        token = data.get("token") or data.get("accessToken") or data.get("data", {}).get("token")
                        if token:
                            self.auth_token = token
                            logger.info("Retrieved auth token from login response")

                        if data.get("status") == "success" or "userId" in data or "user" in data or self.auth_token:
                            login_success = True
                            break
                    except Exception:
                        pass

                    cookies = self._extract_cookies_safely(client)
                    if "naukri_session" in cookies or "_naukri_id" in cookies or "AUTH_KEY" in cookies or "nId" in cookies:
                        login_success = True
                        break
                elif resp.status_code in (301, 302, 303):
                    login_success = True
                    break
                else:
                    last_error = f"HTTP {resp.status_code} ({resp.text[:120]})"
            except Exception as ex:
                last_error = str(ex)
                continue

        # Verify profile accessible
        if not login_success:
            try:
                check_p = await client.get("https://www.naukri.com/mnjuser/profile", headers=self.base_headers, timeout=15.0)
                if "nlogin" not in str(check_p.url) and check_p.status_code == 200:
                    login_success = True
            except Exception:
                pass

        if not login_success:
            raise Exception(f"Login failed. Please verify NAUKRI_EMAIL and NAUKRI_PASSWORD in .env. Reason: {last_error or 'Wrong credentials or Captcha required'}")

        saved_cookies = self._extract_cookies_safely(client)
        self._save_session(saved_cookies, self.auth_token)
        logger.info("Login successful!")
        return True

    async def get_current_headline(self) -> Dict[str, Any]:
        """Fetch current resume headline from Naukri."""
        result = {"success": False, "headline": "", "message": ""}
        saved_cookies, saved_token = self._load_saved_session()
        self.auth_token = saved_token

        async with httpx.AsyncClient(cookies=saved_cookies, follow_redirects=True) as client:
            headers = self._get_auth_headers()
            
            # Try API first
            try:
                resp = await client.get(
                    "https://www.naukri.com/gateway/v1/profiles/userProfile",
                    headers=headers,
                    timeout=20.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    h = (
                        data.get("profile", {}).get("resumeHeadline") or
                        data.get("resumeHeadline") or
                        data.get("data", {}).get("resumeHeadline")
                    )
                    if h:
                        result["headline"] = h.strip()
                        result["success"] = True
                        result["message"] = "Fetched successfully."
                        return result
            except Exception:
                pass

            # Try Web Profile HTML
            try:
                resp = await client.get("https://www.naukri.com/mnjuser/profile", headers=headers, timeout=20.0)
                if "nlogin" in str(resp.url):
                    await self._login(client)
                    headers = self._get_auth_headers()
                    resp = await client.get("https://www.naukri.com/mnjuser/profile", headers=headers, timeout=20.0)

                soup = BeautifulSoup(resp.text, "html.parser")
                el = soup.select_one(".resumeHeadline .msg, .resumeHeadline .widgetCont, div.resumeHeadlineTxt, textarea#resumeHeadlineTxt")
                if el:
                    result["headline"] = (el.get_text(strip=True) or el.get("value", "")).strip()
                    result["success"] = True
                    result["message"] = "Fetched successfully."
                    return result
            except Exception as e:
                result["message"] = str(e)

        return result

    async def update_profile_headline(self, custom_headline: Optional[str] = None) -> Dict[str, Any]:
        """Updates Naukri profile headline by toggling a dot (or setting custom headline)."""
        result = {
            "success": False,
            "old_headline": "",
            "new_headline": "",
            "message": ""
        }

        saved_cookies, saved_token = self._load_saved_session()
        self.auth_token = saved_token

        async with httpx.AsyncClient(cookies=saved_cookies, follow_redirects=True) as client:
            headers = self._get_auth_headers()
            
            # Step 1: Ensure authenticated session
            logger.info("Verifying authentication...")
            try:
                check_resp = await client.get(
                    "https://www.naukri.com/gateway/v1/profiles/userProfile",
                    headers=headers,
                    timeout=15.0
                )
            except Exception:
                check_resp = None

            if not check_resp or check_resp.status_code in (401, 403) or "nlogin" in str(check_resp.url):
                logger.info("Session expired or not logged in. Authenticating...")
                await self._login(client)
                headers = self._get_auth_headers()
                check_resp = await client.get(
                    "https://www.naukri.com/gateway/v1/profiles/userProfile",
                    headers=headers,
                    timeout=15.0
                )

            # Step 2: Get current headline
            current_headline = ""
            if check_resp and check_resp.status_code == 200:
                try:
                    data = check_resp.json()
                    current_headline = (
                        data.get("profile", {}).get("resumeHeadline") or
                        data.get("resumeHeadline") or
                        data.get("data", {}).get("resumeHeadline") or ""
                    )
                except Exception:
                    pass

            if not current_headline:
                p_resp = await client.get("https://www.naukri.com/mnjuser/profile", headers=headers, timeout=20.0)
                soup = BeautifulSoup(p_resp.text, "html.parser")
                el = soup.select_one(".resumeHeadline .msg, .resumeHeadline .widgetCont, div.resumeHeadlineTxt, textarea#resumeHeadlineTxt")
                if el:
                    current_headline = el.get_text(strip=True) or el.get("value", "")

            current_headline = current_headline.strip() if current_headline else "Experienced Software Professional"
            result["old_headline"] = current_headline

            # Step 3: Compute new headline (Toggle dot)
            if custom_headline:
                new_headline = custom_headline.strip()
            else:
                if current_headline.endswith("."):
                    new_headline = current_headline[:-1].rstrip()
                else:
                    new_headline = f"{current_headline}."

            result["new_headline"] = new_headline
            logger.info("Current headline: '{}' | New headline: '{}'", current_headline, new_headline)

            # Step 4: Update Headline via Naukri Profile APIs
            update_targets = [
                {
                    "url": "https://www.naukri.com/gateway/v1/profiles/userProfile/resume-headline",
                    "method": "POST",
                    "json": {"resumeHeadline": new_headline}
                },
                {
                    "url": "https://www.naukri.com/gateway/v1/profiles/userProfile/resume-headline",
                    "method": "PUT",
                    "json": {"resumeHeadline": new_headline}
                },
                {
                    "url": "https://www.naukri.com/gateway/v1/profiles/userProfile",
                    "method": "POST",
                    "json": {"resumeHeadline": new_headline}
                },
                {
                    "url": "https://www.naukri.com/mnjuser/profile",
                    "method": "POST",
                    "data": {"resumeHeadline": new_headline}
                }
            ]

            update_success = False
            last_err = ""

            for target in update_targets:
                try:
                    up_headers = dict(headers)
                    if "json" in target:
                        up_headers["Content-Type"] = "application/json"
                        if target["method"] == "POST":
                            r = await client.post(target["url"], json=target["json"], headers=up_headers, timeout=20.0)
                        else:
                            r = await client.put(target["url"], json=target["json"], headers=up_headers, timeout=20.0)
                    else:
                        up_headers["Content-Type"] = "application/x-www-form-urlencoded"
                        r = await client.post(target["url"], data=target["data"], headers=up_headers, timeout=20.0)

                    logger.info("Update headline on {} returned HTTP {}", target["url"], r.status_code)
                    if r.status_code in (200, 201, 204):
                        update_success = True
                        break
                    else:
                        last_err = f"HTTP {r.status_code}: {r.text[:100]}"
                except Exception as e:
                    last_err = str(e)
                    continue

            saved_cookies = self._extract_cookies_safely(client)
            self._save_session(saved_cookies, self.auth_token)

            if update_success:
                result["success"] = True
                result["message"] = f"Headline successfully updated from:\n`{current_headline}`\nto:\n`{new_headline}`"
            else:
                result["success"] = False
                result["message"] = f"Naukri rejected the update request ({last_err or 'Session expired'})."

        return result