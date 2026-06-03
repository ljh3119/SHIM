from fastapi import APIRouter
from . import dashboard, users, leaves, holidays, settings, audit

page_router = APIRouter(prefix="/admin", tags=["admin_pages"])
api_router = APIRouter(prefix="/api/admin", tags=["admin_api"])

# Include page routers from sub-modules
page_router.include_router(dashboard.page_router)
page_router.include_router(users.page_router)
page_router.include_router(leaves.page_router)
page_router.include_router(holidays.page_router)
page_router.include_router(settings.page_router)
page_router.include_router(audit.page_router)

# Include API routers from sub-modules
api_router.include_router(dashboard.api_router)
api_router.include_router(users.api_router)
api_router.include_router(leaves.api_router)
api_router.include_router(holidays.api_router)
api_router.include_router(settings.api_router)
api_router.include_router(audit.api_router)
