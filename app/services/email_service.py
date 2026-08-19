"""Transactional email — Resend delivery + the branded Newmeric Compass templates.

Every mail we send is built here so the look stays in one place. The palette is
the app's own (`src/theme/theme.ts`): deep emerald on warm paper (#FFFDF1) with
gold as the single accent.

Email clients are not browsers: the markup is table-based with inline styles,
no flex/grid, no SVG, no web fonts (Georgia/serif + system sans only), and every
mail ships a plain-text part for clients that refuse HTML.
"""

from datetime import datetime, timezone

import resend

from app.core.config import settings

if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY

# --- brand tokens (mirrors app/src/theme/theme.ts) --------------------------
EMERALD = "#2E9E5B"
EMERALD_DARK = "#1B7A45"
EMERALD_DEEP = "#126035"
GOLD = "#C9962B"
PAPER = "#FFFDF1"
INK = "#1C2A22"
MUTED = "#5F7268"
FAINT = "#9AAAA0"
BORDER = "#E4E7DA"
CARD = "#FFFFFF"
BACKDROP = "#EFF4EC"

SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"
SERIF = "Georgia, 'Times New Roman', Times, serif"

APP_NAME = "Newmeric Compass"

def _logo_url() -> str:
    """Absolute URL of the N5 shree-chakra logo — email clients cannot read local files."""
    if settings.EMAIL_LOGO_URL:
        return settings.EMAIL_LOGO_URL
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/static/email/logo.png"

# Per-purpose copy. Keeping it in one dict makes a new mail a four-line change.
_COPY = {
    "verify": {
        "subject": "{otp} is your Newmeric Compass verification code",
        "eyebrow": "Email verification",
        "heading": "Verify your email",
        "lead": "Welcome to {app}. Use the code below to confirm this email address and finish setting up your account.",
        "label": "Your verification code",
        "note": "If you didn’t start a sign-up on {app}, you can safely ignore this email — no account will be created.",
    },
    "reset": {
        "subject": "{otp} is your Newmeric Compass password reset code",
        "eyebrow": "Password reset",
        "heading": "Reset your password",
        "lead": "We received a request to reset the password for your {app} account. Use the code below to continue.",
        "label": "Your password reset code",
        "note": "If you didn’t request a password reset, ignore this email — your current password stays unchanged.",
    },
}


def _greeting(name: str | None) -> str:
    name = (name or "").strip()
    return f"Namaste, {name}" if name else "Namaste"


def _otp_html(otp: str, name: str | None, purpose: str, minutes: int) -> str:
    c = _COPY.get(purpose, _COPY["verify"])
    year = datetime.now(timezone.utc).year
    lead = c["lead"].format(app=APP_NAME)
    note = c["note"].format(app=APP_NAME)
    # Shown as the inbox snippet next to the subject, then hidden in the body.
    preheader = f"{otp} — expires in {minutes} minutes."
    logo = _logo_url()

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="color-scheme" content="light" />
<meta name="supported-color-schemes" content="light" />
<title>{c['heading']} · {APP_NAME}</title>
<style type="text/css">
  body {{ margin:0 !important; padding:0 !important; width:100% !important; }}
  img {{ border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; }}
  table {{ border-collapse:collapse !important; }}
  a {{ color:{EMERALD_DARK}; }}
  @media only screen and (max-width:620px) {{
    .wrap {{ width:100% !important; }}
    .pad {{ padding-left:24px !important; padding-right:24px !important; }}
    .code {{ font-size:34px !important; letter-spacing:8px !important; }}
    .title {{ font-size:26px !important; }}
  }}
</style>
</head>
<body style="margin:0; padding:0; background-color:{BACKDROP};">
  <div style="display:none; font-size:1px; color:{BACKDROP}; line-height:1px; max-height:0; max-width:0; opacity:0; overflow:hidden;">{preheader}</div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{BACKDROP};">
    <tr>
      <td align="center" style="padding:32px 12px 40px 12px;">

        <table role="presentation" class="wrap" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px; max-width:600px;">

          <!-- brand header -->
          <tr>
            <td align="center" bgcolor="{EMERALD_DEEP}" style="background-color:{EMERALD_DEEP}; border-radius:20px 20px 0 0; padding:34px 24px 28px 24px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="padding:0;">
                    <img src="{logo}" width="92" height="92" alt="{APP_NAME}"
                         style="display:block; width:92px; height:92px; border:2px solid {GOLD}; border-radius:50%;
                                background-color:{EMERALD_DEEP}; outline:none; text-decoration:none;" />
                  </td>
                </tr>
              </table>
              <div style="font-family:{SANS}; font-size:17px; line-height:24px; color:#FFFFFF; font-weight:bold; letter-spacing:3px; padding-top:16px; text-transform:uppercase;">
                Newmeric&nbsp;Compass
              </div>
              <div style="font-family:{SANS}; font-size:11px; line-height:16px; color:{GOLD}; letter-spacing:2px; padding-top:6px; text-transform:uppercase;">
                Vastu &nbsp;&middot;&nbsp; 32 Pada &nbsp;&middot;&nbsp; N5 Chart
              </div>
            </td>
          </tr>

          <!-- gold hairline -->
          <tr><td height="3" bgcolor="{GOLD}" style="height:3px; line-height:3px; font-size:0; background-color:{GOLD};">&nbsp;</td></tr>

          <!-- card -->
          <tr>
            <td bgcolor="{CARD}" class="pad" style="background-color:{CARD}; padding:38px 44px 8px 44px;">
              <div style="font-family:{SANS}; font-size:11px; line-height:16px; letter-spacing:2px; text-transform:uppercase; color:{EMERALD}; font-weight:bold;">
                {c['eyebrow']}
              </div>
              <h1 class="title" style="margin:10px 0 0 0; font-family:{SERIF}; font-size:30px; line-height:38px; color:{INK}; font-weight:normal;">
                {c['heading']}
              </h1>
              <p style="margin:18px 0 0 0; font-family:{SANS}; font-size:15px; line-height:25px; color:{INK};">
                {_greeting(name)},
              </p>
              <p style="margin:10px 0 0 0; font-family:{SANS}; font-size:15px; line-height:25px; color:{MUTED};">
                {lead}
              </p>
            </td>
          </tr>

          <!-- the code -->
          <tr>
            <td bgcolor="{CARD}" class="pad" style="background-color:{CARD}; padding:26px 44px 6px 44px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background-color:{PAPER}; border:1px solid {BORDER}; border-radius:16px;">
                <tr>
                  <td align="center" style="padding:26px 16px 24px 16px;">
                    <div style="font-family:{SANS}; font-size:11px; line-height:16px; letter-spacing:2px; text-transform:uppercase; color:{MUTED};">
                      {c['label']}
                    </div>
                    <div class="code" style="font-family:{SANS}; font-size:42px; line-height:56px; letter-spacing:12px; font-weight:bold; color:{EMERALD_DEEP}; padding:8px 0 0 8px;">
                      {otp}
                    </div>
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;">
                      <tr>
                        <td style="background-color:#FFFFFF; border:1px solid {BORDER}; border-radius:999px; padding:7px 16px;
                                   font-family:{SANS}; font-size:12px; line-height:16px; color:{MUTED};">
                          Expires in {minutes} minutes
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ornament -->
          <tr>
            <td bgcolor="{CARD}" align="center" style="background-color:{CARD}; padding:26px 44px 0 44px;">
              <div style="font-family:{SERIF}; font-size:13px; line-height:16px; color:{GOLD}; letter-spacing:6px;">&#10022; &#10022; &#10022;</div>
            </td>
          </tr>

          <!-- security note -->
          <tr>
            <td bgcolor="{CARD}" class="pad" style="background-color:{CARD}; padding:22px 44px 36px 44px;">
              <p style="margin:0; font-family:{SANS}; font-size:13px; line-height:22px; color:{MUTED};">
                For your safety, never share this code with anyone. Our team will never ask you for it.
              </p>
              <p style="margin:10px 0 0 0; font-family:{SANS}; font-size:13px; line-height:22px; color:{FAINT};">
                {note}
              </p>
            </td>
          </tr>

          <!-- footer -->
          <tr>
            <td bgcolor="{PAPER}" class="pad" align="center" style="background-color:{PAPER}; border-top:1px solid {BORDER}; border-radius:0 0 20px 20px; padding:26px 44px 30px 44px;">
              <div style="font-family:{SERIF}; font-size:15px; line-height:22px; color:{EMERALD_DEEP};">
                {APP_NAME}
              </div>
              <div style="font-family:{SANS}; font-size:12px; line-height:20px; color:{MUTED}; padding-top:4px;">
                Vastu guidance from the N5 32-pada chart, in your pocket.
              </div>
              <div style="font-family:{SANS}; font-size:11px; line-height:18px; color:{FAINT}; padding-top:12px;">
                This is an automated message — please don’t reply.<br />
                &copy; {year} {APP_NAME}. All rights reserved.
              </div>
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""


def _otp_text(otp: str, name: str | None, purpose: str, minutes: int) -> str:
    c = _COPY.get(purpose, _COPY["verify"])
    return "\n".join([
        f"{_greeting(name)},",
        "",
        c["lead"].format(app=APP_NAME),
        "",
        f"{c['label']}: {otp}",
        f"This code expires in {minutes} minutes.",
        "",
        "Never share this code with anyone — our team will never ask you for it.",
        c["note"].format(app=APP_NAME),
        "",
        f"— {APP_NAME}",
    ])


def send_otp_email(to: str, otp: str, name: str | None = "", purpose: str = "verify", minutes: int = 10) -> bool:
    """Send the branded OTP mail. Never raises — a mail failure must not 500 the API."""
    if not (settings.RESEND_API_KEY and settings.MAIL_ADDRESS):
        print(f"[email] RESEND_API_KEY/MAIL_ADDRESS not set — OTP for {to}: {otp}")
        return False

    c = _COPY.get(purpose, _COPY["verify"])
    try:
        resend.Emails.send({
            "from": f"{APP_NAME} <{settings.MAIL_ADDRESS}>",
            "to": to,
            "subject": c["subject"].format(otp=otp),
            "html": _otp_html(otp, name, purpose, minutes),
            "text": _otp_text(otp, name, purpose, minutes),
        })
        return True
    except Exception as e:  # noqa: BLE001 - delivery is best-effort
        print(f"Failed to send email: {e}")
        return False
