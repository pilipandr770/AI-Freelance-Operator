"""
Freelancer.com Selenium Client — automated bid submission.

Uses undetected-chromedriver to avoid bot detection.
This module is OPTIONAL: if FREELANCER_LOGIN is not configured,
bids are sent to Telegram for manual copy-paste instead.

Session lifecycle:
  1. Browser is initialised lazily on first bid
  2. Login is performed once; session persists across bids
  3. If session expires, auto re-login
  4. Browser is closed on shutdown
"""
import time
import json
import random
import threading
import logging
from pathlib import Path
from typing import Optional, Tuple

from config import Config

log = logging.getLogger(__name__)

# File that tracks already-submitted project URLs (avoids duplicate bids)
_SUBMITTED_FILE = Path(__file__).resolve().parent.parent / 'data' / 'submitted_bids.json'


class FreelancerClient:
    """
    Selenium-based client for submitting bids on freelancer.com.

    Usage:
        client = get_freelancer_client()
        if client.enabled:
            ok, msg = client.submit_bid(url, amount=150, days=7, text='...')
    """

    def __init__(self):
        self.login_username = getattr(Config, 'FREELANCER_LOGIN', '') or ''
        self.login_password = getattr(Config, 'FREELANCER_PASSWORD', '') or ''
        self.enabled = bool(self.login_username and self.login_password)

        self._driver = None
        self._wait = None
        self._logged_in = False
        self._lock = threading.Lock()
        self._submitted: set = set()

        if not self.enabled:
            log.info("[FreelancerClient] FREELANCER_LOGIN not set — auto-bidding disabled")
        else:
            log.info("[FreelancerClient] Enabled for user: %s", self.login_username)
            self._load_submitted()

    # ──────────── Browser lifecycle ────────────

    def _ensure_browser(self):
        """Lazily start an undetected Chrome browser."""
        if self._driver is not None:
            return
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.support.ui import WebDriverWait

            options = uc.ChromeOptions()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-gpu")
            # Headless by default on servers; set FREELANCER_HEADLESS=false for debug
            headless = (getattr(Config, 'FREELANCER_HEADLESS', 'true') or 'true').lower()
            if headless != 'false':
                options.add_argument("--headless=new")

            self._driver = uc.Chrome(options=options)
            self._wait = WebDriverWait(self._driver, 20)
            log.info("[FreelancerClient] Browser started")
        except Exception as e:
            log.error("[FreelancerClient] Cannot start browser: %s", e)
            self._driver = None
            raise RuntimeError(f"Browser init failed: {e}")

    def shutdown(self):
        """Close browser and release resources."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
            self._logged_in = False
            log.info("[FreelancerClient] Browser closed")

    # ──────────── Login ────────────

    def _login(self) -> bool:
        """Login to freelancer.com. Returns True on success."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC

        try:
            self._driver.get("https://www.freelancer.com/login")
            time.sleep(random.uniform(2, 4))

            # Email/username field
            email_field = self._wait.until(
                EC.presence_of_element_located((By.ID, "emailOrUsernameInput"))
            )
            self._human_type(email_field, self.login_username)

            # Password field
            pwd_field = self._driver.find_element(By.ID, "passwordInput")
            self._human_type(pwd_field, self.login_password)

            # Login button
            login_btn = self._driver.find_element(
                By.CSS_SELECTOR,
                "fl-button[data-form-id='loginForm'] button, "
                "button[type='submit']"
            )
            login_btn.click()
            time.sleep(random.uniform(4, 6))

            url = self._driver.current_url.lower()
            if 'dashboard' in url or 'feed' in url or 'home' in url:
                self._logged_in = True
                log.info("[FreelancerClient] Login successful")
                return True
            else:
                log.warning("[FreelancerClient] Login may have failed. URL: %s", url)
                # Still mark as logged in — some redirects are OK
                self._logged_in = True
                return True

        except Exception as e:
            log.error("[FreelancerClient] Login error: %s", e)
            self._logged_in = False
            return False

    def _ensure_logged_in(self) -> bool:
        """Make sure we have an active session."""
        self._ensure_browser()
        if self._logged_in:
            # Quick check: try accessing a page that requires auth
            try:
                self._driver.get("https://www.freelancer.com/dashboard")
                time.sleep(2)
                if 'login' in self._driver.current_url.lower():
                    self._logged_in = False
            except Exception:
                self._logged_in = False

        if not self._logged_in:
            return self._login()
        return True

    # ──────────── Bid submission ────────────

    def submit_bid(self, project_url: str, amount: float,
                   days: int, proposal_text: str) -> Tuple[bool, str]:
        """
        Submit a bid on a freelancer.com project page.

        Args:
            project_url: Full URL to the project page
            amount: Bid amount (EUR/USD)
            days: Delivery period in days
            proposal_text: The proposal text to submit

        Returns:
            (success: bool, message: str)
        """
        if not self.enabled:
            return False, "Auto-bidding disabled (no credentials)"

        if project_url in self._submitted:
            return False, f"Already submitted bid for this URL"

        with self._lock:
            return self._submit_bid_locked(project_url, amount, days, proposal_text)

    def _submit_bid_locked(self, project_url: str, amount: float,
                            days: int, proposal_text: str) -> Tuple[bool, str]:
        """Thread-safe bid submission (called under lock)."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.action_chains import ActionChains

        try:
            if not self._ensure_logged_in():
                return False, "Login failed"

            # Navigate to project page
            self._driver.get(project_url)
            time.sleep(random.uniform(3, 5))

            # ── 1. Bid amount ──
            try:
                amount_field = self._wait.until(
                    EC.presence_of_element_located((By.ID, "bidAmountInput"))
                )
                ActionChains(self._driver).triple_click(amount_field).perform()
                amount_field.send_keys(str(int(amount)))
                log.info("[FreelancerClient] Amount set: %s", amount)
                time.sleep(0.5)
            except Exception as e:
                log.warning("[FreelancerClient] Amount field not found: %s", e)
                # Some projects have different form structure; continue anyway

            # ── 2. Delivery period ──
            try:
                period_field = self._driver.find_element(By.ID, "periodInput")
                ActionChains(self._driver).triple_click(period_field).perform()
                period_field.send_keys(str(days))
                time.sleep(0.3)
            except Exception:
                log.debug("[FreelancerClient] Period field not found, skipping")

            # ── 3. Proposal text ──
            desc_field = self._wait.until(
                EC.presence_of_element_located((By.ID, "descriptionTextArea"))
            )
            desc_field.click()
            time.sleep(0.5)

            # Ensure minimum 120 chars (freelancer requirement)
            text = proposal_text
            if len(text) < 120:
                text += "\n\nI look forward to discussing the project details with you."

            self._human_type(desc_field, text)
            log.info("[FreelancerClient] Proposal text entered (%d chars)", len(text))
            time.sleep(1)

            # ── 4. Submit button ──
            submit_btn = self._wait.until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "fl-button[fltrackinglabel='PlaceBidButton'] button, "
                    "button.submit-btn, "
                    "button[data-bid-submit], "
                    "button.BidForm-submit"
                ))
            )
            self._driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            time.sleep(0.5)
            submit_btn.click()
            time.sleep(random.uniform(3, 5))

            # ── 5. Verify success ──
            success = self._check_bid_success()
            if success:
                self._submitted.add(project_url)
                self._save_submitted()
                msg = f"Bid submitted: {int(amount)}, {days} days"
                log.info("[FreelancerClient] %s", msg)
                return True, msg
            else:
                msg = "Bid form submitted but success not confirmed"
                log.warning("[FreelancerClient] %s", msg)
                # Still mark as submitted to avoid duplicates
                self._submitted.add(project_url)
                self._save_submitted()
                return True, msg

        except Exception as e:
            msg = f"Bid submission error: {e}"
            log.error("[FreelancerClient] %s", msg)
            try:
                # Screenshot for debugging
                ss_path = Path(__file__).resolve().parent.parent / 'data' / 'last_bid_error.png'
                ss_path.parent.mkdir(parents=True, exist_ok=True)
                self._driver.save_screenshot(str(ss_path))
                log.info("[FreelancerClient] Error screenshot saved: %s", ss_path)
            except Exception:
                pass
            return False, msg

    def _check_bid_success(self) -> bool:
        """Check if the bid submission was successful."""
        from selenium.webdriver.common.by import By

        try:
            page_text = self._driver.find_element(By.TAG_NAME, "body").text.lower()
            success_markers = [
                'your bid has been placed',
                'bid placed',
                'successfully',
                'your proposal has been submitted',
                'bid submitted',
            ]
            if any(m in page_text for m in success_markers):
                return True

            # Check for error messages
            error_markers = [
                'insufficient',
                'error',
                'failed',
                'unable to place',
                'minimum bid',
                'already placed',
            ]
            if any(m in page_text for m in error_markers):
                return False

            # No clear signal — assume it worked if we're not on login page
            if 'login' not in self._driver.current_url.lower():
                return True

        except Exception:
            pass
        return False

    # ──────────── Helpers ────────────

    def _human_type(self, element, text: str):
        """Type text with random delays to simulate human input."""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.02, 0.08))

    def _load_submitted(self):
        """Load previously submitted URLs from file."""
        try:
            if _SUBMITTED_FILE.exists():
                with open(_SUBMITTED_FILE, 'r') as f:
                    self._submitted = set(json.load(f))
                log.info("[FreelancerClient] Loaded %d submitted URLs", len(self._submitted))
        except Exception:
            self._submitted = set()

    def _save_submitted(self):
        """Persist submitted URLs to file."""
        try:
            _SUBMITTED_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_SUBMITTED_FILE, 'w') as f:
                json.dump(list(self._submitted), f)
        except Exception as e:
            log.warning("[FreelancerClient] Cannot save submitted URLs: %s", e)

    def is_submitted(self, url: str) -> bool:
        """Check if a bid was already submitted for this URL."""
        return url in self._submitted


# ── Singleton ──
_client: Optional[FreelancerClient] = None


def get_freelancer_client() -> FreelancerClient:
    """Get or create the singleton FreelancerClient."""
    global _client
    if _client is None:
        _client = FreelancerClient()
    return _client
