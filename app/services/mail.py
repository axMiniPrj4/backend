"""SMTP 메일 발송 — SMTP_HOST 미설정 시 no-op(False)."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(*, to: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    """성공 시 True. 메일 미설정·발송 실패 시 False (호출부에서 UX 분기)."""
    if not settings.mail_enabled:
        logger.info("mail skipped (SMTP_HOST empty): to=%s subject=%s", to, subject)
        return False

    from_addr = (settings.smtp_from or settings.smtp_user or "noreply@localhost").strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("mail sent to=%s subject=%s", to, subject)
        return True
    except Exception:
        logger.exception("mail send failed to=%s subject=%s", to, subject)
        return False


def send_find_login_id_email(*, to: str, login_id: str) -> bool:
    subject = f"[{settings.app_name}] 아이디 안내"
    text = (
        f"안녕하세요, {settings.app_name} 입니다.\n\n"
        f"요청하신 계정의 아이디는 다음과 같습니다.\n\n"
        f"  아이디: {login_id}\n\n"
        f"본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.\n"
    )
    html = (
        f"<p>안녕하세요, <strong>{settings.app_name}</strong> 입니다.</p>"
        f"<p>요청하신 계정의 아이디는 <strong>{login_id}</strong> 입니다.</p>"
        f"<p style='color:#666'>본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.</p>"
    )
    return send_email(to=to, subject=subject, text_body=text, html_body=html)


def send_password_reset_email(*, to: str, reset_url: str, minutes: int) -> bool:
    subject = f"[{settings.app_name}] 비밀번호 재설정"
    text = (
        f"안녕하세요, {settings.app_name} 입니다.\n\n"
        f"비밀번호 재설정을 요청하셨습니다. 아래 링크에서 {minutes}분 안에 새 비밀번호를 설정해 주세요.\n\n"
        f"{reset_url}\n\n"
        f"본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.\n"
    )
    html = (
        f"<p>안녕하세요, <strong>{settings.app_name}</strong> 입니다.</p>"
        f"<p>비밀번호 재설정을 요청하셨습니다. "
        f"<a href='{reset_url}'>여기</a>를 눌러 {minutes}분 안에 새 비밀번호를 설정해 주세요.</p>"
        f"<p style='word-break:break-all;color:#666'>{reset_url}</p>"
        f"<p style='color:#666'>본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.</p>"
    )
    return send_email(to=to, subject=subject, text_body=text, html_body=html)


def send_password_changed_email(*, to: str) -> bool:
    subject = f"[{settings.app_name}] 비밀번호가 변경되었습니다"
    text = (
        f"안녕하세요, {settings.app_name} 입니다.\n\n"
        f"계정 비밀번호가 변경되었습니다. 본인이 아니라면 즉시 고객센터로 문의해 주세요.\n"
    )
    return send_email(to=to, subject=subject, text_body=text)
