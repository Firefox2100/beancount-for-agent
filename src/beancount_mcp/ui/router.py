import asyncio
import hmac
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from beancount_mcp.ledger.errors import LedgerStoreError
from beancount_mcp.models import (
    AccountDetails,
    AccountProfile,
    Caller,
    ChangeStatus,
    Pool,
    SetAccountDetails,
)
from beancount_mcp.models.common import Amount
from beancount_mcp.models.details import DETAIL_FIELDS, SENSITIVE_FIELDS
from beancount_mcp.ui.present import describe
from beancount_mcp.ui.session import COOKIE, SESSION_SECONDS, UiAuth

USER = Caller(actor="user", client_id="ui")
TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")

DETAIL_LABELS = {
    "bank_name": "Bank",
    "account_holder": "Account holder",
    "branch": "Branch",
    "sort_code": "Sort code",
    "account_number": "Account number",
    "routing_number": "Routing number (US)",
    "iban": "IBAN",
    "swift_bic": "SWIFT / BIC",
    "card_number": "Card number",
    "card_holder": "Name on card",
    "card_expiry": "Card expiry (MM/YY)",
}
PROFILE_ACCOUNT_FIELDS = ("autopay_from", "unbilled_account", "interest_account", "cash_account", "gains_account")


class LoginRequired(Exception):
    def __init__(self, next_path: str):
        self.next_path = next_path


def _auth(request: Request) -> UiAuth:
    return request.app.state.ui_auth


async def session(request: Request) -> str | None:
    auth = _auth(request)
    cookie = request.cookies.get(COOKIE)
    if not auth.valid(cookie):
        raise LoginRequired(request.url.path)
    return cookie


async def checked_form(request: Request, cookie: str | None = Depends(session)) -> dict[str, str]:
    """The posted form, once it is known to come from a page this service served."""
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "cross-site request refused")
    form = {key: str(value) for key, value in (await request.form()).items()}
    if not _matches(form.get("csrf", ""), _auth(request).csrf_token(cookie)):
        raise HTTPException(403, "this page has expired, reload it and try again")
    return form


def _matches(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def render(request: Request, template: str, status_code: int = 200, **context) -> HTMLResponse:
    auth = _auth(request)
    cookie = request.cookies.get(COOKIE)
    context.setdefault("flash", request.query_params.get("flash"))
    context.setdefault("flash_kind", request.query_params.get("kind", "ok"))
    return TEMPLATES.TemplateResponse(
        request,
        template,
        {"csrf": auth.csrf_token(cookie), "login_enabled": auth.enabled, **context},
        status_code=status_code,
    )


def back(path: str, message: str, kind: str = "ok") -> RedirectResponse:
    return RedirectResponse(f"{path}?{urlencode({'flash': message, 'kind': kind})}", status_code=303)


def _safe_next(path: str | None) -> str:
    return path if path and path.startswith("/ui") and not path.startswith("//") else "/ui/"


def _problem(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" if error["loc"] else error["msg"]
            for error in exc.errors()
        )
    return str(exc)


def _services(request: Request):
    state = request.app.state
    return state.ledger_service, state.change_service, state.profile_service


router = APIRouter(prefix="/ui", include_in_schema=False)
protected = APIRouter(dependencies=[Depends(session)])


@router.get("/login")
async def login_page(request: Request, next: str | None = None):
    if not _auth(request).enabled:
        return RedirectResponse("/ui/", status_code=303)
    return render(request, "login.html", next=_safe_next(next))


@router.post("/login")
async def login(request: Request):
    auth = _auth(request)
    form = {key: str(value) for key, value in (await request.form()).items()}
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "cross-site request refused")
    if not auth.token_matches(form.get("token", "")):
        await asyncio.sleep(0.5)
        return render(request, "login.html", status_code=401, next=_safe_next(form.get("next")),
                      flash="That is not the service token.", flash_kind="error")
    response = RedirectResponse(_safe_next(form.get("next")), status_code=303)
    response.set_cookie(COOKIE, auth.issue(), max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                        path="/ui", secure=request.url.scheme == "https")
    return response


@router.post("/logout")
async def logout(form: dict = Depends(checked_form)):
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie(COOKIE, path="/ui")
    return response


@router.get("")
async def bare_root():
    return RedirectResponse("/ui/", status_code=307)


@protected.get("/")
async def inbox(request: Request):
    ledgers, changes, _ = _services(request)
    groups = []
    for info in await ledgers.list_ledgers():
        pending = await changes.list(info.id, ChangeStatus.PENDING)
        groups.append({
            "id": info.id,
            "changes": [{"change": c, "blocks": describe(c.operation)} for c in sorted(pending, key=lambda c: c.created_at)],
        })
    return render(request, "inbox.html", groups=groups, total=sum(len(g["changes"]) for g in groups))


@protected.post("/ledgers/{ledger}/changes/{change_id}/{verb}")
async def resolve(request: Request, ledger: str, change_id: str, verb: str, form: dict = Depends(checked_form)):
    _, changes, _ = _services(request)
    if verb not in ("approve", "reject"):
        raise HTTPException(404)
    note = form.get("note", "").strip() or None
    try:
        await (changes.approve if verb == "approve" else changes.reject)(ledger, change_id, note)
    except LedgerStoreError as exc:
        return back("/ui/", f"Could not {verb} {change_id}: {exc}", "error")
    return back("/ui/", f"{'Approved' if verb == 'approve' else 'Rejected'} {change_id}.")


@protected.get("/ledgers/{ledger}/history")
async def history(request: Request, ledger: str):
    _, changes, _ = _services(request)
    resolved = [c for c in await changes.list(ledger, None) if c.status != ChangeStatus.PENDING]
    resolved.sort(key=lambda c: c.resolved_at or c.created_at, reverse=True)
    return render(request, "history.html", ledger=ledger,
                  items=[{"change": c, "blocks": describe(c.operation)} for c in resolved[:50]])


@protected.get("/ledgers/{ledger}/accounts")
async def accounts(request: Request, ledger: str):
    ledgers, _, _ = _services(request)
    status = await ledgers.get_ledger(ledger)
    listed = [a for a in await ledgers.list_accounts(ledger) if a.close_date is None]
    return render(request, "accounts.html", ledger=ledger, accounts=listed, errors=status.errors)


@protected.get("/ledgers/{ledger}/accounts/{account}")
async def account_page(request: Request, ledger: str, account: str):
    ledgers, _, profiles = _services(request)
    info = next((a for a in await ledgers.list_accounts(ledger) if a.name == account), None)
    if info is None:
        raise HTTPException(404, "no such account")
    view = await profiles.get(ledger)
    open_names = sorted(a.name for a in await ledgers.list_accounts(ledger) if a.close_date is None)
    return render(
        request, "account.html", ledger=ledger, info=info,
        fields=[(name, DETAIL_LABELS[name], name in SENSITIVE_FIELDS) for name in DETAIL_FIELDS],
        profile=view.profile.accounts.get(account, AccountProfile()), profile_version=view.version,
        warnings=[w for w in view.warnings if w.startswith(account)], pools=sorted(view.profile.pools),
        account_fields=PROFILE_ACCOUNT_FIELDS, open_names=open_names,
    )


@protected.post("/ledgers/{ledger}/accounts/{account}/details")
async def save_details(request: Request, ledger: str, account: str, form: dict = Depends(checked_form)):
    ledgers, _, _ = _services(request)
    path = f"/ui/ledgers/{ledger}/accounts/{quote(account)}"
    info = next((a for a in await ledgers.list_accounts(ledger) if a.name == account), None)
    if info is None:
        raise HTTPException(404, "no such account")
    changed, cleared = {}, []
    for name in DETAIL_FIELDS:
        new, old = form.get(name, "").strip(), info.details.get(name, "")
        if new == old:
            continue
        if new:
            changed[name] = new
        else:
            cleared.append(name)
    if not changed and not cleared:
        return back(path, "Nothing changed.")
    try:
        operation = SetAccountDetails(account=account, set=AccountDetails(**changed), clear=cleared)
        await ledgers.apply(ledger, operation, USER, None)
    except (ValidationError, LedgerStoreError) as exc:
        return back(path, _problem(exc), "error")
    return back(path, "Bank details saved.")


def _text(form: dict, name: str) -> str | None:
    return form.get(name, "").strip() or None


@protected.post("/ledgers/{ledger}/accounts/{account}/profile")
async def save_profile(request: Request, ledger: str, account: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    path = f"/ui/ledgers/{ledger}/accounts/{quote(account)}"
    view = await profiles.get(ledger)
    existing = view.profile.accounts.get(account, AccountProfile())
    try:
        values = {name: _text(form, name) for name in
                  ("description", "statement_day", "due_day", "pool", "maturity_date", "interest_rate", *PROFILE_ACCOUNT_FIELDS)}
        updated = AccountProfile(**values, recipes=existing.recipes)
        profile = view.profile.model_copy(update={"accounts": {**view.profile.accounts, account: updated}})
        await profiles.put(ledger, profile, USER, form.get("profile_version") or None)
    except (ValidationError, LedgerStoreError) as exc:
        return back(path, _problem(exc), "error")
    return back(path, "Profile saved.")


@protected.get("/ledgers/{ledger}/pools")
async def pools_page(request: Request, ledger: str):
    _, _, profiles = _services(request)
    view = await profiles.get(ledger)
    rows = [(name, pool.limit.number, pool.limit.currency) for name, pool in sorted(view.profile.pools.items())]
    return render(request, "pools.html", ledger=ledger, rows=rows + [("", "", "")], profile_version=view.version)


@protected.post("/ledgers/{ledger}/pools")
async def save_pools(request: Request, ledger: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    path = f"/ui/ledgers/{ledger}/pools"
    view = await profiles.get(ledger)
    try:
        pools = {}
        for index in range(len(view.profile.pools) + 1):
            name = form.get(f"name{index}", "").strip()
            if not name:
                continue
            number = Decimal(form.get(f"limit{index}", "").strip() or "0")
            pools[name] = Pool(limit=Amount(number=number, currency=form.get(f"currency{index}", "").strip().upper()))
        await profiles.put(ledger, view.profile.model_copy(update={"pools": pools}), USER, form.get("profile_version") or None)
    except (ValidationError, LedgerStoreError, InvalidOperation) as exc:
        return back(path, _problem(exc), "error")
    return back(path, "Pools saved.")


router.include_router(protected)


def install(app: FastAPI, token: str | None) -> None:
    app.state.ui_auth = UiAuth(token)
    app.mount("/ui/static", StaticFiles(directory=Path(__file__).parent / "static"), name="ui-static")

    @app.exception_handler(LoginRequired)
    async def login_redirect(_: Request, exc: LoginRequired) -> Response:
        return RedirectResponse(f"/ui/login?{urlencode({'next': exc.next_path})}", status_code=303)

    app.include_router(router)
