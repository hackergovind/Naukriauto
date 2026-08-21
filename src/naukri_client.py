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

    def _load_saved_cookies(self) -> dict:
        """Load saved cookies from session.json if present."""
        if self.session_file.exists():
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    if isinstance(cookies, dict):
                        return cookies
            except Exception as e:
                logger.warning("Failed to load saved session cookies: {}", e)
        return {}

    def _save_cookies(self, cookies: dict):
        """Save session cookies to session.json."""
        try:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            logger.info("Saved updated session cookies to {}", self.session_file)
        except Exception as e:
            logger.warning("Could not save session cookies: {}", e)

    async def _login(self, client: httpx.AsyncClient) -> bool:
        """Perform login to Naukri using credentials."""
        logger.info("Initiating login for {}", Config.NAUKRI_EMAIL)
        
        # Step 1: Initial GET to acquire base cookies / csrf
        try:
            r_init = await client.get(
                "https://www.naukri.com/nlogin/login",
                headers=self.base_headers,
                timeout=20.0
            )
        except Exception as e:
            logger.warning("Initial login page fetch notice: {}", e)

        # Step 2: Submit login credentials
        login_endpoints = [
            "https://www.naukri.com/gateway/v1/auth/login",
            "https://auth.naukri.com/v1/login",
            "https://www.naukri.com/nlogin/login"
        ]

        payload = {
            "username": Config.NAUKRI_EMAIL,
            "password": Config.NAUKRI_PASSWORD
        }

        login_success = False
        last_error = ""

        for endpoint in login_endpoints:
            try:
                logger.info("Attempting authentication via endpoint: {}", endpoint)
                login_headers = dict(self.base_headers)
                login_headers["Content-Type"] = "application/json"

                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers=login_headers,
                    timeout=25.0
                )

                if resp.status_code in (200, 201):
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    if data.get("status") == "success" or "user" in data or "token" in data or "userId" in data or resp.cookies:
                        login_success = True
                        logger.info("Login succeeded via {}", endpoint)
                        break
                elif resp.status_code in (301, 302, 303):
                    login_success = True
                    logger.info("Login succeeded with redirect")
                    break
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:150]}"
            except Exception as ex:
                last_error = str(ex)
                continue

        if not login_success:
            # Try form-urlencoded fallback
            try:
                logger.info("Attempting form-urlencoded login fallback...")
                form_headers = dict(self.base_headers)
                form_headers["Content-Type"] = "application/x-www-form-urlencoded"
                resp = await client.post(
                    "https://www.naukri.com/nlogin/login",
                    data=payload,
                    headers=form_headers,
                    timeout=25.0
                )
                if resp.status_code in (200, 302):
                    login_success = True
            except Exception as e:
                last_error = str(e)

        if not login_success:
            raise Exception(f"Naukri Login Failed. Please verify NAUKRI_EMAIL and NAUKRI_PASSWORD. Details: {last_error}")

        # Save cookies
        current_cookies = dict(client.cookies)
        self._save_cookies(current_cookies)
        return True

    async def get_current_headline(self) -> Dict[str, Any]:
        """Fetch current resume headline from Naukri."""
        result = {"success": False, "headline": "", "message": ""}
        saved_cookies = self._load_saved_cookies()

        async with httpx.AsyncClient(cookies=saved_cookies, follow_redirects=True) as client:
            # Step 1: Try gateway API endpoint
            try:
                resp = await client.get(
                    "https://www.naukri.com/gateway/v1/profiles/userProfile",
                    headers=self.base_headers,
                    timeout=20.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    headline = (
                        data.get("profile", {}).get("resumeHeadline") or
                        data.get("resumeHeadline") or
                        data.get("data", {}).get("resumeHeadline") or ""
                    )
                    if headline:
                        result["headline"] = headline.strip()
                        result["success"] = True
                        result["message"] = "Fetched successfully."
                        return result
            except Exception:
                pass

            # Step 2: Fallback to profile HTML page
            try:
                resp = await client.get(
                    "https://www.naukri.com/mnjuser/profile",
                    headers=self.base_headers,
                    timeout=25.0
                )
                if "nlogin" in str(resp.url):
                    # Need login
                    await self._login(client)
                    resp = await client.get("https://www.naukri.com/mnjuser/profile", headers=self.base_headers, timeout=25.0)

                soup = BeautifulSoup(resp.text, "html.parser")
                headline_el = soup.select_one(".resumeHeadline .msg, .resumeHeadline .widgetCont, div.resumeHeadlineTxt, textarea#resumeHeadlineTxt")
                if headline_el:
                    text = headline_el.get_text(strip=True) or headline_el.get("value", "")
                    result["headline"] = text.strip()
                    result["success"] = True
                    result["message"] = "Fetched successfully."
                    return result
            except Exception as e:
                result["message"] = str(e)

        return result

    async def update_profile_headline(self, custom_headline: Optional[str] = None) -> Dict[str, Any]:
        """
        Updates Naukri profile headline by toggling a dot (or setting custom headline).
        Uses ultra-lightweight REST API requests (< 10MB memory/disk).
        """
        result = {
            "success": False,
            "old_headline": "",
            "new_headline": "",
            "screenshot_path": None,
            "message": ""
        }

        saved_cookies = self._load_saved_cookies()

        async with httpx.AsyncClient(cookies=saved_cookies, follow_redirects=True) as client:
            # Step 1: Ensure session is authenticated
            logger.info("Checking authentication state...")
            check_resp = await client.get(
                "https://www.naukri.com/gateway/v1/profiles/userProfile",
                headers=self.base_headers,
                timeout=20.0
            )

            if check_resp.status_code in (401, 403) or "nlogin" in str(check_resp.url):
                logger.info("Session not authenticated or expired. Logging in...")
                await self._login(client)
                check_resp = await client.get(
                    "https://www.naukri.com/gateway/v1/profiles/userProfile",
                    headers=self.base_headers,
                    timeout=20.0
                )

            # Step 2: Get current headline
            current_headline = ""
            if check_resp.status_code == 200:
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
                # Fetch from profile HTML page
                profile_page = await client.get("https://www.naukri.com/mnjuser/profile", headers=self.base_headers, timeout=25.0)
                soup = BeautifulSoup(profile_page.text, "html.parser")
                el = soup.select_one(".resumeHeadline .msg, .resumeHeadline .widgetCont, div.resumeHeadlineTxt, textarea#resumeHeadlineTxt")
                if el:
                    current_headline = el.get_text(strip=True) or el.get("value", "")

            current_headline = current_headline.strip() if current_headline else "Experienced Software Professional"
            result["old_headline"] = current_headline

            # Step 3: Compute new headline (Smart Dot Toggle)
            if custom_headline:
                new_headline = custom_headline.strip()
            else:
                if current_headline.endswith("."):
                    new_headline = current_headline[:-1].rstrip()
                else:
                    new_headline = f"{current_headline}."

            result["new_headline"] = new_headline
            logger.info("Old Headline: '{}'", current_headline)
            logger.info("New Headline: '{}'", new_headline)

            # Step 4: Submit updated headline to Naukri API
            update_endpoints = [
                "https://www.naukri.com/gateway/v1/profiles/userProfile/resume-headline",
                "https://www.naukri.com/gateway/v1/profiles/userProfile"
            ]

            payload = {
                "resumeHeadline": new_headline
            }

            update_success = False
            for endpoint in update_endpoints:
                try:
                    logger.info("Sending update request to {}", endpoint)
                    up_headers = dict(self.base_headers)
                    up_headers["Content-Type"] = "application/json"

                    r = await client.post(
                        endpoint,
                        json=payload,
                        headers=up_headers,
                        timeout=25.0
                    )

                    if r.status_code in (200, 201, 204):
                        update_success = True
                        logger.info("Profile headline updated successfully via API!")
                        break
                    else:
                        # Try PUT request
                        r_put = await client.put(
                            endpoint,
                            json=payload,
                            headers=up_headers,
                            timeout=25.0
                        )
                        if r_put.status_code in (200, 201, 204):
                            update_success = True
                            logger.info("Profile headline updated successfully via PUT API!")
                            break
                except Exception as e:
                    logger.warning("Endpoint {} failed: {}", endpoint, e)
                    continue

            # Save session cookies
            self._save_cookies(dict(client.cookies))

            if update_success:
                result["success"] = True
                result["message"] = f"Headline successfully updated from:\n`{current_headline}`\nto:\n`{new_headline}`"
            else:
                result["success"] = False
                result["message"] = "Naukri rejected the update request. Please verify login credentials."

        return result