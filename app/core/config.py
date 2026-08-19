from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Newmeric Compass Backend"
    
    # MongoDB settings
    MONGODB_URL: str
    DATABASE_NAME: str = "newmericcompass"
    
    # Cloudinary settings
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None
    
    # Optional settings that might be useful later
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Firebase
    FIREBASE_CREDENTIALS_PATH: Optional[str] = "firebase-credentials.json"
    
    # Resend Email Verification
    RESEND_API_KEY: Optional[str] = None
    MAIL_ADDRESS: Optional[str] = None
    # Logo shown in transactional emails. Defaults to the copy this API serves
    # at /static/email/logo.png; set this to a CDN URL to override.
    EMAIL_LOGO_URL: Optional[str] = None
    
    # Acharya the app offers to call for a treatment consultation.
    ACHARYA_NAME: str = "N5 Acharya"
    ACHARYA_PHONE: Optional[str] = None
    ACHARYA_WHATSAPP: Optional[str] = None

    # Razorpay. Both come from the environment; the secret is never committed.
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None
    # Where this API is reachable from a phone - used to build the checkout URL.
    PUBLIC_BASE_URL: str = "https://newmericcompass-backend.onrender.com"

    # Environment variables are loaded from the .env file in development
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
