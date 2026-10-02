"""Naukri API client — lightweight, no browser (good for basic CLI servers).

Uses curl-cffi with Chrome TLS impersonation to bypass Akamai fingerprinting,
so plain email+password login works without Playwright/Selenium.

Endpoints (verified working pattern, incl. NopeRi July-2026):
  LOGIN:    POST https://www.naukri.com/central-login-services/v1/login
            headers: appid=105, clientid=d3skt0p, systemid=jobseeker
            json: {"username": email, "password": password}
            token: cookie "nauk_at" (Bearer)
  DASHBOARD: GET https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/dashboard
  UPDATE:   POST https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/fullprofiles
            headers: Authorization Bearer, systemid=Naukri, x-http-method-override=PUT
            json: {"profile": {"resumeHeadline": ...}, "profileId": ...}
"""
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any

from src.config import Config, logger

LOGIN_URL = "https://www.naukri.com/central-login-services/v1/login"
DASHBOARD_URL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/dashboard"
PROFILE_UPDATE_URL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/fullprofiles"

LOGIN_HEADERS = {
    "accept": "application/json",
    "appid": "105",
    "clientid": "d3skt0p",
    "content-type": "application/json",
    "referer": "https://www.naukri.com/nlogin/login",
    "systemid": "jobseeker",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _make_session():
    """Chrome-impersonating sync session (bypasses Akamai TLS fingerprint)."""
    from curl_cffi import requests as crequests
    return crequests.Session(impersonate="chrome124", timeout=30)


class NaukriClient:
    def __init__(self):
        self.session_file = Config.SESSION_FILE_PATH
        self.auth_token: Optional[str] = None

    # ---------- session persistence ----------
    def _parse_cookie_string(self, cookie_str: str) -> dict:
        cookies = {}
        if not cookie_str:
            return cookies
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def _load_saved_session(self) -> tuple[dict, Optional[str]]:
        if Config.NAUKRI_COOKIES:
            env_cookies = self._parse_cookie_string(Config.NAUKRI_COOKIES)
            if env_cookies:
                token = env_cookies.get("nauk_at")
                return env_cookies, token
        if self.session_file.exists():
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        cookies = data.get("cookies", data)
                        token = data.get("token")
                        if isinstance(cookies, dict):
                            if not token:
                                token = cookies.get("nauk_at")
                            return cookies, token
            except Exception as e:
                logger.warning("Failed to load saved session: {}", e)
        return {}, None

    def save_raw_cookie_string(self, raw_cookie_str: str) -> bool:
        cookies = self._parse_cookie_string(raw_cookie_str)
        if not cookies:
            return False
        token = cookies.get("nauk_at")
        if token:
            self.auth_token = token
        self._save_session(cookies, self.auth_token)
        return True

    def _save_session(self, cookies: dict, token: Optional[str] = None):
        try:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"cookies": cookies, "token": token or self.auth_token}
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info("Saved session ({} cookies) to {}", len(cookies), self.session_file)
        except Exception as e:
            logger.warning("Could not save session: {}", e)

    def _auth_headers(self) -> dict:
        h = dict(LOGIN_HEADERS)
        if self.auth_token:
            h["authorization"] = f"Bearer {self.auth_token}"
            h["systemid"] = "Naukri"
        return h

    # ---------- blocking I/O (run in thread) ----------
    def _do_login_blocking(self) -> tuple[dict, str]:
        """POST login, return (cookies, nauk_at). Raises on failure."""
        if not Config.NAUKRI_EMAIL or not Config.NAUKRI_PASSWORD:
            raise Exception("NAUKRI_EMAIL / NAUKRI_PASSWORD not set in .env.")
        s = _make_session()
        resp = s.post(
            LOGIN_URL,
            headers=LOGIN_HEADERS,
            json={"username": Config.NAUKRI_EMAIL, "password": Config.NAUKRI_PASSWORD},
        )
        logger.info("Login API returned HTTP {}", resp.status_code)
        if resp.status_code == 401:
            raise Exception("Invalid email/password (401).")
        if resp.status_code in (400, 403, 429):
            body = (resp.text or "")[:200]
            raise Exception(f"Login rejected (HTTP {resp.status_code}). Blocked IP/captcha? {body}")
        if not resp.ok:
            raise Exception(f"Login failed HTTP {resp.status_code}: {(resp.text or '')[:200]}")
        cookies = {c.name: c.value for c in s.cookies.jar} if hasattr(s.cookies, "jar") else dict(s.cookies)
        # curl_cffi cookies may expose via .get
        token = s.cookies.get("nauk_at") if hasattr(s.cookies, "get") else cookies.get("nauk_at")
        if not token:
            token = cookies.get("nauk_at")
        if not token:
            # Some flows put token in JSON
            try:
                token = resp.json().get("token") or resp.json().get("authToken")
            except Exception:
                pass
        if not token:
            raise Exception("Login OK but no nauk_at token — MFA/captcha may be required. Try login from this IP in browser once.")
        return cookies, token

    def _newauthed_session(self, cookies: dict):
        s = _make_session()
        for k, v in cookies.items():
            try:
                s.cookies.set(k, v, domain=".naukri.com")
            except Exception:
                try:
                    s.cookies.set(k, v)
                except Exception:
                    pass
        return s

    # ---------- headline state (Naukri offers no lightweight headline READ api;
    # profile HTML is a JS shell, so we track the dot-toggle locally) ----------
    def get_headline_state(self) -> dict:
        """Return {'base': str, 'last_dot': bool}. Base seeded from BASE_HEADLINE env or /set_headline."""
        state = {"base": "", "last_dot": False}
        p = Config.HEADLINE_STATE_PATH
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        if saved.get("base"):
                            state["base"] = str(saved["base"]).strip()
                        state["last_dot"] = bool(saved.get("last_dot", False))
            except Exception as e:
                logger.warning("Could not read headline state: {}", e)
        if not state["base"] and Config.BASE_HEADLINE:
            state["base"] = Config.BASE_HEADLINE.strip().rstrip(".").strip()
        return state

    def set_base_headline(self, headline: str) -> str:
        """Seed/overwrite tracked base headline. Returns normalized base."""
        base = (headline or "").strip().rstrip(".").strip()
        if not base:
            raise ValueError("Headline is empty.")
        try:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(Config.HEADLINE_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"base": base, "last_dot": False}, f, indent=2)
        except Exception as e:
            logger.warning("Could not save headline state: {}", e)
        logger.info("Base headline set to: '{}'", base)
        return base

    def _save_headline_state(self, base: str, last_dot: bool):
        try:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(Config.HEADLINE_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"base": base, "last_dot": last_dot}, f, indent=2)
        except Exception as e:
            logger.warning("Could not save headline state: {}", e)

    def _do_get_mod_dt_blocking(self, cookies: dict, token: Optional[str]) -> Optional[str]:
        """Dashboard mod_dt = profile last-modified timestamp. Used to verify updates."""
        try:
            s = self._newauthed_session(cookies)
            headers = dict(LOGIN_HEADERS)
            if token:
                headers["authorization"] = f"Bearer {token}"
                headers["systemid"] = "Naukri"
            r = s.get(DASHBOARD_URL, headers=headers)
            if r.status_code == 401:
                return "EXPIRED"
            if r.ok:
                d = r.json()
                return d.get("dashBoard", {}).get("mod_dt")
        except Exception as e:
            logger.debug("mod_dt fetch failed: {}", e)
        return None

    def _do_update_headline_blocking(self, cookies: dict, token: Optional[str], new_headline: str) -> Dict[str, Any]:
        s = self._newauthed_session(cookies)
        headers = dict(LOGIN_HEADERS)
        if token:
            headers["authorization"] = f"Bearer {token}"
        headers.update({
            "origin": "https://www.naukri.com",
            "referer": "https://www.naukri.com/mnjuser/profile?id=&altresid",
            "systemid": "105",
            "x-http-method-override": "PUT",
            "x-requested-with": "XMLHttpRequest",
        })

        # Need profileId
        pid = None
        try:
            r = s.get(DASHBOARD_URL, headers=headers)
            if r.status_code == 401:
                return {"success": False, "message": "Session expired (401). Will re-login."}
            if r.ok:
                d = r.json()
                pid = d.get("profileId") or d.get("dashBoard", {}).get("profileId")
        except Exception as e:
            logger.debug("Dashboard for profileId failed: {}", e)
        if not pid:
            return {"success": False, "message": "Could not get profileId from dashboard."}

        headers["systemid"] = "105"
        payload = {"profile": {"resumeHeadline": new_headline}, "profileId": pid}
        r = s.post(PROFILE_UPDATE_URL, headers=headers, json=payload)
        logger.info("Profile update returned HTTP {}", r.status_code)
        if r.ok:
            try:
                body = r.json()
                if body.get("status") is False or body.get("success") is False:
                    return {"success": False, "message": f"Naukri rejected update: {str(body)[:200]}"}
            except Exception:
                pass
            fresh_cookies = {c.name: c.value for c in s.cookies.jar} if hasattr(s.cookies, "jar") else dict(s.cookies)
            return {"success": True, "message": "Updated.", "cookies": fresh_cookies}
        if r.status_code == 401:
            return {"success": False, "message": "Session expired (401). Will re-login."}
        return {"success": False, "message": f"Update failed HTTP {r.status_code}: {(r.text or '')[:200]}"}

    # ---------- async public API (same signatures as before) ----------
    async def _ensure_login(self, cookies: dict, token: Optional[str]) -> tuple[dict, str]:
        if token and cookies.get("nauk_at"):
            self.auth_token = token
            return cookies, token
        logger.info("No valid session, logging in with email+password...")
        new_cookies, new_token = await asyncio.to_thread(self._do_login_blocking)
        self.auth_token = new_token
        self._save_session(new_cookies, new_token)
        return new_cookies, new_token

    async def get_current_headline(self) -> Dict[str, Any]:
        """Return tracked headline + live profile freshness (mod_dt from dashboard).

        Note: Naukri's profile HTML is a JS shell and offers no lightweight
        headline-read API, so the headline text itself is tracked locally
        (seeded once via BASE_HEADLINE / /set_headline). Login + mod_dt prove
        the session is live.
        """
        result: Dict[str, Any] = {"success": False, "headline": "", "message": ""}
        cookies, token = self._load_saved_session()
        if token:
            self.auth_token = token
        try:
            cookies, token = await self._ensure_login(cookies, token)
            state = self.get_headline_state()
            mod_dt = await asyncio.to_thread(self._do_get_mod_dt_blocking, cookies, token)
            if mod_dt == "EXPIRED":
                cookies, token = await self._ensure_login({}, None)
                mod_dt = await asyncio.to_thread(self._do_get_mod_dt_blocking, cookies, token)
            if not state["base"]:
                result["message"] = (
                    "Login works, but base headline is not set yet. "
                    "Copy your headline from naukri.com/mnjuser/profile and run: "
                    "/set_headline <your headline> (or set BASE_HEADLINE in .env)."
                )
                return result
            current = state["base"] + ("." if state["last_dot"] else "")
            result["success"] = True
            result["headline"] = current
            result["message"] = f"Tracked headline. Profile last modified: {mod_dt or 'unknown'}."
            return result
        except Exception as e:
            result["message"] = str(e)
            logger.error("get_current_headline failed: {}", e)
            return result

    async def update_profile_headline(self, custom_headline: Optional[str] = None) -> Dict[str, Any]:
        """Toggle trailing dot using locally tracked state, verify via mod_dt bump."""
        result: Dict[str, Any] = {"success": False, "old_headline": "", "new_headline": "", "message": ""}
        cookies, token = self._load_saved_session()
        if token:
            self.auth_token = token
        try:
            # 1) Ensure logged in
            cookies, token = await self._ensure_login(cookies, token)

            # 2) Determine old -> new from tracked state (never guess/overwrite blindly)
            state = self.get_headline_state()
            if custom_headline:
                base = custom_headline.strip().rstrip(".").strip()
                if not base:
                    result["message"] = "Custom headline is empty."
                    return result
                old_headline = state["base"] + ("." if state.get("last_dot") else "") if state["base"] else base
                new_headline = custom_headline.strip()
                new_last_dot = new_headline.endswith(".")
                base = new_headline.rstrip(".").strip()
            else:
                base = state["base"]
                if not base:
                    result["message"] = (
                        "Base headline is not set — refusing to overwrite your profile with a guess. "
                        "Copy your headline from naukri.com/mnjuser/profile and run: "
                        "/set_headline <your headline> (or set BASE_HEADLINE in .env), then retry."
                    )
                    return result
                old_headline = base + ("." if state["last_dot"] else "")
                new_last_dot = not state["last_dot"]
                new_headline = base + ("." if new_last_dot else "")
            result["old_headline"] = old_headline
            result["new_headline"] = new_headline
            logger.info("Headline: '{}' -> '{}'", old_headline, new_headline)

            # 3) Snapshot mod_dt before
            mod_before = await asyncio.to_thread(self._do_get_mod_dt_blocking, cookies, token)

            # 4) Update (retry once with fresh login on expiry)
            upd = await asyncio.to_thread(self._do_update_headline_blocking, cookies, token, new_headline)
            if not upd.get("success") and "expired" in upd.get("message", "").lower():
                cookies, token = await self._ensure_login({}, None)
                mod_before = await asyncio.to_thread(self._do_get_mod_dt_blocking, cookies, token)
                upd = await asyncio.to_thread(self._do_update_headline_blocking, cookies, token, new_headline)
            if not upd.get("success"):
                result["message"] = upd.get("message", "Update failed.")
                return result
            if upd.get("cookies"):
                self._save_session(upd["cookies"], token)
            else:
                self._save_session(cookies, token)

            # 5) Verify: mod_dt should bump to now
            await asyncio.sleep(2)
            mod_after = await asyncio.to_thread(
                self._do_get_mod_dt_blocking, upd.get("cookies", cookies), token
            )
            self._save_headline_state(base, new_last_dot)
            result["success"] = True
            if mod_after and mod_after != mod_before:
                result["message"] = (
                    f"Headline updated:\n`{old_headline}`\nto:\n`{new_headline}`\n"
                    f"Verified: profile modified {mod_before} -> {mod_after}."
                )
            else:
                result["message"] = (
                    f"Headline update accepted (HTTP 200):\n`{old_headline}`\nto:\n`{new_headline}`."
                    + ("" if mod_after else " Could not re-read mod_dt for verification.")
                )
            return result
        except Exception as e:
            result["message"] = str(e)
            logger.error("update_profile_headline failed: {}", e)
            return result
