import asyncio
import datetime as dt
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
from beancount_mcp.ledger.recurring import slug
from beancount_mcp.models.budgets import Budget
from beancount_mcp.models.common import Amount
from beancount_mcp.models.goals import Goal
from beancount_mcp.models.recurring import Recurring
from beancount_mcp.models.details import DETAIL_FIELDS, SENSITIVE_FIELDS
from beancount_mcp.ui.present import describe, grouped, held, line_chart
from beancount_mcp.ui.session import COOKIE, SESSION_SECONDS, UiAuth

USER = Caller(actor="user", client_id="ui")
TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
TEMPLATES.env.filters["num"] = grouped
TEMPLATES.env.filters["held"] = held
ROOTS = ("Assets", "Liabilities", "Equity", "Income", "Expenses")

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
    return _verified(request, cookie, await request.form())[0]


def _verified(request: Request, cookie: str | None, form) -> tuple[dict[str, str], dict]:
    """The text fields of a form, and its files, after the origin and CSRF checks."""
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "cross-site request refused")
    fields = {key: str(value) for key, value in form.items() if isinstance(value, str)}
    if not _matches(fields.get("csrf", ""), _auth(request).csrf_token(cookie)):
        raise HTTPException(403, "this page has expired, reload it and try again")
    return fields, {key: value for key, value in form.items() if not isinstance(value, str)}


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


@protected.get("/ledgers/{ledger}/receipts")
async def receipts_page(request: Request, ledger: str):
    ledgers, _, _ = _services(request)
    service = request.app.state.receipt_service
    recent = (await ledgers.list_transactions(ledger, limit=100_000)).items[-40:]
    return render(request, "receipts.html", ledger=ledger, items=await service.listing(ledger), recent=list(reversed(recent)), access=service.access)


@protected.post("/ledgers/{ledger}/receipts")
async def upload_receipt(request: Request, ledger: str, cookie: str | None = Depends(session)):
    fields, files = _verified(request, cookie, await request.form())
    service = request.app.state.receipt_service
    path = f"/ui/ledgers/{ledger}/receipts"
    upload = files.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        return back(path, "Choose a receipt first.", "error")
    try:
        receipt = await service.upload(ledger, upload.filename, await upload.read(service.max_bytes + 1), USER)
        if fields.get("transaction"):
            await service.attach(ledger, fields["transaction"], receipt.path, USER)
    except LedgerStoreError as exc:
        return back(path, str(exc), "error")
    return back(path, f"Stored {receipt.name}" + (" and linked it." if fields.get("transaction") else "."))


@protected.post("/ledgers/{ledger}/receipts/attach")
async def attach_receipt(request: Request, ledger: str, form: dict = Depends(checked_form)):
    path = f"/ui/ledgers/{ledger}/receipts"
    try:
        await request.app.state.receipt_service.attach(ledger, form.get("transaction", ""), form.get("path", ""), USER)
    except LedgerStoreError as exc:
        return back(path, str(exc), "error")
    return back(path, "Linked.")


@protected.get("/ledgers/{ledger}/receipts/file")
async def receipt_file(request: Request, ledger: str, path: str):
    try:
        content, media_type = await request.app.state.receipt_service.file(ledger, path)
    except LedgerStoreError as exc:
        raise HTTPException(404, str(exc)) from None
    return Response(content, media_type=media_type, headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@protected.get("/ledgers/{ledger}/goals")
async def goals_page(request: Request, ledger: str):
    ledgers, _, _ = _services(request)
    accounts = sorted({":".join(a.name.split(":")[:depth]) for a in await ledgers.list_accounts(ledger)
                       if a.close_date is None and a.name.startswith("Assets") for depth in (2, len(a.name.split(":")))})
    return render(request, "goals.html", ledger=ledger, items=await request.app.state.view_service.goals(ledger), accounts=accounts)


@protected.post("/ledgers/{ledger}/goals")
async def add_goal(request: Request, ledger: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    path = f"/ui/ledgers/{ledger}/goals"
    try:
        currency = form.get("currency", "").strip().upper()
        monthly = _text(form, "monthly")
        goal = Goal(
            title=form.get("title", "").strip(),
            accounts=[name.strip() for name in form.get("accounts", "").replace("\n", ",").split(",") if name.strip()],
            target=Amount(number=Decimal(form.get("target", "").strip() or "0"), currency=currency),
            by=_text(form, "by"), monthly=Amount(number=Decimal(monthly), currency=currency) if monthly else None,
        )
        if not goal.title:
            raise ValueError("give it a title")
        await profiles.set_goal(ledger, slug(goal.title), goal, USER)
    except (ValidationError, LedgerStoreError, InvalidOperation, ValueError) as exc:
        return back(path, _problem(exc), "error")
    return back(path, f"Saved {goal.title}.")


@protected.post("/ledgers/{ledger}/goals/{goal}/delete")
async def delete_goal(request: Request, ledger: str, goal: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    await profiles.set_goal(ledger, goal, None, USER)
    return back(f"/ui/ledgers/{ledger}/goals", "Removed.")


@protected.get("/ledgers/{ledger}/budgets")
async def budgets_page(request: Request, ledger: str):
    ledgers, _, _ = _services(request)
    views = request.app.state.view_service
    groups = sorted({":".join(a.name.split(":")[:depth]) for a in await ledgers.list_accounts(ledger)
                     if a.close_date is None and a.name.startswith("Expenses") for depth in (1, 2, len(a.name.split(":")))})
    return render(request, "budgets.html", ledger=ledger, today_ordinal=dt.date.today().toordinal(), items=await views.budgets(ledger), groups=groups,
                  suggestions=await views.budget_suggestions(ledger))


@protected.post("/ledgers/{ledger}/budgets")
async def add_budget(request: Request, ledger: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    path = f"/ui/ledgers/{ledger}/budgets"
    try:
        budget = Budget(
            account=form.get("account", "").strip(),
            amount=Amount(number=Decimal(form.get("number", "").strip() or "0"), currency=form.get("currency", "").strip().upper()),
            every=form.get("every", "month"), start_day=int(form.get("start_day") or 1),
        )
        await profiles.set_budget(ledger, slug(budget.account.removeprefix("Expenses:").removeprefix("Expenses") or "expenses"), budget, USER)
    except (ValidationError, LedgerStoreError, InvalidOperation, ValueError) as exc:
        return back(path, _problem(exc), "error")
    return back(path, f"Saved the budget for {budget.account}.")


@protected.post("/ledgers/{ledger}/budgets/suggestions/{suggestion}")
async def adopt_budget(request: Request, ledger: str, suggestion: str, form: dict = Depends(checked_form)):
    """Adopt a suggested budget. It is looked up again here, so nothing the browser sends is trusted."""
    _, _, profiles = _services(request)
    found = next((s for s in await request.app.state.view_service.budget_suggestions(ledger) if s.id == suggestion), None)
    path = f"/ui/ledgers/{ledger}/budgets"
    if found is None:
        return back(path, "That suggestion is gone.", "error")
    await profiles.set_budget(ledger, found.id, found.budget, USER)
    return back(path, f"Added a budget for {found.budget.account}.")


@protected.post("/ledgers/{ledger}/budgets/{budget}/delete")
async def delete_budget(request: Request, ledger: str, budget: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    await profiles.set_budget(ledger, budget, None, USER)
    return back(f"/ui/ledgers/{ledger}/budgets", "Removed.")


@protected.get("/ledgers/{ledger}/reports")
async def reports_page(request: Request, ledger: str, start: str = "", end: str = "", interval: str = "month", compare: str = "", account: str = ""):
    """Income and expenses over a period, from the same view the agent's report tool reads."""
    try:
        first = dt.date.fromisoformat(start) if start else None
        last = dt.date.fromisoformat(end) if end else None
        report = await request.app.state.view_service.income_statement(
            ledger, first, last, None, account.strip() or None, interval if interval in ("week", "month") else None, compare == "on",
        )
        problem = None
    except (ValueError, LedgerStoreError) as exc:
        report, problem = None, str(exc)
    today = dt.date.today()
    last_month_end = today.replace(day=1) - dt.timedelta(days=1)
    presets = [
        ("This month", today.replace(day=1), today), ("Last month", last_month_end.replace(day=1), last_month_end),
        ("Last 90 days", today - dt.timedelta(days=89), today), ("This year", today.replace(month=1, day=1), today),
    ]
    return render(request, "reports.html", ledger=ledger, report=report, problem=problem, presets=presets,
                  form={"start": start or (report.start.isoformat() if report else ""), "end": end or (report.end.isoformat() if report else ""),
                        "interval": interval, "compare": compare == "on", "account": account})


@protected.get("/ledgers/{ledger}/recurring")
async def recurring_page(request: Request, ledger: str):
    ledgers, _, _ = _services(request)
    views = request.app.state.view_service
    accounts = sorted(a.name for a in await ledgers.list_accounts(ledger) if a.close_date is None)
    return render(request, "recurring.html", ledger=ledger, accounts=accounts,
                  items=await views.recurring(ledger, 30, 60), suggestions=await views.recurring_suggestions(ledger))


@protected.post("/ledgers/{ledger}/recurring")
async def add_recurring(request: Request, ledger: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    path = f"/ui/ledgers/{ledger}/recurring"
    try:
        item = Recurring(
            title=form.get("title", "").strip(), from_account=form.get("from_account", ""), to_account=form.get("to_account", ""),
            amount=Amount(number=Decimal(form.get("number", "").strip() or "0"), currency=form.get("currency", "").strip().upper()),
            every=form.get("every", "month"), interval=int(form.get("interval") or 1), start=form.get("start", ""),
            end=_text(form, "end"), payee=_text(form, "payee"), variable=form.get("variable") == "on",
        )
        if not item.title:
            raise ValueError("give it a title")
        await profiles.set_recurring(ledger, slug(item.title), item, USER)
    except (ValidationError, LedgerStoreError, InvalidOperation, ValueError) as exc:
        return back(path, _problem(exc), "error")
    return back(path, f"Saved {item.title}.")


@protected.post("/ledgers/{ledger}/recurring/suggestions/{suggestion}")
async def adopt_suggestion(request: Request, ledger: str, suggestion: str, form: dict = Depends(checked_form)):
    """Adopt a pattern found in the history. It is looked up again here, so nothing the browser sends is trusted."""
    _, _, profiles = _services(request)
    found = next((s for s in await request.app.state.view_service.recurring_suggestions(ledger) if s.id == suggestion), None)
    path = f"/ui/ledgers/{ledger}/recurring"
    if found is None:
        return back(path, "That pattern is no longer in the history.", "error")
    await profiles.set_recurring(ledger, found.id, found.recurring, USER)
    return back(path, f"Added {found.recurring.title}.")


@protected.post("/ledgers/{ledger}/recurring/{item}/delete")
async def delete_recurring(request: Request, ledger: str, item: str, form: dict = Depends(checked_form)):
    _, _, profiles = _services(request)
    await profiles.set_recurring(ledger, item, None, USER)
    return back(f"/ui/ledgers/{ledger}/recurring", "Removed.")


@protected.get("/ledgers/{ledger}/imports")
async def imports_page(request: Request, ledger: str):
    ledgers, _, _ = _services(request)
    service = request.app.state.import_service
    accounts = sorted(a.name for a in await ledgers.list_accounts(ledger)
                      if a.close_date is None and a.name.split(":")[0] in ("Assets", "Liabilities"))
    return render(request, "imports.html", ledger=ledger, items=await service.summaries(ledger), accounts=accounts, formats=service.formats())


@protected.post("/ledgers/{ledger}/imports")
async def upload_import(request: Request, ledger: str, cookie: str | None = Depends(session)):
    fields, files = _verified(request, cookie, await request.form())
    service = request.app.state.import_service
    path = f"/ui/ledgers/{ledger}/imports"
    upload = files.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        return back(path, "Choose a statement file first.", "error")
    try:
        data = await upload.read(service.max_bytes + 1)
        created = await service.upload(ledger, fields.get("account", ""), upload.filename, data, fields.get("format") or None)
    except LedgerStoreError as exc:
        return back(path, str(exc), "error")
    return back(path, f"Read {sum(len(c.statement.lines) for c in created)} transactions from {upload.filename}. Ask the agent to propose them.")


@protected.get("/ledgers/{ledger}/imports/{import_id}")
async def import_page(request: Request, ledger: str, import_id: str):
    try:
        review = await request.app.state.import_service.review(ledger, import_id, False, 2000)
    except LedgerStoreError as exc:
        raise HTTPException(404, str(exc)) from None
    return render(request, "import.html", ledger=ledger, review=review)


@protected.post("/ledgers/{ledger}/imports/{import_id}/delete")
async def delete_import(request: Request, ledger: str, import_id: str, form: dict = Depends(checked_form)):
    try:
        await request.app.state.import_service.delete(ledger, import_id)
    except LedgerStoreError as exc:
        return back(f"/ui/ledgers/{ledger}/imports", str(exc), "error")
    return back(f"/ui/ledgers/{ledger}/imports", "Statement removed.")


def _total(held_by_currency: dict[str, Decimal], base: str | None, rates: dict[str, str]) -> str:
    """One line for a root: its base-currency total when every currency has a rate, else each currency as held."""
    if base and held_by_currency and all(c == base or c in rates for c in held_by_currency):
        value = sum((number * (1 if c == base else Decimal(rates[c])) for c, number in held_by_currency.items()), Decimal(0))
        return f"≈ {grouped(f'{value:.2f}')} {base}"
    return held({c: n for c, n in held_by_currency.items()})


@protected.get("/ledgers/{ledger}/overview")
async def overview(request: Request, ledger: str, interval: str = "month"):
    """The same overview as the DeepSeek Harness dock: position, what is due, and every account with its balance."""
    ledgers, _, _ = _services(request)
    views = request.app.state.view_service
    interval = interval if interval in ("week", "month") else "month"
    accounts = [a for a in await ledgers.list_accounts(ledger) if a.close_date is None]
    balances = {b.account: b.balances for b in await ledgers.balances(ledger, None)}
    due = await views.due(ledger, None, None)
    scheduled = [item for item in await views.recurring(ledger, 14, 45) if item.occurrences]
    watched = [b for b in await views.budgets(ledger) if b.state != "ok"]
    findings = await views.checks(ledger, 45)
    try:
        position, problem = await views.financial_position(ledger, interval, 12), None
    except Exception as exc:  # the valuation is optional; the rest of the page must still show
        position, problem = None, str(exc)
    rates = position.rates if position else {}
    base = position.base_currency if position else None
    roots = []
    for root in ROOTS:
        rows = [a for a in accounts if a.name == root or a.name.startswith(f"{root}:")]
        if not rows:
            continue
        sums: dict[str, Decimal] = {}
        for account in rows:
            for currency, number in balances.get(account.name, {}).items():
                sums[currency] = sums.get(currency, Decimal(0)) + Decimal(number)
        roots.append({
            "name": root, "total": _total(sums, base, rates),
            "rows": [{"name": a.name, "short": a.name[len(root) + 1:], "type": a.type, "bank": a.details.get("bank_name"),
                      "held": held(balances.get(a.name, {}))} for a in rows],
        })
    chart = line_chart(position.points, ("assets", "liabilities", "net")) if position else {}
    return render(request, "overview.html", ledger=ledger, interval=interval, position=position, problem=problem,
                  chart=chart, roots=roots, due=due, scheduled=scheduled, watched=watched, findings=findings, latest=position.points[-1] if position and position.points else None)


@protected.post("/ledgers/{ledger}/reference-rates/refresh")
async def refresh_rates(request: Request, ledger: str, form: dict = Depends(checked_form)):
    status = await request.app.state.view_service.refresh_reference_rates(ledger)
    return back(f"/ui/ledgers/{ledger}/overview", f"Reference rates: {status.state}.")


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
