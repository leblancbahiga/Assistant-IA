"""Integration Gmail — Lecture, recherche, envoi via IMAP/SMTP.

Nécessite un mot de passe d'application Gmail (MFA requis).
Les credentials sont stockés dans le trousseau macOS (keyring).
"""

from __future__ import annotations

import email
import imaplib
import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "com.nuru.assistant"
KEYRING_GMAIL_USER = "gmail_user"
KEYRING_GMAIL_APP_PASSWORD = "gmail_app_password"


@dataclass
class GmailConfig:
    """Configuration Gmail."""
    email_address: str = ""
    use_keyring: bool = True
    imap_server: str = "imap.gmail.com"
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    max_results: int = 20


@dataclass
class EmailResult:
    """Résultat d'une opération email."""
    success: bool
    message: str = ""
    emails: list[dict] = field(default_factory=list)


@dataclass
class GmailIntegration:
    """Connecteur Gmail pour NURU.

    Usage :
        gmail = GmailIntegration("user@gmail.com")
        connected = gmail.connect()
        if connected:
            emails = gmail.search_inbox("from:boss")
            gmail.send_email("boss@co.com", "Sujet", "Message")
            gmail.disconnect()
    """

    config: GmailConfig = field(default_factory=GmailConfig)
    _imap: Optional[imaplib.IMAP4_SSL] = None

    def __post_init__(self):
        if self.config.email_address and self.config.use_keyring:
            self._load_credentials()

    def _load_credentials(self) -> None:
        """Charge les credentials depuis le trousseau."""
        try:
            import keyring
            stored_user = keyring.get_password(KEYRING_SERVICE, KEYRING_GMAIL_USER)
            stored_pass = keyring.get_password(KEYRING_SERVICE, KEYRING_GMAIL_APP_PASSWORD)
            if stored_user:
                self.config.email_address = stored_user
            if stored_pass:
                self._app_password = stored_pass
            else:
                self._app_password = ""
        except Exception:
            self._app_password = ""

    def _get_password(self) -> str:
        if not self._app_password:
            self._load_credentials()
        return self._app_password

    def connect(self) -> bool:
        """Connexion IMAP à Gmail."""
        password = self._get_password()
        if not self.config.email_address or not password:
            logger.error("Credentials Gmail manquants")
            return False

        try:
            self._imap = imaplib.IMAP4_SSL(self.config.imap_server)
            self._imap.login(self.config.email_address, password)
            self._imap.select("INBOX")
            logger.info(f"Gmail connecté: {self.config.email_address}")
            return True
        except Exception as e:
            logger.error(f"Erreur connexion Gmail: {e}")
            return False

    def disconnect(self) -> None:
        """Déconnexion IMAP."""
        if self._imap:
            try:
                self._imap.close()
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def search_inbox(self, query: str = "ALL") -> EmailResult:
        """Recherche dans la boîte de réception.

        Args:
            query: Requête IMAP (e.g., "FROM boss", "SUBJECT rapport", "UNSEEN")

        Returns:
            EmailResult avec la liste des emails
        """
        if not self._imap:
            return EmailResult(False, "Non connecté")

        try:
            status, messages = self._imap.search(None, query)
            if status != "OK":
                return EmailResult(False, f"Erreur recherche: {status}")

            msg_ids = messages[0].split() if messages[0] else []
            results = []
            for mid in msg_ids[-self.config.max_results:]:
                status, data = self._imap.fetch(mid, "(RFC822)")
                if status != "OK" or not data or not data[0]:
                    continue
                raw_email = data[0][1]
                if raw_email is None or isinstance(raw_email, int):
                    continue
                msg = email.message_from_bytes(raw_email)
                results.append({
                    "id": mid.decode(),
                    "from": msg.get("From", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "preview": self._get_preview(msg),
                    "unread": "UNSEEN" in str(data),
                })

            return EmailResult(
                success=True,
                message=f"{len(results)} emails trouvés",
                emails=results,
            )
        except Exception as e:
            return EmailResult(False, str(e))

    def send_email(self, to: str, subject: str, body: str) -> EmailResult:
        """Envoie un email via SMTP Gmail.

        Args:
            to: Destinataire
            subject: Sujet
            body: Corps du message (plain text)

        Returns:
            EmailResult
        """
        password = self._get_password()
        if not self.config.email_address or not password:
            return EmailResult(False, "Credentials manquants")

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.config.email_address
            msg["To"] = to

            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.email_address, password)
                server.send_message(msg)

            logger.info(f"Email envoyé à {to}: {subject}")
            return EmailResult(True, f"Email envoyé à {to}")
        except Exception as e:
            return EmailResult(False, str(e))

    def _get_preview(self, msg) -> str:
        """Extrait un aperçu du corps du message."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    text = part.get_payload(decode=True)
                    if text:
                        return text.decode("utf-8", errors="ignore")[:150]
        else:
            text = msg.get_payload(decode=True)
            if text:
                return text.decode("utf-8", errors="ignore")[:150]
        return ""

    def inbox_summary(self) -> str:
        """Résumé textuel de la boîte de réception."""
        result = self.search_inbox("UNSEEN")
        if not result.success:
            return f"Erreur: {result.message}"
        unread = len(result.emails)
        total_result = self.search_inbox("ALL")
        total = len(total_result.emails) if total_result.success else 0
        if unread > 0:
            previews = "\n".join(
                f"  - {e['from']}: {e['subject']}"
                for e in result.emails[:5]
            )
            return f"📬 {unread} non lus / {total} total\n{previews}"
        return f"📬 0 non lus / {total} total"
