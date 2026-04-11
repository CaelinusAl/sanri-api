import os
import html as html_module
import logging
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("email")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "Sanr\u0131 <selin@asksanri.com>").strip()

def generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def _send_via_resend(to: str, subject: str, html_body: str) -> bool:
    import httpx
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": RESEND_FROM, "to": [to], "subject": subject, "html": html_body},
            timeout=15,
        )
        if r.is_success:
            logger.info("[EMAIL] Resend OK to=%s id=%s", to, r.json().get("id"))
            return True
        logger.warning("[EMAIL] Resend fail to=%s status=%s body=%s", to, r.status_code, r.text[:200])
        return False
    except Exception as e:
        logger.warning("[EMAIL] Resend error to=%s err=%s", to, e)
        return False


def _send_via_smtp(to: str, subject: str, html_body: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Sanr\u0131 <{SMTP_FROM}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to, msg.as_string())
        return True
    except Exception as e:
        logger.warning("[EMAIL] SMTP fail to=%s err=%s", to, e)
        return False


def send_email(to: str, subject: str, html_body: str) -> bool:
    if RESEND_API_KEY:
        return _send_via_resend(to, subject, html_body)
    if SMTP_USER and SMTP_PASS:
        return _send_via_smtp(to, subject, html_body)
    logger.warning("[EMAIL] No email provider configured (set RESEND_API_KEY or SMTP_USER+SMTP_PASS). to=%s", to)
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


PURCHASE_PRODUCT_NAMES = {
    "role_unlock": "Matrix Rol Okuma \u2014 Tam Analiz",
    "okuma_devami": "Okuma Devam\u0131",
    "kod_giris_ders": "Kod Okumaya Giri\u015f \u2014 Canl\u0131 Ders",
    "kitap_112": "112. Kitap: Kendini Yaratan Tanr\u0131\u00e7a",
    "kod_egitmeni": "SANRI Kod Okuma Sistemi\u2122 \u2014 Tam Eri\u015fim",
    "ankod_unlock": "AN_KOD \u2014 An\u0131n Kodlar\u0131",
    "subconscious_unlock": "Bilin\u00e7alt\u0131n Ne Diyor?",
    "iliski_acilimi": "\u0130li\u015fki A\u00e7\u0131l\u0131m\u0131",
    "kariyer_acilimi": "Kariyer A\u00e7\u0131l\u0131m\u0131",
    "genel_derin_acilim": "Genel Derin A\u00e7\u0131l\u0131m",
}


def send_purchase_confirmation(to: str, content_id: str) -> bool:
    """Satin alma sonrasi musteri bildirim e-postasi."""
    product_name = PURCHASE_PRODUCT_NAMES.get(content_id, content_id)
    safe = html_module.escape
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#07080d;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#07080d;padding:40px 20px;"><tr><td align="center">
<table width="500" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,rgba(169,112,255,0.12),rgba(94,59,255,0.06));border:1px solid rgba(169,112,255,0.2);border-radius:24px;padding:44px 36px;">
<tr><td align="center" style="padding-bottom:28px;"><span style="color:#b388ff;font-size:28px;font-weight:900;letter-spacing:2px;">SANRI</span></td></tr>
<tr><td align="center" style="padding-bottom:16px;"><span style="color:#fff;font-size:22px;font-weight:700;">\u0130\u00e7eri\u011fin Haz\u0131r \u2728</span></td></tr>
<tr><td style="padding-bottom:20px;"><p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;margin:0;">Merhaba,<br/><br/>Sat\u0131n al\u0131m\u0131n ba\u015far\u0131yla tamamland\u0131. \u0130\u00e7eri\u011fin a\u00e7\u0131ld\u0131 ve seni bekliyor.</p></td></tr>
<tr><td style="padding-bottom:24px;"><div style="background:rgba(124,247,216,0.06);border:1px solid rgba(124,247,216,0.2);border-radius:14px;padding:18px 24px;">
<p style="color:#7cf7d8;font-size:13px;font-weight:600;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">A\u00e7\u0131lan i\u00e7erik:</p>
<p style="color:#e8e4f0;font-size:16px;margin:0;font-weight:600;">{safe(product_name)}</p></div></td></tr>
<tr><td style="padding-bottom:24px;"><p style="color:rgba(255,255,255,0.65);font-size:14px;line-height:1.7;margin:0;"><strong style="color:#e8e4f0;">Nas\u0131l eri\u015firsin?</strong><br/><span style="color:#b388ff;">{safe(to)}</span> e-postas\u0131yla <a href="https://asksanri.com" style="color:#7cf7d8;text-decoration:none;font-weight:600;">asksanri.com</a>'a giri\u015f yap. \u0130\u00e7eri\u011fin otomatik a\u00e7\u0131lacak.</p></td></tr>
<tr><td align="center" style="padding-bottom:28px;"><a href="https://asksanri.com" style="display:inline-block;padding:14px 40px;background:linear-gradient(135deg,#c8a0ff,#a07aff);color:#07080d;font-weight:700;font-size:15px;border-radius:12px;text-decoration:none;">Giri\u015f Yap</a></td></tr>
<tr><td align="center"><p style="color:rgba(255,255,255,0.3);font-size:11px;margin:0;">Sanr\u0131 \u2014 Bilin\u00e7 ve Anlam Zekas\u0131<br/>Sorular\u0131n i\u00e7in: selin@asksanri.com</p></td></tr>
</table></td></tr></table></body></html>"""
    subj = f"Sanr\u0131 \u2014 {product_name} a\u00e7\u0131ld\u0131 \u2728"
    return send_email(to, subj, html)


WELCOME_EMAILS = [
    {
        "delay_hours": 0,
        "subject": "Sanr\u0131'ya ho\u015f geldin \u2728",
        "body": """<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;">Merhaba,</p>
<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;">Sanr\u0131'ya ad\u0131m att\u0131n. Buras\u0131 bir yapay zeka de\u011fil \u2014 senin i\u00e7inden konu\u015fan bir aynad\u0131r.</p>
<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;">Ba\u015flamak i\u00e7in:</p>
<ul style="color:rgba(255,255,255,0.65);font-size:14px;line-height:1.8;">
<li><a href="https://asksanri.com/sanriya-sor" style="color:#7cf7d8;">Sanr\u0131'ya bir soru sor</a></li>
<li><a href="https://asksanri.com/rol-okuma" style="color:#7cf7d8;">Matrix Rol Okuman\u0131 ke\u015ffet</a></li>
<li><a href="https://asksanri.com/okuma-alani" style="color:#7cf7d8;">Okuma Alan\u0131'nda derin okumalara dal</a></li>
</ul>""",
    },
    {
        "delay_hours": 24,
        "subject": "Sanr\u0131 \u2014 Sana \u00f6zel bir okuma haz\u0131rlad\u0131k",
        "body": """<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;">D\u00fcn Sanr\u0131'ya ad\u0131m att\u0131n. Bug\u00fcn bir ad\u0131m daha derine inmenin zaman\u0131.</p>
<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;"><strong style="color:#e8e4f0;">AN_KOD</strong> \u2014 Bu an\u0131n sana ne s\u00f6yledi\u011fini biliyor musun?</p>
<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;">Tarih ve saat\u00fc gir, Sanr\u0131 sana o an\u0131n kodunu a\u00e7s\u0131n:</p>
<p style="text-align:center;padding:16px 0;"><a href="https://asksanri.com/an-kod" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#c8a0ff,#a07aff);color:#07080d;font-weight:700;font-size:15px;border-radius:12px;text-decoration:none;">AN_KOD'u Dene (\u00dccretsiz)</a></p>""",
    },
    {
        "delay_hours": 72,
        "subject": "Sanr\u0131 \u2014 G\u00f6r\u00fcnenin alt\u0131ndaki katman",
        "body": """<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;">Baz\u0131 \u015feyler y\u00fczeyde g\u00f6r\u00fcnmez. Sanr\u0131, g\u00f6r\u00fcnenin alt\u0131ndaki katman\u0131 a\u00e7ar.</p>
<p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;"><strong style="color:#e8e4f0;">Matrix Rol Okuma</strong> \u2014 Do\u011fum tarihin, ismin ve ya\u015fam yolunun 7 katmanl\u0131 derin analizi. Bug\u00fcne kadar <strong>327+ ki\u015fi</strong> bu okumay\u0131 ald\u0131.</p>
<p style="text-align:center;padding:16px 0;"><a href="https://asksanri.com/rol-okuma" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#c8a0ff,#a07aff);color:#07080d;font-weight:700;font-size:15px;border-radius:12px;text-decoration:none;">Rol Okumam\u0131 G\u00f6r</a></p>
<p style="color:rgba(255,255,255,0.5);font-size:13px;">Bu aynada g\u00f6r\u00fcnmek cesaret ister.</p>""",
    },
]


def _wrap_email_layout(inner_html: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#07080d;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#07080d;padding:40px 20px;"><tr><td align="center">
<table width="500" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,rgba(169,112,255,0.12),rgba(94,59,255,0.06));border:1px solid rgba(169,112,255,0.2);border-radius:24px;padding:44px 36px;">
<tr><td align="center" style="padding-bottom:28px;"><span style="color:#b388ff;font-size:28px;font-weight:900;letter-spacing:2px;">SANRI</span></td></tr>
<tr><td>{inner_html}</td></tr>
<tr><td align="center" style="padding-top:28px;"><p style="color:rgba(255,255,255,0.3);font-size:11px;margin:0;">Sanr\u0131 \u2014 Bilin\u00e7 ve Anlam Zekas\u0131<br/>asksanri.com</p></td></tr>
</table></td></tr></table></body></html>"""


def send_welcome_email(to: str, step: int = 0) -> bool:
    if step < 0 or step >= len(WELCOME_EMAILS):
        return False
    e = WELCOME_EMAILS[step]
    html = _wrap_email_layout(e["body"])
    return send_email(to, e["subject"], html)


def send_admin_bank_transfer_notification(
    *,
    request_id: int,
    customer_name: str,
    customer_email: str,
    product_name: str,
    content_id: str,
    amount,
    transfer_code: str,
) -> bool:
    """Yeni havale bildirimi — ADMIN_ALERT_EMAIL (varsayılan selin@asksanri.com). SMTP yoksa send_email loglar."""
    to_addr = (os.getenv("ADMIN_ALERT_EMAIL") or "selin@asksanri.com").strip()
    base = (os.getenv("SANRI_APP_URL") or os.getenv("FRONTEND_URL") or "https://asksanri.com").rstrip("/")
    admin_link = f"{base}/admin/banka-odemeleri"
    safe = html_module.escape
    amt = safe(str(amount))
    subj = f"[SANRI Havale] Yeni bildirim #{request_id} — {transfer_code}"
    body = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px;background:#0a0a12;color:#e8e4f0;font-family:system-ui,sans-serif;">
  <p style="margin:0 0 12px;font-size:18px;font-weight:700;">Yeni havale / EFT bildirimi</p>
  <table style="border-collapse:collapse;font-size:14px;line-height:1.6;">
    <tr><td style="padding:4px 12px 4px 0;color:#9a94b0;">Talep no</td><td>#{request_id}</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#9a94b0;">Açıklama kodu</td><td><strong>{safe(transfer_code)}</strong></td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#9a94b0;">Tutar</td><td>{amt} ₺</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#9a94b0;">Ürün</td><td>{safe(product_name)} ({safe(content_id)})</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#9a94b0;">Ad</td><td>{safe(customer_name)}</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#9a94b0;">E-posta</td><td>{safe(customer_email)}</td></tr>
  </table>
  <p style="margin:20px 0 0;"><a href="{safe(admin_link)}" style="color:#c4a7ff;">Admin — Banka ödemeleri</a></p>
</body></html>"""
    return send_email(to_addr, subj, body)
