import json
import os
import secrets
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from comparador.adapters.storage.sqlite.repository import SqliteProductRepository
from comparador.adapters.web.auth import (
    check_credentials,
    is_admin,
    require_admin_or_redirect,
)

BASE = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(BASE / "templates"))

DB_PATH = Path(os.environ.get("COMPARADOR_DB", "data/comparador.db"))
repo = SqliteProductRepository(DB_PATH)

SESSION_SECRET = os.environ.get("COMPARADOR_SECRET", secrets.token_urlsafe(32))

app = FastAPI(title="Comparador de Preços")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
import hashlib

def get_product_color(product_id: UUID) -> str:
    # A palette of cool, modern colors (blues, teals, cold greens, cool purples, soft greys)
    palette = ['#00d4b5', '#4a90e2', '#9013fe', '#50e3c2', '#8b9dc3', '#0088ce', '#7b68ee']
    idx = int(hashlib.md5(str(product_id).encode()).hexdigest(), 16) % len(palette)
    return palette[idx]

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def _ctx(request: Request, **extra) -> dict:
    """Default template context — always includes is_admin flag."""
    return {"is_admin": is_admin(request), **extra}


# ---------------- root ----------------
@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/public/", status_code=303)


# ---------------- public ----------------
@app.get("/public/")
def public_index(request: Request):
    products = repo.list_products_public_view()
    return TEMPLATES.TemplateResponse(
        request, "public/index.html", _ctx(request, products=products)
    )


@app.get("/public/product/{product_id}")
def public_product(request: Request, product_id: str):
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid product id")
    product = repo.get_product(pid)
    if not product:
        raise HTTPException(status_code=404, detail="product not found")
    listings = repo.get_listings_for_comparison(pid)
    history = repo.get_price_history(pid)
    history_series = [{"label": k, "data": v} for k, v in history.items()]
    chart_color = get_product_color(pid)

    return TEMPLATES.TemplateResponse(
        request,
        "public/product.html",
        _ctx(
            request, 
            product=product, 
            listings=listings,
            history_json=json.dumps(history_series).replace("</", "<\\/"),
            chart_color=chart_color
        ),
    )


# ---------------- admin auth ----------------
@app.get("/admin/login")
def login_form(request: Request):
    if is_admin(request):
        return RedirectResponse(url="/admin/", status_code=303)
    return TEMPLATES.TemplateResponse(
        request, "admin/login.html", _ctx(request, error=None)
    )


@app.post("/admin/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    if check_credentials(email, password):
        request.session["user"] = email
        return RedirectResponse(url="/admin/", status_code=303)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/login.html",
        _ctx(request, error="Credenciais inválidas"),
        status_code=401,
    )


@app.get("/admin/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/admin/login", status_code=303)


# ---------------- admin ----------------
@app.get("/admin/")
def admin_index(request: Request):
    redirect = require_admin_or_redirect(request)
    if redirect:
        return redirect
    products = repo.list_products_summary()
    return TEMPLATES.TemplateResponse(
        request, "admin/index.html", _ctx(request, products=products)
    )


@app.get("/admin/product/{product_id}")
def admin_product(request: Request, product_id: str):
    redirect = require_admin_or_redirect(request)
    if redirect:
        return redirect
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid product id")
    product = repo.get_product(pid)
    if not product:
        raise HTTPException(status_code=404, detail="product not found")
    listings = repo.get_listings_with_current_price(pid)
    history = repo.get_price_history(pid)
    history_series = [
        {"label": k, "data": v} for k, v in history.items()
    ]
    chart_color = get_product_color(pid)
    
    return TEMPLATES.TemplateResponse(
        request,
        "admin/product.html",
        _ctx(
            request,
            product=product,
            listings=listings,
            history_json=json.dumps(history_series).replace("</", "<\\/"),
            chart_color=chart_color,
        ),
    )


def _update_listing_status(request: Request, listing_id: str, status: str):
    redirect = require_admin_or_redirect(request)
    if redirect:
        return redirect
    try:
        lid = UUID(listing_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid listing id")
    repo.set_listing_status(lid, status)
    return RedirectResponse(
        url=request.headers.get("referer", "/admin/"), status_code=303
    )


@app.post("/admin/listing/{listing_id}/confirm")
def listing_confirm(request: Request, listing_id: str):
    return _update_listing_status(request, listing_id, "confirmed")


@app.post("/admin/listing/{listing_id}/reject")
def listing_reject(request: Request, listing_id: str):
    return _update_listing_status(request, listing_id, "rejected")


@app.post("/admin/listing/{listing_id}/unobserve")
def listing_unobserve(request: Request, listing_id: str):
    # Same state as reject but semantically different: user is un-doing a
    # previous accept. History snapshots are kept, just not shown anywhere.
    return _update_listing_status(request, listing_id, "rejected")


@app.post("/admin/listing/{listing_id}/reactivate")
def listing_reactivate(request: Request, listing_id: str):
    # Bring back a rejected/unobserved listing to an explicitly-user-observed
    # state, regardless of its original auto-match score.
    return _update_listing_status(request, listing_id, "confirmed")
