from fastapi import Request
from fastapi.responses import RedirectResponse

# Hardcoded single admin for MVP. Move to env vars / proper user store
# when multi-user access is needed.
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "password"


def is_admin(request: Request) -> bool:
    return request.session.get("user") == ADMIN_EMAIL


def require_admin_or_redirect(request: Request) -> RedirectResponse | None:
    if not is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return None


def check_credentials(email: str, password: str) -> bool:
    return email == ADMIN_EMAIL and password == ADMIN_PASSWORD
