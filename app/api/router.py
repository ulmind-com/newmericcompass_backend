from fastapi import APIRouter

from app.api.routes import (
    admin_applinks,
    admin_billing,
    admin_categories,
    admin_dashboard,
    admin_padas,
    admin_rules,
    admin_submissions,
    admin_tips,
    admin_uploads,
    auth,
    billing,
    public,
    submissions,
    uploads,
    users,
    vastu,
)

api_router = APIRouter()

# ---- Public (app-facing) ----
api_router.include_router(public.router, tags=["Public"])
api_router.include_router(vastu.router, prefix="/vastu", tags=["Vastu Engine"])
api_router.include_router(submissions.router, prefix="/submissions", tags=["Submissions"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["Uploads"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])

# ---- Auth ----
api_router.include_router(auth.router, prefix="/auth", tags=["Admin Auth"])
api_router.include_router(users.router, prefix="/users", tags=["App Users"])

# ---- Admin ----
api_router.include_router(admin_dashboard.router, prefix="/admin", tags=["Admin Dashboard"])
api_router.include_router(admin_applinks.router, prefix="/admin/app", tags=["Admin App Links"])
api_router.include_router(admin_billing.router, prefix="/admin/billing", tags=["Admin Billing"])
api_router.include_router(admin_categories.router, prefix="/admin/categories", tags=["Admin Categories"])
api_router.include_router(admin_padas.router, prefix="/admin/padas", tags=["Admin Padas"])
api_router.include_router(admin_rules.router, prefix="/admin/rules", tags=["Admin Rules"])
api_router.include_router(admin_submissions.router, prefix="/admin/submissions", tags=["Admin Submissions"])
api_router.include_router(admin_tips.router, prefix="/admin/tips", tags=["Admin Tips"])
api_router.include_router(admin_uploads.router, prefix="/admin/uploads", tags=["Admin Uploads"])


@api_router.get("/health")
async def health_check():
    return {"status": "ok"}
