"""Sending a one-time code over WhatsApp, through apitxt.com.

The owner bought this gateway, which posts a pre-approved WhatsApp template
with the code as its single body parameter. Numbers are normalised to the
country-code form the gateway wants (``917908288829``) before they are stored
or sent, so a number typed with a +, with spaces, or without the country code
all land on the same account.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

#: India, where the app and its gateway both are.
DEFAULT_COUNTRY = "91"
SEND_TIMEOUT = 20.0


class WhatsAppError(RuntimeError):
    """The code could not be handed to the gateway."""


def normalise_mobile(raw: str) -> str | None:
    """``+91 79082 88829``, ``07908288829``, ``7908288829`` → ``917908288829``.

    Returns None when what is left cannot be a mobile number, so a caller can
    answer "that is not a number we can message" rather than send into space.
    """
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return None
    if len(digits) == 10:
        digits = DEFAULT_COUNTRY + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = DEFAULT_COUNTRY + digits[1:]
    elif digits.startswith("00"):
        digits = digits[2:]
    # 10 national digits plus a 1–3 digit country code.
    if not 11 <= len(digits) <= 15:
        return None
    return digits


def is_configured() -> bool:
    return bool(settings.APITXT_AUTHKEY and settings.APITXT_PROJECT_REF_ID)


async def send_otp_whatsapp(mobile: str, otp: str) -> None:
    """Hand one code to the gateway, or raise.

    The gateway answers 200 with a body that says what really happened, so the
    body is what is checked: a message counted as failed is a failure here too,
    rather than a code the user is told to wait for and never receives.
    """
    if not is_configured():
        raise WhatsAppError("WhatsApp OTP is not configured on the server.")

    payload = {
        "authkey": settings.APITXT_AUTHKEY,
        "template_name": settings.APITXT_TEMPLATE,
        "project_ref_id": settings.APITXT_PROJECT_REF_ID,
        "mobiles": mobile,
        "body_params": [otp],
    }

    try:
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
            res = await client.post(settings.APITXT_URL, json=payload)
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp OTP send failed for %s: %s", mobile[-4:], exc)
        raise WhatsAppError("Could not reach WhatsApp just now. Please try again.") from exc

    if res.status_code >= 400:
        logger.warning("WhatsApp OTP gateway returned %s: %s", res.status_code, res.text[:300])
        raise WhatsAppError("WhatsApp could not send the code. Please try again.")

    try:
        body = res.json()
    except ValueError:
        body = {}

    if int(body.get("sent") or 0) < 1 or int(body.get("failed") or 0) > 0:
        detail = ""
        for row in body.get("details") or []:
            detail = row.get("error") or ""
            if detail:
                break
        logger.warning("WhatsApp OTP not delivered to %s: %s", mobile[-4:], detail or body)
        raise WhatsAppError(
            "WhatsApp could not deliver the code to that number. "
            "Check the number has WhatsApp, or sign up with your email."
        )
