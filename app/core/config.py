from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Newmeric Compass Backend"
    
    # MongoDB settings
    MONGODB_URL: str
    DATABASE_NAME: str = "newmericcompass"
    
    # Optional settings that might be useful later
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Environment variables are loaded from the .env file in development
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
