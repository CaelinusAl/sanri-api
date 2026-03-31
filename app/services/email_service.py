import os
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER

def generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))

def send_email(to: str, subject: str, html_body: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        print(f"[EMAIL] SMTP not configured. Code would be sent to {to}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Sanrı <{SMTP_FROM}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Send failed: {e}")
        return False

def create_verification_code(db: Session, user_id: int, email: str, code_type: str) -> str:
    """Create a 6-digit verification code, valid for 15 minutes. Invalidates previous codes."""
    db.execute(
        text("UPDATE verification_codes SET used = TRUE WHERE user_id = :uid AND type = :t AND used = FALSE"),
        {"uid": user_id, "t": code_type},
    )
    
    code = generate_code()
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    
    db.execute(
        text("""
            INSERT INTO verification_codes (user_id, email, code, type, expires_at)
            VALUES (:uid, :email, :code, :type, :expires_at)
        """),
        {"uid": user_id, "email": email, "code": code, "type": code_type, "expires_at": expires_at},
    )
    db.commit()
    return code

def verify_code(db: Session, email: str, code: str, code_type: str) -> dict | None:
    """Verify a code. Returns the verification_codes row if valid, None otherwise."""
    row = db.execute(
        text("""
            SELECT id, user_id, email, code, type, expires_at, used
            FROM verification_codes
            WHERE email = :email AND code = :code AND type = :type AND used = FALSE
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"email": email, "code": code, "type": code_type},
    ).mappings().first()
    
    if not row:
        return None
    
    if datetime.utcnow() > row["expires_at"]:
        return None
    
    db.execute(
        text("UPDATE verification_codes SET used = TRUE WHERE id = :id"),
        {"id": row["id"]},
    )
    db.commit()
    return dict(row)

def _email_template(code: str, title: str, message: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#07080d;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#07080d;padding:40px 20px;">
    <tr><td align="center">
      <table width="460" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,rgba(169,112,255,0.15),rgba(94,59,255,0.08));border:1px solid rgba(169,112,255,0.25);border-radius:24px;padding:40px 32px;">
        <tr><td align="center" style="padding-bottom:24px;">
          <span style="color:#b388ff;font-size:28px;font-weight:900;letter-spacing:2px;">SANRI</span>
        </td></tr>
        <tr><td align="center" style="padding-bottom:12px;">
          <span style="color:#ffffff;font-size:20px;font-weight:700;">{title}</span>
        </td></tr>
        <tr><td align="center" style="padding-bottom:28px;">
          <span style="color:rgba(255,255,255,0.7);font-size:14px;line-height:22px;">{message}</span>
        </td></tr>
        <tr><td align="center" style="padding-bottom:28px;">
          <div style="background:rgba(124,247,216,0.08);border:2px solid rgba(124,247,216,0.3);border-radius:16px;padding:20px 40px;display:inline-block;">
            <span style="color:#7cf7d8;font-size:36px;font-weight:900;letter-spacing:12px;">{code}</span>
          </div>
        </td></tr>
        <tr><td align="center" style="padding-bottom:8px;">
          <span style="color:rgba(255,255,255,0.45);font-size:12px;">Bu kod 15 dakika geçerlidir. / This code expires in 15 minutes.</span>
        </td></tr>
        <tr><td align="center">
          <span style="color:rgba(255,255,255,0.3);font-size:11px;">Sanrı — Bilinç ve Anlam Zekası</span>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

def send_verification_email(to: str, code: str) -> bool:
    html = _email_template(code, "E-posta Doğrulama", "Hesabını doğrulamak için aşağıdaki kodu gir.<br/>Enter the code below to verify your account.")
    return send_email(to, "Sanrı — Doğrulama Kodu", html)

def send_password_reset_email(to: str, code: str) -> bool:
    html = _email_template(code, "Şifre Sıfırlama", "Şifreni sıfırlamak için aşağıdaki kodu gir.<br/>Enter the code below to reset your password.")
    return send_email(to, "Sanrı — Şifre Sıfırlama Kodu", html)
