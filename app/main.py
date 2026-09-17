import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, get_database
from app.api.router import api_router
from app.core.logger import setup_logging
from app.db.seed import ensure_seed_data
from app.services.cloudinary_service import configure_cloudinary

# Configure professional logging
setup_logging()

logger = logging.getLogger(__name__)

from app.core.firebase import initialize_firebase

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize services
    setup_logging()
    configure_cloudinary()
    initialize_firebase()
    
    # Connect to MongoDB
    await connect_to_mongo()
    try:
        await ensure_seed_data(get_database())
    except Exception as exc:  # never let seeding block startup
        logger.error("Auto-seed failed: %s", exc)
    yield
    # Shutdown actions
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update this to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Brand assets that must be reachable by absolute URL (email clients fetch these).
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include the main router
app.include_router(api_router, prefix="/api")

@app.get("/ping", tags=["System"])
async def ping():
    return {"ping": "pong!"}


# The domain this service answers on is also the domain the Razorpay checkout
# page is served from, which means a payment gateway reviewer will open its root
# by hand. An API that answers 404 there reads as a dead site, so the root is a
# real page: who is collecting the money, what is being sold, and where the
# policies are.
_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Newmeric Compass — Secure Payments</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 40px 20px 64px;
    background: #FFFDF1; color: #2C1B11;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
  }}
  .wrap {{ max-width: 720px; margin: 0 auto; }}
  header {{
    background: linear-gradient(135deg, #B1510B, #833501 60%, #5E2601);
    color: #fff; border-radius: 20px; padding: 34px 28px; text-align: center;
  }}
  header h1 {{ margin: 0; font-size: 26px; letter-spacing: -0.2px; }}
  header p {{ margin: 8px 0 0; opacity: .9; font-size: 15px; }}
  .card {{
    background: #fff; border: 1px solid #EAE0D7; border-radius: 16px;
    padding: 24px 26px; margin-top: 20px;
  }}
  h2 {{ font-size: 17px; margin: 0 0 12px; color: #501E02; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li {{ margin: 6px 0; }}
  .note {{
    background: #FAF2EB; border-left: 3px solid #C9962B;
    border-radius: 10px; padding: 14px 16px; margin-top: 18px; font-size: 14.5px;
  }}
  .rows {{ margin: 0; }}
  .rows div {{ padding: 10px 0; border-top: 1px solid #F0E7DE; }}
  .rows div:first-child {{ border-top: 0; }}
  .rows span {{ display: block; font-size: 12px; text-transform: uppercase;
    letter-spacing: .6px; color: #786154; }}
  a {{ color: #B1510B; }}
  .links {{ display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 4px; }}
  footer {{ text-align: center; color: #786154; font-size: 13px; margin-top: 26px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Newmeric Compass</h1>
    <p>Secure payments for the Newmeric Compass app</p>
  </header>

  <div class="card">
    <h2>What this domain does</h2>
    <p style="margin:0">This domain serves the secure checkout page used by the
    Newmeric Compass Android app. When a customer buys access inside the app,
    the Razorpay payment window opens from here. Card, UPI and banking details
    are handled entirely by Razorpay and are never seen or stored by us.</p>
    <div class="note">The app itself is on Google Play:
      <a href="{play_url}" target="_blank" rel="noopener">Newmeric Compass</a>.
      For everything else, visit <a href="{site_url}" target="_blank" rel="noopener">www.newmericcompass.in</a>.
    </div>
  </div>

  <div class="card">
    <h2>What is sold</h2>
    <ul>
      <li>16 Zone Analysis — zone-by-zone Vastu readings for a placement</li>
      <li>7D Nexus — the seven-dimension reading of a direction</li>
      <li>Integrated Vastu Space &amp; Environment Analysis</li>
      <li>Placement submissions reviewed by the consultant</li>
    </ul>
    <div class="note">These are digital reading sections inside the app. Prices
    are shown in Indian Rupees on the purchase screen before payment and include
    applicable taxes. Payments are one-time — nothing renews automatically.</div>
  </div>

  <div class="card">
    <h2>Merchant details</h2>
    <div class="rows">
      <div><span>Business</span>Newmeric Compass — Pannkaj Kabiraj</div>
      <div><span>Address</span>Bokajan, Karbi-Anglong, Assam 782480, India</div>
      <div><span>Email</span><a href="mailto:{email}">{email}</a></div>
      <div><span>Website</span><a href="{site_url}" target="_blank" rel="noopener">www.newmericcompass.in</a></div>
    </div>
  </div>

  <div class="card">
    <h2>Policies</h2>
    <div class="links">
      <a href="{site_url}/terms" target="_blank" rel="noopener">Terms of Service</a>
      <a href="{site_url}/refund" target="_blank" rel="noopener">Refund &amp; Cancellation</a>
      <a href="{site_url}/privacy" target="_blank" rel="noopener">Privacy Policy</a>
      <a href="{site_url}/contact" target="_blank" rel="noopener">Contact Us</a>
    </div>
  </div>

  <footer>&copy; Newmeric Compass</footer>
</div>
</body>
</html>"""

_SITE_URL = "https://www.newmericcompass.in"
_PLAY_URL = "https://play.google.com/store/apps/details?id=com.ulmind.newmericcompass"
_MERCHANT_EMAIL = "newmericcompass@gmail.com"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing():
    return HTMLResponse(
        _LANDING_HTML.format(
            site_url=_SITE_URL,
            play_url=_PLAY_URL,
            email=_MERCHANT_EMAIL,
        )
    )
