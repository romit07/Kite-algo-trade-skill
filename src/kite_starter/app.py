from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .config import Settings, default_login_url
from .risk import kill_switch_active
from .services.state import AppState

security = HTTPBasic()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def get_settings() -> Settings:
    return Settings()


def get_state(settings: Annotated[Settings, Depends(get_settings)]) -> AppState:
    return AppState.from_settings(settings)


def verify_user(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    ok_user = credentials.username == settings.dashboard_user
    ok_pass = credentials.password == settings.dashboard_password
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kite Starter (Educational)",
        version="0.1.0",
        description="Paper-first Zerodha Kite Connect starter — not financial advice.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/login")
    def login(settings: Annotated[Settings, Depends(get_settings)]) -> RedirectResponse:
        url = settings.kite_login_url or default_login_url(settings.kite_api_key)
        return RedirectResponse(url)

    @app.get("/callback/kite")
    def kite_callback(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> HTMLResponse:
        """Show request_token from redirect for manual exchange — educational."""
        token = request.query_params.get("request_token")
        if not token:
            return HTMLResponse(
                "<p>No request_token in query. Complete login at /login first.</p>",
                status_code=400,
            )
        safe = json.dumps(token)
        return HTMLResponse(
            content=f"""
            <html><body style="font-family: system-ui; padding: 2rem;">
            <p>Captured <code>request_token</code> (handle securely; do not share):</p>
            <pre>{safe}</pre>
            <p>POST it to <code>/api/auth/exchange</code> as JSON with {{ "request_token": "..." }}.</p>
            <p>Your configured redirect is: <code>{settings.kite_redirect_url}</code></p>
            </body></html>
            """
        )

    class ExchangeBody(BaseModel):
        request_token: str

    @app.post("/api/auth/exchange")
    def exchange_token(
        body: ExchangeBody,
        state: Annotated[AppState, Depends(get_state)],
    ) -> JSONResponse:
        kite = state.kite_factory.build(access_token=None)
        try:
            session = kite.generate_session(body.request_token, api_secret=state.settings.kite_api_secret)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"generate_session failed: {exc}") from exc
        access = session.get("access_token")
        refresh = session.get("refresh_token")
        if not access:
            raise HTTPException(status_code=400, detail="No access_token in session response")
        state.db.set_session_tokens(access, refresh)
        return JSONResponse({"ok": True, "access_token_preview": access[:6] + "…"})

    @app.post("/api/strategy/start")
    def strategy_start(
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> RedirectResponse:
        state.db.set_strategy_running(True)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/api/strategy/stop")
    def strategy_stop(
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> RedirectResponse:
        state.db.set_strategy_running(False)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/api/strategy/run-once")
    def strategy_run_once(
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> RedirectResponse:
        kite = state.kite_with_token()
        result = state.strategy.run_once(kite)
        msg = json.dumps(result)
        # Store last run message in kv for template display (session flash substitute)
        state.db.kv_set("ui_last_run", msg)
        return RedirectResponse(url="/", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> HTMLResponse:
        kite = state.kite_with_token()
        logged_in = bool(kite.access_token)
        profile = positions = orders = margins = {}
        if logged_in:
            try:
                profile = kite.profile()
            except Exception as exc:  # noqa: BLE001
                profile = {"error": str(exc)}
            try:
                positions = kite.positions()
            except Exception as exc:  # noqa: BLE001
                positions = {"error": str(exc)}
            try:
                orders = kite.orders()
            except Exception as exc:  # noqa: BLE001
                orders = [{"error": str(exc)}]
            try:
                margins = kite.margins()
            except Exception as exc:  # noqa: BLE001
                margins = {"error": str(exc)}

        meta = state.db.get_strategy_meta()
        orders_today, realized = state.db.today_counters()
        last_run = state.db.kv_get("ui_last_run")

        ctx = {
            "request": request,
            "logged_in": logged_in,
            "paper_trading": settings.paper_trading,
            "enable_live_orders": settings.enable_live_orders,
            "kill_switch_path": settings.kill_switch_path,
            "kill_switch": kill_switch_active(settings),
            "orders_today": orders_today,
            "max_orders": settings.max_orders_per_day,
            "realized_pnl": round(realized, 2),
            "max_loss": settings.max_daily_loss_inr,
            "strategy_running": bool(meta.get("running")),
            "last_signal": meta.get("last_signal"),
            "last_run_message": last_run,
            "profile_json": json.dumps(profile, indent=2, default=str),
            "positions_json": json.dumps(positions, indent=2, default=str),
            "orders_json": json.dumps(orders, indent=2, default=str),
            "margins_json": json.dumps(margins, indent=2, default=str),
            "paper_positions": state.db.get_paper_positions(),
            "paper_orders": state.db.recent_paper_orders(50),
        }
        return templates.TemplateResponse("dashboard.html", ctx)

    return app


app = create_app()
