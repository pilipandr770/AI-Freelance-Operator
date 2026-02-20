"""
Telegram Notifier — sends event notifications to the owner via Telegram Bot API.

Uses raw HTTP requests (no async framework needed).
All methods are fire-and-forget: errors are logged but never raised,
so a Telegram outage can never break the main workflow.
"""
import json
import time
import threading
import requests
from config import Config


# ── Emoji mapping for event types ──
_ICONS = {
    'new_project':    '🆕',
    'rejected':       '🚫',
    'analyzed':       '🔍',
    'classified':     '📊',
    'estimation':     '💰',
    'offer_sent':     '📨',
    'client_reply':   '💬',
    'agreed':         '✅',
    'negotiation':    '🤝',
    'escalate':       '⚠️',
    'error':          '🚨',
    'info':           '📌',
    'email_sent':     '📧',
    'email_failed':   '❌',
    'system':         '🔧',
}

_BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Singleton Telegram notifier."""

    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.chat_id = Config.TELEGRAM_OWNER_ID
        self._enabled = bool(self.token and self.chat_id)
        self._lock = threading.Lock()
        self._last_send = 0.0  # timestamp of last successful send
        self._MIN_INTERVAL = 0.5  # min seconds between messages
        if not self._enabled:
            print("[Telegram] Bot token or owner ID not configured — notifications disabled")

    # ───────── low-level ─────────

    def send(self, text: str, parse_mode: str = 'HTML') -> bool:
        """Send a raw message with rate-limit handling. Returns True on success."""
        if not self._enabled:
            return False

        with self._lock:
            # Enforce minimum interval between sends
            elapsed = time.time() - self._last_send
            if elapsed < self._MIN_INTERVAL:
                time.sleep(self._MIN_INTERVAL - elapsed)

            for attempt in range(3):
                try:
                    url = _BASE_URL.format(token=self.token)
                    resp = requests.post(url, json={
                        'chat_id': self.chat_id,
                        'text': text[:4096],
                        'parse_mode': parse_mode,
                        'disable_web_page_preview': True,
                    }, timeout=10)

                    if resp.status_code == 200:
                        self._last_send = time.time()
                        return True

                    if resp.status_code == 429:
                        # Rate limited — extract retry_after
                        try:
                            data = resp.json()
                            wait = data.get('parameters', {}).get('retry_after', 30)
                        except Exception:
                            wait = 30
                        # Cap wait at 60 seconds; skip message if too long
                        if wait > 60:
                            print(f"[Telegram] Rate limited for {wait}s — dropping message")
                            self._last_send = time.time()
                            return False
                        print(f"[Telegram] Rate limited, waiting {wait}s (attempt {attempt+1})")
                        time.sleep(wait)
                        continue

                    print(f"[Telegram] API error {resp.status_code}: {resp.text[:200]}")
                    return False

                except Exception as e:
                    print(f"[Telegram] Send error: {e}")
                    return False

            return False

    # ───────── high-level event methods ─────────

    def notify_new_project(self, project_id: int, title: str, client_email: str,
                           description: str = ''):
        """New project received from email."""
        desc_short = (description or '')[:300]
        self.send(
            f"{_ICONS['new_project']} <b>Новый проект #{project_id}</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Клиент:</b> {_esc(client_email)}\n"
            f"<b>Описание:</b>\n<i>{_esc(desc_short)}{'…' if len(description or '') > 300 else ''}</i>"
        )

    def notify_rejected(self, project_id: int, title: str, reason: str):
        """Project rejected by scam filter."""
        self.send(
            f"{_ICONS['rejected']} <b>Проект #{project_id} отклонён</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Причина:</b> {_esc(reason[:500])}"
        )

    def notify_analyzed(self, project_id: int, title: str, scam_score: float):
        """Project passed scam filter."""
        self.send(
            f"{_ICONS['analyzed']} <b>Проект #{project_id} проверен</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Scam-score:</b> {scam_score:.2f}  ✅ Пройден"
        )

    def notify_classified(self, project_id: int, title: str, complexity: str,
                          tech_stack: list, estimated_hours: float = 0):
        """Classification + estimation done."""
        stack_str = ', '.join(tech_stack) if tech_stack else '—'
        self.send(
            f"{_ICONS['classified']} <b>Проект #{project_id} классифицирован</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Сложность:</b> {complexity}\n"
            f"<b>Стек:</b> {_esc(stack_str)}\n"
            f"<b>Оценка:</b> {estimated_hours:.0f}ч"
        )

    def notify_estimation(self, project_id: int, title: str,
                          hours: float, price: float):
        """Estimation complete."""
        self.send(
            f"{_ICONS['estimation']} <b>Проект #{project_id} оценён</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Часы:</b> {hours:.0f}ч\n"
            f"<b>Цена:</b> ${price:.0f}"
        )

    def notify_offer_sent(self, project_id: int, title: str, price: float,
                          client_email: str):
        """Offer/proposal generated and queued for sending."""
        self.send(
            f"{_ICONS['offer_sent']} <b>Оффер отправлен — проект #{project_id}</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Цена:</b> ${price:.0f}\n"
            f"<b>Кому:</b> {_esc(client_email)}"
        )

    def notify_client_reply(self, project_id: int, title: str,
                            client_email: str, snippet: str = ''):
        """Client replied — project moved to NEGOTIATION."""
        snip = (snippet or '')[:200]
        self.send(
            f"{_ICONS['client_reply']} <b>Клиент ответил — проект #{project_id}</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Клиент:</b> {_esc(client_email)}\n"
            f"<b>Сообщение:</b>\n<i>{_esc(snip)}{'…' if len(snippet or '') > 200 else ''}</i>"
        )

    def notify_agreed(self, project_id: int, title: str, price: float):
        """Client agreed — deal closed."""
        self.send(
            f"{_ICONS['agreed']} <b>СДЕЛКА! Проект #{project_id}</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Цена:</b> ${price:.0f}\n\n"
            f"Переведите проект в FUNDED после получения оплаты."
        )

    def notify_escalate(self, project_id: int, title: str, reason: str = ''):
        """Negotiation needs human intervention."""
        self.send(
            f"{_ICONS['escalate']} <b>Нужно ваше участие — проект #{project_id}</b>\n\n"
            f"<b>Название:</b> {_esc(title)}\n"
            f"<b>Причина:</b> {_esc(reason or 'Достигнут лимит раундов переговоров')}\n\n"
            f"Откройте админ-панель и продолжите переговоры вручную."
        )

    def notify_error(self, component: str, error: str):
        """System error."""
        self.send(
            f"{_ICONS['error']} <b>Ошибка в {_esc(component)}</b>\n\n"
            f"<code>{_esc(error[:1000])}</code>"
        )

    def notify_system(self, message: str):
        """Generic system notification."""
        self.send(f"{_ICONS['system']} {message}")


# ── HTML escaping for Telegram ──
def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


# ── Singleton ──
_notifier = None

def get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
