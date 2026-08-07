from fastapi import APIRouter

from app.api.routes import vastu
from app.api.routes import admin_rules
from app.api.routes import admin_dashboard

api_router = APIRouter()

api_router.include_router(vastu.router, prefix="/vastu", tags=["Vastu Engine"])
api_router.include_router(admin_rules.router, prefix="/admin/rules", tags=["Admin Rules"])
api_router.include_router(admin_dashboard.router, prefix="/admin", tags=["Admin Dashboard"])

@api_router.get("/health")
async def health_check():
    return {"status": "ok"}
