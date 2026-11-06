from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .config import Settings, default_login_url
from .live_orders import PlaceParams, touch_kill_switch
from .risk import kill_switch_active
from .services.state import AppState

log = logging.getLogger(__name__)

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
        version="0.2.0",
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

    @app.api_route("/postback/kite", methods=["GET", "POST"])
    async def kite_postback(
        request: Request,
        state: Annotated[AppState, Depends(get_state)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> JSONResponse:
        """Kite order postback endpoint — logs payload for visibility (verify optional secret)."""
        secret_q = request.query_params.get("secret")
        if settings.kite_postback_secret and secret_q != settings.kite_postback_secret:
            raise HTTPException(status_code=401, detail="invalid postback secret")
        body: dict[str, Any] = {}
        try:
            if request.method == "GET":
                body = dict(request.query_params)
            elif request.method == "POST":
                ct = request.headers.get("content-type", "")
                if "application/json" in ct:
                    body = await request.json()
                elif "application/x-www-form-urlencoded" in ct:
                    form = await request.form()
                    body = dict(form)
                else:
                    body = dict(request.query_params)
        except Exception as exc:  # noqa: BLE001
            log.warning("postback parse: %s", exc)
        state.db.add_live_order_event(
            kind="postback",
            order_id=str(body.get("order_id") or body.get("data", {}).get("order_id") or ""),
            tag=str(body.get("tag") or ""),
            request_json={"method": request.method, "query": dict(request.query_params)},
            response_json=body,
        )
        return JSONResponse({"ok": True})

    class PlaceOrderBody(BaseModel):
        exchange: Literal["NSE", "NFO", "BSE", "BFO", "MCX"]
        tradingsymbol: str
        transaction_type: Literal["BUY", "SELL"]
        quantity: int = Field(ge=1)
        product: Literal["MIS", "NRML", "CNC"]
        order_type: Literal["MARKET", "LIMIT", "SL", "SL-M"]
        price: float | None = None
        trigger_price: float | None = None
        validity: str = "DAY"
        market_protection: int | None = -1

    @app.post("/api/orders/place")
    def api_place_order(
        body: PlaceOrderBody,
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> JSONResponse:
        kite = state.kite_with_token()
        params = PlaceParams(
            exchange=body.exchange,
            tradingsymbol=body.tradingsymbol,
            transaction_type=body.transaction_type,
            quantity=body.quantity,
            product=body.product,
            order_type=body.order_type,
            price=body.price,
            trigger_price=body.trigger_price,
            validity=body.validity,
            market_protection=body.market_protection,
        )
        try:
            result = state.live_orders.place_order(kite, params)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    class ModifyBody(BaseModel):
        order_id: str
        quantity: int | None = None
        price: float | None = None
        order_type: str | None = None
        trigger_price: float | None = None

    @app.post("/api/orders/modify")
    def api_modify_order(
        body: ModifyBody,
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> JSONResponse:
        kite = state.kite_with_token()
        try:
            result = state.live_orders.modify_order(
                kite,
                order_id=body.order_id,
                quantity=body.quantity,
                price=body.price,
                order_type=body.order_type,
                trigger_price=body.trigger_price,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    class CancelBody(BaseModel):
        order_id: str

    @app.post("/api/orders/cancel")
    def api_cancel_order(
        body: CancelBody,
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> JSONResponse:
        kite = state.kite_with_token()
        try:
            result = state.live_orders.cancel_order(kite, order_id=body.order_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/api/actions/square-off")
    def api_square_off(
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> JSONResponse:
        kite = state.kite_with_token()
        cancels = state.live_orders.cancel_open_orders(kite)
        squares = state.live_orders.square_off_positions(kite)
        return JSONResponse({"cancel_open": cancels, "square_off": squares})

    @app.post("/api/actions/kill-switch")
    def api_kill_switch(
        _: Annotated[str, Depends(verify_user)],
        state: Annotated[AppState, Depends(get_state)],
    ) -> RedirectResponse:
        touch_kill_switch(state.settings.kill_switch_path)
        state.db.set_strategy_running(False)
        kite = state.kite_with_token()
        if state.live_orders.live_mode() and kite.access_token:
            state.live_orders.cancel_open_orders(kite)
            state.live_orders.square_off_positions(kite)
        state.db.kv_set(
            "ui_last_run",
            json.dumps({"emergency": "kill_switch", "live": state.live_orders.live_mode()}),
        )
        return RedirectResponse(url="/", status_code=303)

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
        msg = json.dumps(result, default=str)
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
        live_mode = state.live_orders.live_mode()

        ctx = {
            "request": request,
            "logged_in": logged_in,
            "paper_trading": settings.paper_trading,
            "enable_live_orders": settings.enable_live_orders,
            "live_mode": live_mode,
            "order_tag_prefix": settings.order_tag_prefix,
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
            "live_order_log": state.db.recent_live_order_events(40),
        }
        return templates.TemplateResponse("dashboard.html", ctx)

    return app


app = create_app()
