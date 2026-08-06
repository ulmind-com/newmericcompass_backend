from fastapi import APIRouter

api_router = APIRouter()

# Example of including a router from another file:
# from app.api.routes import items
# api_router.include_router(items.router, prefix="/items", tags=["items"])

@api_router.get("/health")
async def health_check():
    return {"status": "ok"}
