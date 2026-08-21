import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from src.config import Config, logger

class NaukriClient:
    def __init__(self):
        self.session_file = Config.SESSION_FILE_PATH
        self.screenshot_dir = Config.SCREENSHOT_DIR
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _init_browser_context(self, p) -> tuple[Browser, BrowserContext]:
        """Launch browser with realistic user-agent and options."""
        browser = await p.chromium.launch(
            headless=Config.HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu"
            ]
        )

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        # Check if saved storage state exists and is valid
        if self.session_file.exists() and self.session_file.stat().st_size > 0:
            try:
                context = await browser.new_context(
                    storage_state=str(self.session_file),
                    user_agent=user_agent,
                    viewport={"width": 1366, "height": 768}
                )
                logger.info("Loaded existing session state from {}", self.session_file)
                return browser, context
            except Exception as e:
                logger.warning("Failed to load session state: {}. Creating fresh context.", e)

        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768}
        )
        return browser, context

    async def _is_logged_in(self, page: Page) -> bool:
        """Check if current page indicates an authenticated user session."""
        try:
            current_url = page.url
            if "mnjuser/profile" in current_url or "naukri.com/mnjuser/homepage" in current_url:
                return True
            
            # Check for profile navigation or avatar element
            logged_in_el = await page.query_selector(".nI-gNb-drawer, .user-name, a[href*='profile'], .nI-gNb-header__user")
            return logged_in_el is not None
        except Exception:
            return False

    async def _login(self, page: Page) -> bool:
        """Log into Naukri using credentials."""
        logger.info("Navigating to Naukri login page...")
        await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)

        if await self._is_logged_in(page):
            logger.info("Already logged in.")
            return True

        # Enter Email / Username
        logger.info("Entering credentials...")
        username_input = await page.wait_for_selector(
            "input#usernameField, input[placeholder*='Email'], input[placeholder*='Username']",
            timeout=15000
        )
        if not username_input:
            raise Exception("Username input field not found on login page.")
        await username_input.fill("")
        await username_input.type(Config.NAUKRI_EMAIL, delay=40)

        # Enter Password
        password_input = await page.wait_for_selector(
            "input#passwordField, input[type='password']",
            timeout=10000
        )
        if not password_input:
            raise Exception("Password input field not found on login page.")
        await password_input.fill("")
        await password_input.type(Config.NAUKRI_PASSWORD, delay=40)

        # Click Login button
        login_btn = await page.wait_for_selector(
            "button[type='submit']:has-text('Login'), button.btn-primary:has-text('Login'), button:has-text('Login')",
            timeout=10000
        )
        await login_btn.click()
        logger.info("Submitted login credentials. Waiting for authentication...")

        # Wait for redirection or profile page
        try:
            await page.wait_for_url(lambda url: "mnjuser" in url or "nlogin" not in url, timeout=25000)
            await asyncio.sleep(3)
        except Exception:
            pass

        # Check login success
        if "nlogin" in page.url:
            # Check for error message
            err_el = await page.query_selector(".server-err, .error, .err")
            err_msg = await err_el.inner_text() if err_el else "Unknown login failure (Captcha or wrong credentials)"
            logger.error("Login failed: {}", err_msg)
            screenshot_err = self.screenshot_dir / "login_error.png"
            await page.screenshot(path=str(screenshot_err))
            raise Exception(f"Login failed: {err_msg}")

        logger.info("Login successful. URL: {}", page.url)
        return True

    async def update_profile_headline(self, custom_headline: Optional[str] = None) -> Dict[str, Any]:
        """
        Navigates to Naukri profile, reads the current headline,
        toggles a dot '.' (or uses custom headline), saves it, and verifies.
        """
        result = {
            "success": False,
            "old_headline": "",
            "new_headline": "",
            "screenshot_path": "",
            "message": ""
        }

        async with async_playwright() as p:
            browser, context = await self._init_browser_context(p)
            page = await context.new_page()

            try:
                # Step 1: Navigate to Profile page
                logger.info("Navigating to Naukri Profile page...")
                await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)

                # Check if redirected to login
                if "nlogin" in page.url or "login" in page.url:
                    logger.info("Session expired or not authenticated. Performing login...")
                    await self._login(page)
                    await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(3)

                # Save new session state
                try:
                    await context.storage_state(path=str(self.session_file))
                    logger.info("Session storage state saved to {}", self.session_file)
                except Exception as e:
                    logger.warning("Could not save session storage state: {}", e)

                # Step 2: Locate Headline section
                logger.info("Locating Resume Headline section...")
                headline_edit_btn = None
                selectors = [
                    "//div[contains(@class, 'resumeHeadline')]//span[contains(@class, 'edit') or contains(text(), 'edit')]",
                    "//span[contains(text(), 'Resume headline') or contains(text(), 'Resume Headline')]/following::span[contains(@class, 'edit')][1]",
                    "div.resumeHeadline span.edit",
                    "div.widgetHead > span.edit",
                    ".resumeHeadline .edit.icon",
                    "//div[contains(@class, 'widgetHead')]//span[contains(@class, 'edit')]"
                ]

                for sel in selectors:
                    try:
                        if sel.startswith("//"):
                            el = await page.wait_for_selector(f"xpath={sel}", timeout=4000)
                        else:
                            el = await page.wait_for_selector(sel, timeout=4000)
                        if el and await el.is_visible():
                            headline_edit_btn = el
                            break
                    except Exception:
                        continue

                if not headline_edit_btn:
                    # Fallback: click directly on the headline text or container
                    headline_container = await page.query_selector(".resumeHeadline, .widgetHead")
                    if headline_container:
                        await headline_container.click()
                    else:
                        raise Exception("Resume headline edit button could not be located on profile page.")
                else:
                    await headline_edit_btn.click()

                await asyncio.sleep(1.5)

                # Step 3: Locate Textarea for Headline
                textarea_selectors = [
                    "textarea#resumeHeadlineTxt",
                    "textarea.resumeHeadlineTxt",
                    "div.resumeHeadlineTxt textarea",
                    "textarea[placeholder*='headline']",
                    "div.modal-content textarea",
                    "textarea"
                ]

                headline_textarea = None
                for t_sel in textarea_selectors:
                    try:
                        el = await page.wait_for_selector(t_sel, timeout=4000)
                        if el and await el.is_visible():
                            headline_textarea = el
                            break
                    except Exception:
                        continue

                if not headline_textarea:
                    raise Exception("Headline textarea input not found after clicking edit.")

                # Read current headline
                current_text = await headline_textarea.input_value()
                current_text = current_text.strip() if current_text else ""
                result["old_headline"] = current_text

                # Compute new headline
                if custom_headline:
                    new_text = custom_headline.strip()
                else:
                    # Toggle dot at the end
                    if current_text.endswith("."):
                        new_text = current_text[:-1].rstrip()
                    else:
                        new_text = f"{current_text}."

                result["new_headline"] = new_text
                logger.info("Current headline: '{}'", current_text)
                logger.info("Updating headline to: '{}'", new_text)

                # Step 4: Fill new headline
                await headline_textarea.fill("")
                await headline_textarea.fill(new_text)
                await asyncio.sleep(1)

                # Step 5: Click Save Button
                save_btn_selectors = [
                    "//div[contains(@class, 'action')]//button[contains(text(), 'Save')]",
                    "//button[contains(@class, 'btn-dark-ot') and contains(text(), 'Save')]",
                    "//button[@type='submit' and (contains(text(), 'Save') or contains(text(), 'SAVE'))]",
                    "button.saveBtn",
                    "form.resumeHeadlineForm button[type='submit']",
                    "//button[contains(text(), 'Save')]"
                ]

                save_btn = None
                for s_sel in save_btn_selectors:
                    try:
                        if s_sel.startswith("//"):
                            el = await page.wait_for_selector(f"xpath={s_sel}", timeout=3000)
                        else:
                            el = await page.wait_for_selector(s_sel, timeout=3000)
                        if el and await el.is_visible():
                            save_btn = el
                            break
                    except Exception:
                        continue

                if not save_btn:
                    raise Exception("Save button for headline could not be found.")

                await save_btn.click()
                logger.info("Save button clicked. Waiting for update confirmation...")
                await asyncio.sleep(3)

                # Step 6: Take verification screenshot
                screenshot_filename = self.screenshot_dir / "latest_update.png"
                await page.screenshot(path=str(screenshot_filename), full_page=False)
                result["screenshot_path"] = str(screenshot_filename)
                result["success"] = True
                result["message"] = f"Headline successfully updated from:\n{current_text}\nto:\n{new_text}"
                logger.info("Profile headline updated successfully!")

            except Exception as e:
                logger.error("Error during Naukri profile update: {}", e)
                err_screenshot = self.screenshot_dir / "latest_error.png"
                try:
                    await page.screenshot(path=str(err_screenshot))
                    result["screenshot_path"] = str(err_screenshot)
                except Exception:
                    pass
                result["success"] = False
                result["message"] = f"Profile update failed: {str(e)}"
            finally:
                await context.close()
                await browser.close()

        return result

    async def get_current_headline(self) -> Dict[str, Any]:
        """Fetch current headline from profile."""
        result = {"success": False, "headline": "", "message": ""}
        async with async_playwright() as p:
            browser, context = await self._init_browser_context(p)
            page = await context.new_page()
            try:
                await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2)
                if "nlogin" in page.url or "login" in page.url:
                    await self._login(page)
                    await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(2)

                # Save session
                try:
                    await context.storage_state(path=str(self.session_file))
                except Exception:
                    pass

                # Read headline text from preview element
                headline_el = await page.query_selector(".resumeHeadline .msg, .resumeHeadline .widgetCont, div.resumeHeadlineTxt")
                if headline_el:
                    text = await headline_el.inner_text()
                    result["headline"] = text.strip()
                    result["success"] = True
                    result["message"] = "Fetched successfully."
                else:
                    result["message"] = "Could not locate headline container."
            except Exception as e:
                result["message"] = str(e)
            finally:
                await context.close()
                await browser.close()
        return result
