import cloudinary
import cloudinary.uploader
import cloudinary.api
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def configure_cloudinary():
    """Configure Cloudinary with credentials from settings."""
    if not all([settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET]):
        logger.warning("Cloudinary credentials are not fully set in environment variables.")
        return False
        
    cloudinary.config( 
        cloud_name = settings.CLOUDINARY_CLOUD_NAME, 
        api_key = settings.CLOUDINARY_API_KEY, 
        api_secret = settings.CLOUDINARY_API_SECRET,
        secure = True
    )
    logger.info("Cloudinary configured successfully.")
    return True

async def upload_image(file_content: bytes, filename: str, folder: str = "newmericcompass"):
    """
    Upload an image to Cloudinary.
    
    Args:
        file_content: The raw bytes of the image file.
        filename: The original name of the file (can be used for public_id).
        folder: The folder in Cloudinary to store the image.
        
    Returns:
        The URL of the uploaded image, or None if upload failed.
    """
    try:
        # We run the upload synchronously as Cloudinary SDK isn't fully async
        # For a truly async approach, we could use run_in_executor
        response = cloudinary.uploader.upload(
            file_content,
            folder=folder,
            resource_type="auto"
        )
        return response.get("secure_url")
    except Exception as e:
        logger.error(f"Error uploading to Cloudinary: {e}")
        return None
