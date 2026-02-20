"""
Freelancer.com Inbox Reader — monitors messages from clients.

Uses the existing FreelancerClient browser session to:
  1. Open /messages/ inbox
  2. Parse thread list (sender, preview, unread status)
  3. Open new/unread threads and read full messages
  4. Link messages to existing projects (by freelancer URL in project)
  5. Store in project_messages + trigger state transitions
  6. Notify via Telegram

Runs as a scheduled task alongside MailWorker.
"""
import re
import time
import logging
from typing import List, Dict, Optional

from app.database import Database
from app.telegram_notifier import get_notifier
from config import Config

log = logging.getLogger(__name__)

# FL staff accounts — not real clients
_STAFF_ACCOUNTS = {
    'flsofia', 'flmandy', 'flalexi', 'fljanessa',
    'rayrecruiter', 'mikhaelrecruiter', 'enterprisetalent',
    'freelancer', 'freelancer.com',
}

# File to track last-seen threads
_SEEN_THREADS_LIMIT = 200  # max threads to track


class FreelancerInbox:
    """
    Reads messages from freelancer.com /messages/ inbox
    using the shared Selenium browser from FreelancerClient.
    """

    INBOX_URL = "https://www.freelancer.com/messages/"

    def __init__(self):
        self.running = False
        self.check_interval = int(getattr(Config, 'FL_INBOX_INTERVAL', 120))  # seconds
        self._known_thread_ids: set = set()
        self._load_known_threads()

    def start(self):
        """Start the inbox polling loop."""
        self.running = True
        log.info("[FreelancerInbox] Started (interval=%ds)", self.check_interval)
        while self.running:
            try:
                self._poll_inbox()
            except Exception as e:
                log.error("[FreelancerInbox] Poll error: %s", e)
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        self.running = False
        log.info("[FreelancerInbox] Stopped")

    # ──────────── Main poll cycle ────────────

    def _poll_inbox(self):
        """One poll cycle: open inbox → parse threads → read new ones."""
        from app.freelancer_client import get_freelancer_client
        client = get_freelancer_client()
        if not client.enabled:
            return

        driver = client._driver
        if driver is None:
            # Browser not started yet (no bids submitted yet)
            # Don't force-start it; wait until first bid triggers browser
            return

        if not client._logged_in:
            if not client._ensure_logged_in():
                return

        # 1. Open inbox
        try:
            driver.get(self.INBOX_URL)
            time.sleep(3)
        except Exception as e:
            log.error("[FreelancerInbox] Cannot open inbox: %s", e)
            return

        # 2. Parse thread list from sidebar
        threads = self._parse_thread_list(driver)
        if not threads:
            log.debug("[FreelancerInbox] No threads found in inbox")
            return

        # 3. Process new/unread threads
        new_count = 0
        for thread in threads:
            # Skip FL staff
            if thread.get('username', '').lower() in _STAFF_ACCOUNTS:
                continue

            thread_id = thread['thread_id']
            is_new = thread_id not in self._known_thread_ids
            is_unread = thread.get('is_unread', False)

            if is_new or is_unread:
                messages = self._read_thread(driver, thread)
                if messages:
                    self._process_thread_messages(thread, messages)
                    new_count += 1

                self._known_thread_ids.add(thread_id)
                time.sleep(1)  # be gentle

        if new_count > 0:
            log.info("[FreelancerInbox] Processed %d thread(s) with new messages", new_count)
            self._save_known_threads()

    # ──────────── Thread list parsing ────────────

    def _parse_thread_list(self, driver) -> List[Dict]:
        """Parse the inbox sidebar into a list of thread dicts."""
        from selenium.webdriver.common.by import By

        threads = []
        try:
            # Find all thread links in sidebar
            thread_links = driver.find_elements(
                By.CSS_SELECTOR,
                "a[href*='/messages/thread/']"
            )
            log.debug("[FreelancerInbox] Found %d thread links", len(thread_links))

            for link in thread_links:
                try:
                    href = link.get_attribute("href") or ""
                    if '/messages/thread/' not in href:
                        continue

                    # Extract thread ID
                    parts = href.split('/messages/thread/')
                    if len(parts) < 2:
                        continue
                    thread_id = parts[1].split('?')[0].split('/')[0].strip()
                    if not thread_id:
                        continue

                    # Extract text content
                    full_text = link.text.strip()
                    lines = [l.strip() for l in full_text.split('\n') if l.strip()]

                    # First line is usually the display name
                    display_name = lines[0] if lines else ''
                    # Look for @username
                    username = ''
                    preview = ''
                    for line in lines:
                        if line.startswith('@'):
                            username = line.lstrip('@')
                        elif line != display_name and len(line) > 3:
                            preview = line

                    # Check unread status via CSS classes or bold text
                    is_unread = False
                    try:
                        classes = link.get_attribute("class") or ""
                        parent_classes = ""
                        try:
                            parent = link.find_element(By.XPATH, "..")
                            parent_classes = parent.get_attribute("class") or ""
                        except Exception:
                            pass
                        all_classes = f"{classes} {parent_classes}".lower()
                        is_unread = any(w in all_classes for w in
                                        ['unread', 'bold', 'new', 'unseen'])

                        # Also check for unread badge/dot
                        if not is_unread:
                            badges = link.find_elements(
                                By.CSS_SELECTOR,
                                "[class*='unread'], [class*='badge'], .dot"
                            )
                            is_unread = len(badges) > 0
                    except Exception:
                        pass

                    threads.append({
                        'thread_id': thread_id,
                        'username': username or display_name,
                        'display_name': display_name,
                        'preview': preview[:200],
                        'is_unread': is_unread,
                        'url': f"https://www.freelancer.com/messages/thread/{thread_id}",
                    })

                except Exception as e:
                    log.debug("[FreelancerInbox] Error parsing thread link: %s", e)
                    continue

        except Exception as e:
            log.error("[FreelancerInbox] Error getting thread list: %s", e)

        return threads

    # ──────────── Read individual thread ────────────

    def _read_thread(self, driver, thread: Dict) -> List[Dict]:
        """Open a thread and extract messages."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        messages = []
        try:
            driver.get(thread['url'])
            time.sleep(3)

            # Wait for chat area to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "textarea, input[type='text'], [contenteditable], "
                        "[class*='message'], [class*='chat']"
                    ))
                )
            except Exception:
                pass  # continue anyway — page might have different structure

            # Try multiple selectors for message elements
            msg_elements = []
            selectors = [
                "[class*='MessageItem'], [class*='message-item']",
                "[class*='ChatMessage'], [class*='chat-message']",
                "[class*='msg-item'], [class*='MsgItem']",
                ".message-body, .chat-line",
            ]
            for sel in selectors:
                msg_elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if msg_elements:
                    break

            # Fallback: try to get all text blocks in chat area
            if not msg_elements:
                msg_elements = driver.find_elements(
                    By.CSS_SELECTOR,
                    "[class*='message'] p, [class*='chat'] p, "
                    "[class*='Message'] div, [class*='Thread'] div[class]"
                )

            # Also try to extract project link from the thread page
            project_url = self._extract_project_url_from_thread(driver)

            for elem in msg_elements:
                try:
                    text = elem.text.strip()
                    if not text or len(text) < 2:
                        continue

                    # Try to determine if this is from us or the client
                    classes = (elem.get_attribute("class") or "").lower()
                    parent_classes = ""
                    try:
                        p = elem.find_element(By.XPATH, "..")
                        parent_classes = (p.get_attribute("class") or "").lower()
                    except Exception:
                        pass

                    all_classes = f"{classes} {parent_classes}"
                    is_mine = any(w in all_classes for w in
                                  ['right', 'sent', 'mine', 'own', 'self', 'outgoing'])

                    messages.append({
                        'text': text[:2000],
                        'is_mine': is_mine,
                        'sender': Config.FREELANCER_LOGIN if is_mine else thread.get('username', ''),
                    })
                except Exception:
                    continue

            if project_url:
                thread['project_url'] = project_url

            log.info("[FreelancerInbox] Thread %s (%s): %d messages, project_url: %s",
                     thread['thread_id'], thread.get('username', '?'),
                     len(messages), project_url or 'none')

        except Exception as e:
            log.error("[FreelancerInbox] Error reading thread %s: %s",
                      thread['thread_id'], e)

        return messages

    def _extract_project_url_from_thread(self, driver) -> Optional[str]:
        """Try to find a project link in the current thread page."""
        from selenium.webdriver.common.by import By

        try:
            # Look for project links on the thread page
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/projects/']")
            for link in links:
                href = link.get_attribute("href") or ""
                if '/projects/' in href and 'freelancer.com' in href:
                    # Clean URL — strip UTM params
                    clean = href.split('?')[0]
                    return clean
        except Exception:
            pass
        return None

    # ──────────── Process & store messages ────────────

    def _process_thread_messages(self, thread: Dict, messages: List[Dict]):
        """Link thread to project, store messages, trigger state transitions."""
        thread_id = thread['thread_id']
        username = thread.get('username', 'unknown')
        project_url = thread.get('project_url')

        # 1. Find matching project in DB
        project_id = self._find_project_for_thread(thread_id, project_url, username)

        if not project_id:
            # No matching project — notify via Telegram only
            self._notify_unlinked_message(thread, messages)
            return

        # 2. Get only NEW messages (not already stored)
        new_messages = self._filter_new_messages(project_id, thread_id, messages)
        if not new_messages:
            return

        # 3. Store messages
        client_messages = []
        for msg in new_messages:
            direction = 'outbound' if msg.get('is_mine') else 'inbound'
            sender = msg.get('sender', username)
            self._store_fl_message(project_id, thread_id, direction, sender, msg['text'])
            if not msg.get('is_mine'):
                client_messages.append(msg)

        # 4. Update project: set client info if missing
        self._update_project_client_info(project_id, username, thread_id)

        # 5. Trigger state transitions if client replied
        if client_messages:
            self._handle_client_reply(project_id, client_messages)

    def _find_project_for_thread(self, thread_id: str, project_url: Optional[str],
                                  username: str) -> Optional[int]:
        """Find the project that this freelancer.com thread belongs to."""
        try:
            with Database.get_cursor() as cursor:
                # Method 1: Check if we already linked this thread to a project
                cursor.execute("""
                    SELECT DISTINCT project_id FROM project_messages
                    WHERE metadata::text LIKE %s
                    ORDER BY project_id DESC LIMIT 1
                """, (f'%"fl_thread_id": "{thread_id}"%',))
                row = cursor.fetchone()
                if row:
                    return row['project_id']

                # Method 2: Match by project URL (stored in requirements_doc)
                if project_url:
                    # Normalize URL for matching
                    clean_url = project_url.split('?')[0].rstrip('/')
                    cursor.execute("""
                        SELECT id FROM projects
                        WHERE source = 'freelancer.com'
                          AND requirements_doc LIKE %s
                          AND current_state NOT IN ('CLOSED', 'REJECTED')
                        ORDER BY created_at DESC LIMIT 1
                    """, (f'%{clean_url}%',))
                    row = cursor.fetchone()
                    if row:
                        return row['id']

                # Method 3: Match by username in project messages
                # (when we sent a bid, Telegram notified with the URL)
                cursor.execute("""
                    SELECT p.id FROM projects p
                    WHERE p.source = 'freelancer.com'
                      AND p.current_state NOT IN ('CLOSED', 'REJECTED')
                      AND p.client_email = %s
                    ORDER BY p.updated_at DESC LIMIT 1
                """, (f'{username}@freelancer.com',))
                row = cursor.fetchone()
                if row:
                    return row['id']

        except Exception as e:
            log.error("[FreelancerInbox] Error finding project for thread %s: %s",
                      thread_id, e)
        return None

    def _filter_new_messages(self, project_id: int, thread_id: str,
                              messages: List[Dict]) -> List[Dict]:
        """Return only messages not already stored in DB."""
        try:
            with Database.get_cursor() as cursor:
                # Get last stored message text for this thread
                cursor.execute("""
                    SELECT body FROM project_messages
                    WHERE project_id = %s AND metadata::text LIKE %s
                    ORDER BY created_at DESC LIMIT 5
                """, (project_id, f'%"fl_thread_id": "{thread_id}"%'))
                known_texts = {row['body'].strip()[:100] for row in cursor.fetchall()}

            # Filter out already-known messages
            new = []
            for msg in messages:
                snippet = msg['text'].strip()[:100]
                if snippet not in known_texts:
                    new.append(msg)
            return new

        except Exception:
            return messages  # if check fails, store all

    def _store_fl_message(self, project_id: int, thread_id: str,
                           direction: str, sender: str, text: str):
        """Store a freelancer.com message in project_messages."""
        try:
            import json
            metadata = json.dumps({
                'fl_thread_id': thread_id,
                'source': 'freelancer.com',
            })
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO project_messages
                    (project_id, direction, sender_email, subject, body,
                     message_id, is_processed, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """, (
                    project_id, direction,
                    f'{sender}@freelancer.com',
                    f'FL message (thread {thread_id})',
                    text,
                    f'fl-{thread_id}-{hash(text[:50])}',
                    direction == 'outbound',  # outbound = already processed
                    metadata,
                ))
        except Exception as e:
            log.error("[FreelancerInbox] Error storing message: %s", e)

    def _update_project_client_info(self, project_id: int, username: str,
                                     thread_id: str):
        """Set client_email on the project if not yet set (for freelancer.com projects)."""
        try:
            fl_email = f'{username}@freelancer.com'
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE projects
                    SET client_email = COALESCE(NULLIF(client_email, ''), %s),
                        source_message_id = COALESCE(NULLIF(source_message_id, ''), %s),
                        updated_at = NOW()
                    WHERE id = %s AND source = 'freelancer.com'
                """, (fl_email, f'fl-thread-{thread_id}', project_id))
        except Exception as e:
            log.error("[FreelancerInbox] Error updating project client info: %s", e)

    def _handle_client_reply(self, project_id: int, client_messages: List[Dict]):
        """Trigger state transitions when client replies on freelancer.com."""
        latest_text = client_messages[-1]['text'] if client_messages else ''
        username = client_messages[-1].get('sender', '')

        try:
            with Database.get_cursor() as cursor:
                cursor.execute("SELECT title, current_state FROM projects WHERE id = %s",
                               (project_id,))
                proj = cursor.fetchone()
                if not proj:
                    return

                title = proj['title']
                state = proj['current_state']

                # OFFER_SENT → NEGOTIATION
                if state == 'OFFER_SENT':
                    cursor.execute("""
                        UPDATE projects SET current_state = 'NEGOTIATION', updated_at = NOW()
                        WHERE id = %s
                    """, (project_id,))
                    cursor.execute("""
                        INSERT INTO project_states
                        (project_id, from_state, to_state, changed_by, reason)
                        VALUES (%s, 'OFFER_SENT', 'NEGOTIATION', 'freelancer_inbox',
                                'Client replied on freelancer.com')
                    """, (project_id,))
                    log.info("[FreelancerInbox] Project #%d: OFFER_SENT → NEGOTIATION", project_id)

                # CLARIFICATION_NEEDED → CLASSIFIED (re-analyse)
                elif state == 'CLARIFICATION_NEEDED':
                    cursor.execute("""
                        UPDATE projects SET current_state = 'CLASSIFIED', updated_at = NOW()
                        WHERE id = %s
                    """, (project_id,))
                    cursor.execute("""
                        INSERT INTO project_states
                        (project_id, from_state, to_state, changed_by, reason)
                        VALUES (%s, 'CLARIFICATION_NEEDED', 'CLASSIFIED', 'freelancer_inbox',
                                'Client replied to clarification on freelancer.com')
                    """, (project_id,))
                    log.info("[FreelancerInbox] Project #%d: CLARIFICATION → CLASSIFIED", project_id)

            # Telegram notification
            tg = get_notifier()
            from app.telegram_notifier import _esc
            msg = (
                f"💬 <b>Ответ на freelancer.com — проект #{project_id}</b>\n\n"
                f"<b>{_esc(title)}</b>\n"
                f"👤 <b>От:</b> @{_esc(username)}\n"
                f"📊 <b>Статус:</b> {state} → NEGOTIATION\n\n"
                f"<b>Сообщение:</b>\n"
                f"<code>{_esc(latest_text[:1500])}</code>"
            )
            tg.send(msg)

        except Exception as e:
            log.error("[FreelancerInbox] Error handling client reply: %s", e)

    def _notify_unlinked_message(self, thread: Dict, messages: List[Dict]):
        """Notify Telegram about a message we can't link to any project."""
        client_msgs = [m for m in messages if not m.get('is_mine')]
        if not client_msgs:
            return

        latest = client_msgs[-1]['text']
        username = thread.get('username', '?')

        try:
            tg = get_notifier()
            from app.telegram_notifier import _esc
            msg = (
                f"💬 <b>Новое сообщение на freelancer.com</b>\n\n"
                f"👤 @{_esc(username)} ({_esc(thread.get('display_name', ''))})\n"
                f"🔗 <a href=\"{thread['url']}\">Открыть тред</a>\n\n"
                f"<b>Сообщение:</b>\n"
                f"<code>{_esc(latest[:1500])}</code>\n\n"
                f"⚠️ Не удалось привязать к проекту. Ответьте вручную."
            )
            tg.send(msg)
        except Exception as e:
            log.error("[FreelancerInbox] Telegram notify error: %s", e)

    # ──────────── Persistence for known threads ────────────

    def _load_known_threads(self):
        """Load thread IDs that we've already processed from DB."""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT metadata->>'fl_thread_id' AS tid
                    FROM project_messages
                    WHERE metadata->>'fl_thread_id' IS NOT NULL
                """)
                self._known_thread_ids = {
                    row['tid'] for row in cursor.fetchall() if row['tid']
                }
                log.info("[FreelancerInbox] Loaded %d known thread IDs",
                         len(self._known_thread_ids))
        except Exception:
            self._known_thread_ids = set()

    def _save_known_threads(self):
        """Known threads are saved via project_messages — no separate persistence needed."""
        pass


# ── Singleton ──
_inbox: Optional[FreelancerInbox] = None


def get_freelancer_inbox() -> FreelancerInbox:
    """Get or create the singleton FreelancerInbox."""
    global _inbox
    if _inbox is None:
        _inbox = FreelancerInbox()
    return _inbox
