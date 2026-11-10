import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from functools import cache
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, email: Email) -> None: ...


class ConsoleMailer:
    def send(self, email: Email) -> None:
        print(f"--- Email to {email.to}: {email.subject}\n{email.body}\n---", flush=True)


class SmtpMailer:
    def __init__(self, host: str, port: int, username: str, password: str, sender: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender

    def send(self, email: Email) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


@cache
def get_mailer() -> Mailer:
    if settings.EMAIL_BACKEND == "smtp":
        return SmtpMailer(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD.get_secret_value(),
            settings.SMTP_FROM,
        )
    return ConsoleMailer()
