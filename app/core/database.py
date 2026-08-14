from motor.motor_asyncio import AsyncIOMotorClient
import logging
from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None

db = Database()

async def connect_to_mongo():
    logger.info("Connecting to MongoDB...")
    try:
        db.client = AsyncIOMotorClient(settings.MONGODB_URL)
        # Verify connection
        await db.client.admin.command('ping')
        logger.info("Successfully connected to MongoDB Atlas!")
        # Ensure indexes for production performance
        await _ensure_indexes()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise e

async def _ensure_indexes():
    """Create indexes that are critical for production performance."""
    try:
        database = db.client[settings.DATABASE_NAME]
        await database.push_tokens.create_index("token", unique=True)
        await database.push_tokens.create_index("is_active")
        logger.info("Database indexes ensured.")
    except Exception as e:
        logger.warning(f"Index creation warning (safe to ignore on re-runs): {e}")

async def close_mongo_connection():
    logger.info("Closing MongoDB connection...")
    if db.client:
        db.client.close()
        logger.info("MongoDB connection closed.")

def get_database():
    """Dependency to get the database instance."""
    if db.client is None:
        raise Exception("Database client not initialized")
    return db.client[settings.DATABASE_NAME]
