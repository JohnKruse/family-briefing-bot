from __future__ import annotations

import base64
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

import requests


def send_telegram_messages(bot_token: str, chat_ids: Iterable[str], text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in chat_ids:
        payload = {"chat_id": str(chat_id), "text": text[:4096]}
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()


def send_email_via_gmail(
    gmail_service,
    recipients: Iterable[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    inline_images: dict[str, bytes] | None = None,
) -> None:
    recipients_list = [r.strip() for r in recipients if str(r).strip()]
    if not recipients_list:
        return
    if html_body and inline_images:
        msg = MIMEMultipart("related")
        msg_alt = MIMEMultipart("alternative")
        msg_alt.attach(MIMEText(body, "plain", "utf-8"))
        msg_alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(msg_alt)
        for cid, img_bytes in inline_images.items():
            image = MIMEImage(img_bytes)
            image.add_header("Content-ID", f"<{cid}>")
            image.add_header("Content-Disposition", "inline")
            msg.attach(image)
    else:
        subtype = "html" if html_body else "plain"
        payload = html_body if html_body else body
        msg = MIMEText(payload, subtype, "utf-8")

    msg["to"] = ", ".join(recipients_list)
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()
