import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# Include the main router
app.include_router(api_router, prefix="/api")

@app.get("/ping", tags=["System"])
async def ping():
    return {"ping": "pong!"}
