"""
Email Sender — SMTP client for sending emails to clients.
Used by the workflow to send offers, replies, and notifications.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config
from app.database import Database, QueryHelper


class EmailSender:
    """Sends emails via SMTP (Gmail or other providers)"""

    def __init__(self):
        self.smtp_host = Config.SMTP_HOST
        self.smtp_port = Config.SMTP_PORT
        self.use_tls = Config.SMTP_USE_TLS

    def _get_credentials(self):
        """Get SMTP credentials from system settings (priority) or config"""
        username = QueryHelper.get_system_setting('smtp_username') or \
                   QueryHelper.get_system_setting('mail_username') or \
                   Config.SMTP_USERNAME
        password = QueryHelper.get_system_setting('smtp_password') or \
                   QueryHelper.get_system_setting('mail_password') or \
                   Config.SMTP_PASSWORD
        return username, password

    def send_email(self, to_email, subject, body, html_body=None, from_name="AI Freelance Operator"):
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            from_name: Display name of sender
            
        Returns:
            bool: True if sent successfully
        """
        username, password = self._get_credentials()

        if not username or not password:
            print("[EmailSender] SMTP credentials not configured")
            return False

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{from_name} <{username}>"
            msg['To'] = to_email
            msg['Subject'] = subject

            # Add plain text
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            # Add HTML if provided
            if html_body:
                msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            # Send
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)

            server.login(username, password)
            server.send_message(msg)
            server.quit()

            print(f"[EmailSender] Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            print(f"[EmailSender] Failed to send email to {to_email}: {e}")
            return False

    def send_pending_messages(self):
        """
        Send all pending outbound messages from the project_messages table.
        Called periodically by the background scheduler.
        Returns number of messages sent.
        """
        try:
            with Database.get_cursor() as cursor:
                # Get unsent outbound messages that have a valid recipient
                cursor.execute("""
                    SELECT id, project_id, recipient_email, subject, body, html_body
                    FROM project_messages
                    WHERE direction = 'outbound' AND is_processed = FALSE
                      AND recipient_email IS NOT NULL AND recipient_email != ''
                    ORDER BY created_at ASC
                    LIMIT 10
                """)
                messages = cursor.fetchall()

            if not messages:
                return 0

            sent_count = 0
            for msg in messages:
                success = self.send_email(
                    to_email=msg['recipient_email'],
                    subject=msg['subject'] or 'No Subject',
                    body=msg['body'] or '',
                    html_body=msg.get('html_body')
                )

                if success:
                    # Mark as sent
                    with Database.get_cursor() as cursor:
                        cursor.execute(
                            "UPDATE project_messages SET is_processed = TRUE WHERE id = %s",
                            (msg['id'],)
                        )
                    sent_count += 1

                    # Log
                    QueryHelper.log_agent_action(
                        agent_name='email_sender',
                        action='EMAIL_SENT',
                        project_id=msg['project_id'],
                        output_data={
                            'to': msg['recipient_email'],
                            'subject': msg['subject']
                        }
                    )

            if sent_count > 0:
                print(f"[EmailSender] Sent {sent_count} pending message(s)")

            return sent_count

        except Exception as e:
            print(f"[EmailSender] Error processing pending messages: {e}")
            return 0

    def test_connection(self):
        """Test SMTP connection"""
        username, password = self._get_credentials()

        if not username or not password:
            return False, "SMTP credentials not configured"

        try:
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)

            server.login(username, password)
            server.quit()
            return True, "Connection successful"

        except Exception as e:
            return False, str(e)


# Singleton
_email_sender = None

def get_email_sender():
    global _email_sender
    if _email_sender is None:
        _email_sender = EmailSender()
    return _email_sender
