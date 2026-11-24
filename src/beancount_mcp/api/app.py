from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from beancount_mcp.api.routers import accounts, actions, changes, directives, ledgers, transactions
from beancount_mcp.config import Settings, load_settings
from beancount_mcp.ledger import errors
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.recipes import default_registry
from beancount_mcp.recipes.registry import RecipeRegistry
from beancount_mcp.services.actions import ActionService
from beancount_mcp.services.changes import ChangeService
from beancount_mcp.services.ledgers import LedgerService
from beancount_mcp.services.profiles import ProfileService

_STATUS_BY_ERROR: dict[type[errors.LedgerStoreError], int] = {
    errors.InvalidLedgerId: 422,
    errors.LedgerNotFound: 404,
    errors.LedgerExists: 409,
    errors.StaleVersion: 412,
    errors.TransactionNotFound: 404,
    errors.NotEditable: 409,
    errors.ChangeNotFound: 404,
    errors.ChangeNotPending: 409,
    errors.ChangeConflict: 409,
    errors.ApprovalRequired: 403,
    errors.VersionRequired: 428,
    errors.RecipeNotFound: 404,
    errors.RecipeError: 422,
    errors.UnsupportedStructure: 409,
}


def create_app(settings: Settings | None = None, registry: RecipeRegistry | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="beancount-mcp")
    app.state.settings = settings
    store = LedgerStore(settings.data_dir, settings.layout)
    registry = registry or default_registry()
    ledger_service = LedgerService(store, registry, settings.agent_approval_required)
    actions_service = ActionService(store, registry, ledger_service)
    app.state.ledger_service = ledger_service
    app.state.action_service = actions_service
    app.state.profile_service = ProfileService(store, registry)
    app.state.change_service = ChangeService(store, actions_service, settings.agent_approval_required)
    app.include_router(ledgers.router)
    app.include_router(accounts.router)
    app.include_router(transactions.router)
    app.include_router(directives.router)
    app.include_router(changes.router)
    app.include_router(actions.router)

    @app.exception_handler(errors.LedgerStoreError)
    async def store_error(_: Request, exc: errors.LedgerStoreError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=_STATUS_BY_ERROR[type(exc)])

    @app.exception_handler(errors.ChangeRejected)
    async def change_rejected(_: Request, exc: errors.ChangeRejected) -> JSONResponse:
        detail = {"detail": str(exc), "errors": [error.model_dump() for error in exc.errors]}
        return JSONResponse(detail, status_code=422)

    return app
