import firebase_admin
from firebase_admin import credentials, auth
import os
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def initialize_firebase():
    """Initializes the Firebase Admin SDK."""
    if not firebase_admin._apps:
        try:
            if os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized successfully.")
            else:
                logger.warning(
                    f"Firebase credentials file not found at {settings.FIREBASE_CREDENTIALS_PATH}. "
                    "Firebase Admin features will not work until this file is provided."
                )
        except Exception as e:
            logger.error(f"Error initializing Firebase Admin SDK: {e}")

def verify_firebase_token(id_token: str):
    """Verifies a Firebase ID token and returns the decoded token payload."""
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        logger.error(f"Error verifying Firebase ID token: {e}")
        return None
