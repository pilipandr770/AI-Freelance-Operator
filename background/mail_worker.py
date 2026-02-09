import time
import email
import imaplib
from email.header import decode_header
from app.database import Database
from config import Config

class MailWorker:
    def __init__(self):
        self.config = Config()
        self.running = False

    def start(self):
        """Start the mail intake loop"""
        self.running = True
        print("Mail worker started")
        self._intake_loop()

    def stop(self):
        """Stop the mail intake"""
        self.running = False

    def _intake_loop(self):
        """Main loop for checking mail every 30-60 seconds"""
        while self.running:
            try:
                self._process_new_emails()
            except Exception as e:
                print(f"Mail worker error: {e}")
            time.sleep(30)  # Check every 30 seconds

    def _process_new_emails(self):
        """Connect to IMAP and process new freelance inquiry emails"""
        try:
            # Connect to IMAP
            mail = imaplib.IMAP4_SSL(self.config.MAIL_HOST, self.config.MAIL_PORT)
            mail.login(self.config.MAIL_USERNAME, self.config.MAIL_PASSWORD)
            mail.select('inbox')

            # Search for unread emails (you might want to filter by subject/sender)
            status, messages = mail.search(None, 'UNSEEN')

            if status == 'OK':
                for msg_id in messages[0].split():
                    # Fetch the email
                    status, msg_data = mail.fetch(msg_id, '(RFC822)')
                    if status == 'OK':
                        email_message = email.message_from_bytes(msg_data[0][1])

                        # Extract sender and subject
                        sender = email_message['From']
                        subject = self._decode_header(email_message['Subject'])

                        # Extract body
                        body = self._get_email_body(email_message)

                        # Create project from email
                        self._create_project_from_email(sender, subject, body)

                        # Mark as read (optional)
                        mail.store(msg_id, '+FLAGS', '\\Seen')

            mail.logout()

        except Exception as e:
            print(f"IMAP connection error: {e}")

    def _decode_header(self, header):
        """Decode email header"""
        if header:
            decoded_parts = decode_header(header)
            subject = ''
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    subject += part.decode(encoding or 'utf-8')
                else:
                    subject += part
            return subject
        return ""

    def _get_email_body(self, email_message):
        """Extract plain text body from email"""
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
        else:
            body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
        return body

    def _create_project_from_email(self, sender, subject, body):
        """Create a new project record from email data"""
        with Database.get_connection() as conn:
            cursor = conn.cursor()

            # Extract email from sender (simple parsing)
            import re
            email_match = re.search(r'<([^>]+)>', sender)
            client_email = email_match.group(1) if email_match else sender

            # Combine subject and body as description
            description = f"Subject: {subject}\n\n{body}"

            # Insert new project
            cursor.execute("""
                INSERT INTO projects (client_email, description, current_state, source, created_at, updated_at)
                VALUES (%s, %s, 'NEW', 'email', NOW(), NOW())
                RETURNING id
            """, (client_email, description))

            project_id = cursor.fetchone()[0]

            print(f"Created new project {project_id} from email: {subject}")