"""
Mail Worker — background process for email intake and sending.
Handles:
  - Reading new emails from IMAP (inbox)
  - Creating project records from email inquiries (ONLY from allowed domains)
  - Linking emails to existing projects (via In-Reply-To / subject matching)
  - Sending pending outbound messages via SMTP
"""
import time
import email
import imaplib
import re
from email.header import decode_header
from app.database import Database, QueryHelper
from app.telegram_notifier import get_notifier
from app.parsers.freelancer_parser import is_freelancer_digest, parse_digest
from config import Config


# ── DOMAIN FILTERING ──
# ALLOWED_SENDER_DOMAINS from .env (comma-separated).  Use "*" to accept all.
# BLOCKED_SENDER_DOMAINS — always rejected even when allowed = "*".
_raw_allowed = getattr(Config, 'ALLOWED_SENDER_DOMAINS', '*')
ALLOWED_SENDER_DOMAINS = (
    [d.strip().lower() for d in _raw_allowed.split(',') if d.strip()]
    if _raw_allowed and _raw_allowed.strip() != '*' else []
)   # empty list = accept all

BLOCKED_SENDER_DOMAINS = [
    'noreply', 'no-reply', 'mailer-daemon',
    'postmaster', 'bounce', 'donotreply',
]


class MailWorker:
    def __init__(self):
        self.running = False
        self.check_interval = 30  # seconds
        self._imap_failed = False  # suppress repeated IMAP error logs
        self._smtp_failed = False  # suppress repeated SMTP error logs

    def start(self):
        """Start the mail intake loop"""
        self.running = True
        print("[MailWorker] Started")
        self._intake_loop()

    def stop(self):
        self.running = False
        print("[MailWorker] Stopped")

    def _intake_loop(self):
        while self.running:
            try:
                # Check if email credentials are configured
                mail_user = self._get_mail_username()
                mail_pass = self._get_mail_password()
                
                if mail_user and mail_pass and not self._is_placeholder(mail_user):
                    self._process_new_emails(mail_user, mail_pass)
                    self._send_pending_emails()
                elif not self._imap_failed:
                    print("[MailWorker] Email credentials not configured or placeholder — skipping")
                    self._imap_failed = True
            except Exception as e:
                print(f"[MailWorker] Error: {e}")
            
            time.sleep(self.check_interval)

    @staticmethod
    def _is_placeholder(value):
        """Check if a credential is a placeholder value"""
        placeholders = ['your_email@gmail.com', 'your_password', 'changeme', '']
        return value.strip().lower() in placeholders

    def _get_mail_username(self):
        """Get mail username from settings or config"""
        try:
            return QueryHelper.get_system_setting('mail_username') or Config.MAIL_USERNAME
        except Exception:
            return Config.MAIL_USERNAME

    def _get_mail_password(self):
        """Get mail password from settings or config"""
        try:
            return QueryHelper.get_system_setting('mail_password') or Config.MAIL_PASSWORD
        except Exception:
            return Config.MAIL_PASSWORD

    def _process_new_emails(self, mail_user, mail_pass):
        """Connect to IMAP and process new emails"""
        try:
            mail = imaplib.IMAP4_SSL(Config.MAIL_HOST, Config.MAIL_PORT)
            mail.login(mail_user, mail_pass)
            mail.select('inbox')
            self._imap_failed = False  # reset on success

            # Only fetch emails from last 7 days to avoid processing ancient mail
            # Use SINCE (not UNSEEN) — emails may be read in browser/phone
            from datetime import datetime, timedelta
            since_date = (datetime.now() - timedelta(days=7)).strftime('%d-%b-%Y')
            status, messages = mail.search(None, f'(SINCE {since_date})')
            if status != 'OK':
                mail.logout()
                return

            msg_ids = messages[0].split()
            if not msg_ids:
                mail.logout()
                return

            # Limit to 20 emails per cycle to avoid overload
            msg_ids = msg_ids[:20]

            # Filter out already-processed emails by Message-ID
            processed_ids = self._get_processed_message_ids()

            created = 0
            skipped = 0
            for msg_id in msg_ids:
                try:
                    status, msg_data = mail.fetch(msg_id, '(RFC822)')
                    if status == 'OK':
                        email_message = email.message_from_bytes(msg_data[0][1])
                        mid = email_message.get('Message-ID', '')
                        if mid and mid in processed_ids:
                            continue  # already processed
                        was_created = self._handle_email(email_message)
                        if was_created:
                            created += 1
                        else:
                            skipped += 1
                except Exception as e:
                    print(f"[MailWorker] Error processing email {msg_id}: {e}")

            mail.logout()
            if created > 0 or skipped > 0:
                print(f"[MailWorker] Cycle done: {created} project(s) created, {skipped} skipped")

        except Exception as e:
            if not self._imap_failed:
                print(f"[MailWorker] IMAP error: {e}")
                self._imap_failed = True

    def _get_processed_message_ids(self):
        """Get set of Message-IDs already stored in project_messages (last 7 days)."""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT message_id FROM project_messages
                    WHERE message_id IS NOT NULL
                      AND created_at > NOW() - INTERVAL '7 days'
                """)
                return {row['message_id'] for row in cursor.fetchall()}
        except Exception:
            return set()

    @staticmethod
    def _is_bulk_email(email_message):
        """Detect automated/bulk emails that should be skipped.
        Lightweight filter — since the inbox is dedicated, most mail is valid."""
        # 1. List-Unsubscribe header → newsletter / marketing
        if email_message.get('List-Unsubscribe'):
            return True
        # 2. Precedence: bulk / list / junk
        precedence = (email_message.get('Precedence') or '').lower()
        if precedence in ('bulk', 'list', 'junk'):
            return True
        # 3. Auto-Submitted (auto-generated bounce / vacation notices)
        auto_submitted = (email_message.get('Auto-Submitted') or '').lower()
        if auto_submitted and auto_submitted != 'no':
            return True
        return False

    def _handle_email(self, email_message):
        """Decide if email is a new project or a reply to existing. Returns True if project created."""
        sender = email_message.get('From', '')
        subject = self._decode_header(email_message.get('Subject', ''))
        body = self._get_email_body(email_message)
        message_id = email_message.get('Message-ID', '')
        in_reply_to = email_message.get('In-Reply-To', '')

        # Extract email address from sender
        email_match = re.search(r'<([^>]+)>', sender)
        client_email = email_match.group(1) if email_match else sender.strip()

        # ── Freelancer.com digest: check BEFORE blocklist ──
        # (digests come from noreply@notifications.freelancer.com)
        if is_freelancer_digest(subject, body):
            return self._handle_freelancer_digest(body, message_id)

        # ── DOMAIN FILTERING ──
        sender_local = client_email.split('@')[0].lower() if '@' in client_email else ''
        sender_domain = client_email.split('@')[-1].lower() if '@' in client_email else ''

        # Always block known automated / noreply addresses
        if any(b in sender_local for b in BLOCKED_SENDER_DOMAINS):
            return False

        # Whitelist check (empty list = accept all)
        is_whitelisted = True
        if ALLOWED_SENDER_DOMAINS:
            if not any(sender_domain.endswith(d) for d in ALLOWED_SENDER_DOMAINS):
                return False  # domain not in whitelist
        # If we reached here, the sender is allowed

        # Skip automated/bulk mail (only for non-whitelisted senders)
        if not is_whitelisted and self._is_bulk_email(email_message):
            return False

        # Check if this is a reply to an existing project
        existing_project_id = self._find_existing_project(in_reply_to, subject, client_email)

        if existing_project_id:
            # Add as inbound message to existing project
            self._add_message_to_project(existing_project_id, client_email, subject, body, message_id, in_reply_to)
            print(f"[MailWorker] Added reply to project #{existing_project_id}")

            # If project is in OFFER_SENT state, move to NEGOTIATION
            self._check_offer_response(existing_project_id, body)

            # If project is waiting for clarification, move back to CLASSIFIED
            self._check_clarification_response(existing_project_id, body)
            return True
        else:
            # Create new project
            self._create_project_from_email(client_email, subject, body, message_id)
            return True

    def _find_existing_project(self, in_reply_to, subject, client_email):
        """Try to find an existing project this email belongs to"""
        try:
            with Database.get_cursor() as cursor:
                # Method 1: Match by In-Reply-To header
                if in_reply_to:
                    cursor.execute("""
                        SELECT project_id FROM project_messages 
                        WHERE message_id = %s LIMIT 1
                    """, (in_reply_to,))
                    result = cursor.fetchone()
                    if result:
                        return result['project_id']

                # Method 2: Match by subject + client email (for active projects)
                if subject and client_email:
                    # Strip "Re:" prefixes
                    clean_subject = re.sub(r'^(Re:\s*)+', '', subject, flags=re.IGNORECASE).strip()
                    if clean_subject:
                        cursor.execute("""
                            SELECT p.id FROM projects p
                            LEFT JOIN project_messages pm ON pm.project_id = p.id
                            WHERE p.client_email = %s 
                            AND p.current_state NOT IN ('CLOSED', 'REJECTED')
                            AND (p.title ILIKE %s OR pm.subject ILIKE %s)
                            ORDER BY p.updated_at DESC
                            LIMIT 1
                        """, (client_email, f'%{clean_subject}%', f'%{clean_subject}%'))
                        result = cursor.fetchone()
                        if result:
                            return result['id']

                # Method 3: Match freelancer.com projects by title
                # (client from FL wrote to our email — project has no client_email yet)
                if subject and client_email:
                    clean_subject = re.sub(r'^(Re:\s*)+', '', subject, flags=re.IGNORECASE).strip()
                    if clean_subject:
                        cursor.execute("""
                            SELECT id FROM projects
                            WHERE source = 'freelancer.com'
                              AND current_state NOT IN ('CLOSED', 'REJECTED')
                              AND (client_email IS NULL OR client_email = '')
                              AND title ILIKE %s
                            ORDER BY updated_at DESC LIMIT 1
                        """, (f'%{clean_subject}%',))
                        result = cursor.fetchone()
                        if result:
                            # Link client email to this project
                            cursor.execute("""
                                UPDATE projects SET client_email = %s, updated_at = NOW()
                                WHERE id = %s
                            """, (client_email, result['id']))
                            print(f"[MailWorker] Linked email {client_email} to FL project #{result['id']}")
                            return result['id']

        except Exception as e:
            print(f"[MailWorker] Error finding existing project: {e}")

        return None

    def _add_message_to_project(self, project_id, sender_email, subject, body, message_id, in_reply_to):
        """Add an inbound message to an existing project"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO project_messages 
                    (project_id, direction, sender_email, subject, body, message_id, in_reply_to, is_processed)
                    VALUES (%s, 'inbound', %s, %s, %s, %s, %s, FALSE)
                """, (project_id, sender_email, subject, body, message_id, in_reply_to))
        except Exception as e:
            print(f"[MailWorker] Error adding message: {e}")

    def _check_offer_response(self, project_id, body=''):
        """If project is in OFFER_SENT, move to NEGOTIATION"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE projects SET current_state = 'NEGOTIATION', updated_at = NOW()
                    WHERE id = %s AND current_state = 'OFFER_SENT'
                """, (project_id,))
                if cursor.rowcount > 0:
                    cursor.execute("""
                        INSERT INTO project_states (project_id, from_state, to_state, changed_by, reason)
                        VALUES (%s, 'OFFER_SENT', 'NEGOTIATION', 'mail_worker', 'Client replied to offer')
                    """, (project_id,))
                    print(f"[MailWorker] Project #{project_id}: OFFER_SENT → NEGOTIATION (client replied)")

                    # Notify owner: client replied!
                    try:
                        cursor.execute("SELECT title, client_email FROM projects WHERE id = %s", (project_id,))
                        proj = cursor.fetchone()
                        if proj:
                            get_notifier().notify_client_reply(
                                project_id, proj['title'], proj['client_email'], body[:200] if body else ''
                            )
                    except Exception:
                        pass
        except Exception as e:
            print(f"[MailWorker] Error updating project state: {e}")

    def _check_clarification_response(self, project_id, body=''):
        """If project is in CLARIFICATION_NEEDED, client replied — re-analyse requirements."""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE projects SET current_state = 'CLASSIFIED', updated_at = NOW()
                    WHERE id = %s AND current_state = 'CLARIFICATION_NEEDED'
                """, (project_id,))
                if cursor.rowcount > 0:
                    cursor.execute("""
                        INSERT INTO project_states (project_id, from_state, to_state, changed_by, reason)
                        VALUES (%s, 'CLARIFICATION_NEEDED', 'CLASSIFIED', 'mail_worker',
                                'Client replied to clarification questions — re-analysing')
                    """, (project_id,))
                    print(f"[MailWorker] Project #{project_id}: CLARIFICATION_NEEDED → CLASSIFIED (client replied)")

                    try:
                        cursor.execute("SELECT title, client_email FROM projects WHERE id = %s", (project_id,))
                        proj = cursor.fetchone()
                        if proj:
                            get_notifier().notify_client_reply(
                                project_id, proj['title'], proj['client_email'], body[:200] if body else ''
                            )
                    except Exception:
                        pass
        except Exception as e:
            print(f"[MailWorker] Error checking clarification response: {e}")

    def _handle_freelancer_digest(self, body, message_id):
        """Parse a freelancer.com digest email and create multiple projects."""
        projects = parse_digest(body)
        if not projects:
            return False

        created = 0
        for proj in projects:
            try:
                # Truncate title to 490 chars (DB column is VARCHAR(500))
                proj['title'] = (proj['title'] or 'Untitled')[:490]

                with Database.get_cursor() as cursor:
                    # Duplicate check: same title from freelancer.com in last 48h
                    cursor.execute("""
                        SELECT id FROM projects
                        WHERE title = %s AND source = 'freelancer.com'
                          AND created_at > NOW() - INTERVAL '48 hours'
                    """, (proj['title'],))
                    if cursor.fetchone():
                        continue  # skip duplicate

                    # Create project directly in PARSED state (data already structured)
                    budget_note = f"Budget: {proj['budget_raw']}"
                    if proj['is_hourly']:
                        budget_note += ' (hourly rate)'

                    full_desc = (
                        f"{proj['description']}\n\n"
                        f"Skills: {', '.join(proj['tech_stack'])}\n"
                        f"{budget_note}\n"
                        f"URL: {proj['freelancer_url']}"
                    )

                    cursor.execute("""
                        INSERT INTO projects (
                            title, description, budget_min, budget_max,
                            tech_stack, category, current_state, source,
                            requirements_doc, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'PARSED', 'freelancer.com',
                                  %s, NOW(), NOW())
                        RETURNING id
                    """, (
                        proj['title'],
                        full_desc,
                        proj['budget_min'],
                        proj['budget_max'],
                        proj['tech_stack'],
                        proj['category'],
                        proj['freelancer_url']
                    ))
                    project_id = cursor.fetchone()['id']

                    # Store listing as inbound message (already processed — no AI parse needed)
                    cursor.execute("""
                        INSERT INTO project_messages
                        (project_id, direction, sender_email, subject, body, message_id, is_processed)
                        VALUES (%s, 'inbound', 'noreply@notifications.freelancer.com', %s, %s, %s, TRUE)
                    """, (project_id, proj['title'], full_desc, message_id))

                    # Log state transition
                    cursor.execute("""
                        INSERT INTO project_states (project_id, from_state, to_state, changed_by, reason)
                        VALUES (%s, 'NEW', 'PARSED', 'freelancer_parser', %s)
                    """, (project_id, budget_note))

                print(f"[MailWorker] Freelancer #{project_id}: {proj['title'][:60]}")

                # Telegram notification
                desc_with_budget = (
                    f"💵 {proj['budget_raw']}\n"
                    f"🛠 {', '.join(proj['tech_stack'][:5])}\n\n"
                    f"{proj['description'][:250]}"
                )
                get_notifier().notify_new_project(
                    project_id, proj['title'],
                    proj['freelancer_url'], desc_with_budget
                )

                created += 1
            except Exception as e:
                print(f"[MailWorker] Error creating freelancer project: {e}")

        if created > 0:
            print(f"[MailWorker] Created {created} freelancer project(s) from digest")

        return created > 0

    def _create_project_from_email(self, client_email, subject, body, message_id):
        """Create a new project record from email data"""
        try:
            # Ensure client exists
            client_id = self._ensure_client(client_email)

            title = subject.strip() if subject.strip() else body.split('\n')[0][:200] if body else 'Untitled Project'
            if not title:
                title = 'Untitled Project'

            description = f"Subject: {subject}\n\n{body}" if subject else body

            with Database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO projects (title, client_email, client_id, description, 
                                         current_state, source, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'NEW', 'email', NOW(), NOW())
                    RETURNING id
                """, (title, client_email, client_id, description))
                project_id = cursor.fetchone()['id']

                # Also store the original email as a message
                cursor.execute("""
                    INSERT INTO project_messages 
                    (project_id, direction, sender_email, subject, body, message_id, is_processed)
                    VALUES (%s, 'inbound', %s, %s, %s, %s, FALSE)
                """, (project_id, client_email, subject, body, message_id))

            print(f"[MailWorker] Created project #{project_id}: {title}")

            # Notify owner via Telegram
            get_notifier().notify_new_project(project_id, title, client_email, description)

        except Exception as e:
            print(f"[MailWorker] Error creating project: {e}")

    def _ensure_client(self, email_addr):
        """Create client if not exists, return client_id"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("SELECT id FROM clients WHERE email = %s", (email_addr,))
                result = cursor.fetchone()
                if result:
                    return result['id']

                cursor.execute("""
                    INSERT INTO clients (email) VALUES (%s)
                    ON CONFLICT (email) DO NOTHING
                    RETURNING id
                """, (email_addr,))
                result = cursor.fetchone()
                if result:
                    return result['id']

                # If ON CONFLICT hit, fetch again
                cursor.execute("SELECT id FROM clients WHERE email = %s", (email_addr,))
                result = cursor.fetchone()
                return result['id'] if result else None
        except Exception as e:
            print(f"[MailWorker] Error ensuring client: {e}")
            return None

    def _send_pending_emails(self):
        """Send any pending outbound messages via SMTP"""
        try:
            from app.email_sender import get_email_sender
            sender = get_email_sender()
            sent = sender.send_pending_messages()
            if sent == 0 and self._smtp_failed:
                return  # Already logged, don't spam
            if sent and sent > 0:
                self._smtp_failed = False
        except Exception as e:
            if not self._smtp_failed:
                print(f"[MailWorker] Error sending pending emails: {e}")
                self._smtp_failed = True

    def _decode_header(self, header):
        if header:
            decoded_parts = decode_header(header)
            result = ''
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    result += part.decode(encoding or 'utf-8', errors='ignore')
                else:
                    result += part
            return result
        return ""

    def _get_email_body(self, email_message):
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode('utf-8', errors='ignore')
                    break
        else:
            payload = email_message.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='ignore')
        return body