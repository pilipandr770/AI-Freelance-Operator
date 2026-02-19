"""
Mail Worker — background process for email intake and sending.
Handles:
  - Reading new emails from IMAP (inbox)
  - Creating project records from email inquiries
  - Linking emails to existing projects (via In-Reply-To / subject matching)
  - Sending pending outbound messages via SMTP
"""
import time
import email
import imaplib
import re
from email.header import decode_header
from app.database import Database, QueryHelper
from config import Config


class MailWorker:
    def __init__(self):
        self.running = False
        self.check_interval = 30  # seconds

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
                
                if mail_user and mail_pass:
                    self._process_new_emails(mail_user, mail_pass)
                    self._send_pending_emails()
            except Exception as e:
                print(f"[MailWorker] Error: {e}")
            
            time.sleep(self.check_interval)

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

            status, messages = mail.search(None, 'UNSEEN')
            if status != 'OK':
                mail.logout()
                return

            msg_ids = messages[0].split()
            if not msg_ids:
                mail.logout()
                return

            print(f"[MailWorker] Found {len(msg_ids)} new email(s)")

            for msg_id in msg_ids:
                try:
                    status, msg_data = mail.fetch(msg_id, '(RFC822)')
                    if status == 'OK':
                        email_message = email.message_from_bytes(msg_data[0][1])
                        self._handle_email(email_message)
                        mail.store(msg_id, '+FLAGS', '\\Seen')
                except Exception as e:
                    print(f"[MailWorker] Error processing email {msg_id}: {e}")

            mail.logout()

        except Exception as e:
            print(f"[MailWorker] IMAP error: {e}")

    def _handle_email(self, email_message):
        """Decide if email is a new project or a reply to existing"""
        sender = email_message.get('From', '')
        subject = self._decode_header(email_message.get('Subject', ''))
        body = self._get_email_body(email_message)
        message_id = email_message.get('Message-ID', '')
        in_reply_to = email_message.get('In-Reply-To', '')

        # Extract email address from sender
        email_match = re.search(r'<([^>]+)>', sender)
        client_email = email_match.group(1) if email_match else sender.strip()

        # Check if this is a reply to an existing project
        existing_project_id = self._find_existing_project(in_reply_to, subject, client_email)

        if existing_project_id:
            # Add as inbound message to existing project
            self._add_message_to_project(existing_project_id, client_email, subject, body, message_id, in_reply_to)
            print(f"[MailWorker] Added reply to project #{existing_project_id}")

            # If project is in OFFER_SENT state, move to NEGOTIATION
            self._check_offer_response(existing_project_id)
        else:
            # Create new project
            self._create_project_from_email(client_email, subject, body, message_id)

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

    def _check_offer_response(self, project_id):
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
        except Exception as e:
            print(f"[MailWorker] Error updating project state: {e}")

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
            sender.send_pending_messages()
        except Exception as e:
            print(f"[MailWorker] Error sending pending emails: {e}")

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