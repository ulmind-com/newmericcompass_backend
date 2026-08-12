"""App-facing billing: what is for sale, what this user has, and paying for it.

The money path is deliberately one-way: creating an order records nothing that
counts as revenue. A payment is only written to `payments`, and access only
granted, once Razorpay's signature verifies. A user who opens the checkout and
closes it leaves an abandoned order behind and nothing else.
"""

import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_database
from app.core.security import TokenData, get_current_user
from app.domain import billing as bl
from app.schemas.billing import (
    MyAccessResponse,
    OrderCreate,
    OrderResponse,
    PaymentVerify,
    PlanResponse,
)
from app.schemas.common import now_utc, serialize_docs
from app.services import razorpay_service as rzp

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/plans", response_model=list[PlanResponse], summary="Plans on sale")
async def list_plans(feature: Optional[str] = None, db: AsyncIOMotorDatabase = Depends(get_database)):
    query: dict = {"is_active": True}
    if feature:
        query["feature"] = feature
    cursor = db[bl.PLANS].find(query).sort([("feature", 1), ("order", 1), ("amount", 1)])
    return serialize_docs(await cursor.to_list(length=100))


@router.get("/me", response_model=MyAccessResponse, summary="What this user has unlocked")
async def my_access(
    current: TokenData = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    email = bl.normalize_email(current.email)
    return MyAccessResponse(email=email, features=await bl.access_map(db, email))


@router.post("/order", response_model=OrderResponse, summary="Start a payment")
async def create_order(
    payload: OrderCreate,
    current: TokenData = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if not rzp.is_configured():
        raise HTTPException(status_code=503, detail="Payments are not configured yet.")

    plan = await db[bl.PLANS].find_one({"slug": payload.plan_slug, "is_active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="That plan is not available.")
    if plan["amount"] <= 0:
        raise HTTPException(status_code=400, detail="This plan is free; no payment is needed.")

    email = bl.normalize_email(current.email)
    user = await db.users.find_one({"email": email}) or {}

    try:
        order = await rzp.create_order(
            amount=plan["amount"],
            currency=plan.get("currency", "INR"),
            receipt=f"{plan['slug']}-{ObjectId()}",
            notes={"email": email, "plan": plan["slug"], "feature": plan["feature"]},
        )
    except rzp.RazorpayError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # An in-flight order, not revenue. It exists so verify can trust the amount
    # and plan rather than anything the client sends back.
    await db[bl.PAYMENT_ORDERS].update_one(
        {"razorpay_order_id": order["id"]},
        {"$set": {
            "razorpay_order_id": order["id"],
            "user_email": email,
            "user_name": user.get("name"),
            "user_contact": user.get("whatsapp") or user.get("phone"),
            "plan_slug": plan["slug"],
            "plan_name": plan["name"],
            "feature": plan["feature"],
            "kind": plan["kind"],
            "amount": plan["amount"],
            "currency": plan.get("currency", "INR"),
            "duration_days": plan.get("duration_days"),
            "submission_quota": plan.get("submission_quota"),
            "status": "created",
            "created_at": now_utc(),
        }},
        upsert=True,
    )

    return OrderResponse(
        order_id=order["id"],
        amount=plan["amount"],
        currency=plan.get("currency", "INR"),
        key_id=settings.RAZORPAY_KEY_ID or "",
        plan_slug=plan["slug"],
        plan_name=plan["name"],
        feature=plan["feature"],
        checkout_url=f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/billing/checkout/{order['id']}",
        prefill_name=user.get("name"),
        prefill_email=email,
        prefill_contact=user.get("whatsapp") or user.get("phone"),
    )


@router.post("/verify", summary="Confirm a payment and unlock the feature")
async def verify_payment(
    payload: PaymentVerify,
    current: TokenData = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    order = await db[bl.PAYMENT_ORDERS].find_one({"razorpay_order_id": payload.razorpay_order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Unknown order.")

    email = bl.normalize_email(current.email)
    if order["user_email"] != email:
        raise HTTPException(status_code=403, detail="This order belongs to another account.")

    if not rzp.verify_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        logger.warning("Rejected payment with a bad signature for order %s", payload.razorpay_order_id)
        raise HTTPException(status_code=400, detail="Payment could not be verified.")

    # Replaying the same payment must not grant a second period.
    existing = await db[bl.PAYMENTS].find_one({"razorpay_payment_id": payload.razorpay_payment_id})
    if existing:
        return {"ok": True, "already_recorded": True, "features": [f.model_dump() for f in await bl.access_map(db, email)]}

    raw = await rzp.fetch_payment(payload.razorpay_payment_id)
    doc = {
        "user_email": email,
        "user_name": order.get("user_name"),
        "user_contact": order.get("user_contact"),
        "plan_slug": order["plan_slug"],
        "plan_name": order["plan_name"],
        "feature": order["feature"],
        "kind": order["kind"],
        "amount": order["amount"],
        "currency": order.get("currency", "INR"),
        "razorpay_order_id": payload.razorpay_order_id,
        "razorpay_payment_id": payload.razorpay_payment_id,
        "razorpay_signature": payload.razorpay_signature,
        "method": (raw or {}).get("method"),
        "status": "paid",
        "razorpay_raw": raw,
        "created_at": now_utc(),
    }
    result = await db[bl.PAYMENTS].insert_one(doc)

    await bl.grant(
        db,
        email=email,
        feature=order["feature"],
        source="payment",
        plan_slug=order["plan_slug"],
        plan_name=order["plan_name"],
        duration_days=order.get("duration_days"),
        submission_quota=order.get("submission_quota"),
        payment_id=str(result.inserted_id),
    )
    await db[bl.PAYMENT_ORDERS].update_one(
        {"razorpay_order_id": payload.razorpay_order_id},
        {"$set": {"status": "paid", "paid_at": now_utc()}},
    )

    return {"ok": True, "features": [f.model_dump() for f in await bl.access_map(db, email)]}


# The app has no native Razorpay module (it runs in Expo Go), so checkout is the
# hosted widget in a WebView. This page is what that WebView loads; it reports
# the result back through postMessage and the app then calls /verify.
_CHECKOUT_HTML = """<!doctype html>
<html><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
<title>Secure payment</title>
<style>
  html,body{{margin:0;height:100%;background:#F6EFE0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
  .wrap{{height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:14px;color:#7A5A20}}
  .dot{{width:38px;height:38px;border-radius:50%;border:3px solid #F0DFC0;border-top-color:#FF6A00;animation:s .9s linear infinite}}
  @keyframes s{{to{{transform:rotate(360deg)}}}}
</style></head>
<body><div class="wrap"><div class="dot"></div><div>Opening secure payment…</div></div>
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
  var send = function (msg) {{
    if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(msg));
  }};
  var rzp = new Razorpay({{
    key: "{key_id}",
    order_id: "{order_id}",
    amount: {amount},
    currency: "{currency}",
    name: "Newmeric Compass",
    description: {plan_name!r},
    prefill: {{ name: {name!r}, email: {email!r}, contact: {contact!r} }},
    theme: {{ color: "#FF6A00" }},
    modal: {{ ondismiss: function () {{ send({{ status: "cancelled" }}); }} }},
    handler: function (r) {{
      send({{
        status: "success",
        razorpay_order_id: r.razorpay_order_id,
        razorpay_payment_id: r.razorpay_payment_id,
        razorpay_signature: r.razorpay_signature
      }});
    }}
  }});
  rzp.on('payment.failed', function (r) {{
    send({{ status: "failed", reason: (r.error && r.error.description) || "Payment failed" }});
  }});
  rzp.open();
</script></body></html>"""


@router.get("/checkout/{order_id}", response_class=HTMLResponse, summary="Hosted checkout page")
async def checkout_page(order_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    order = await db[bl.PAYMENT_ORDERS].find_one({"razorpay_order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Unknown order.")
    return HTMLResponse(_CHECKOUT_HTML.format(
        key_id=settings.RAZORPAY_KEY_ID or "",
        order_id=order_id,
        amount=order["amount"],
        currency=order.get("currency", "INR"),
        plan_name=order.get("plan_name") or "Newmeric Compass",
        name=order.get("user_name") or "",
        email=order.get("user_email") or "",
        contact=order.get("user_contact") or "",
    ))
