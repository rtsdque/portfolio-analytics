"""FastAPI application.

Stores no user data. Portfolios live in the browser; the database here is a
cache of public market and filing data only.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app.deps import get_creditlab_service, get_portfolio_service
from app.providers.base import (
    InsufficientData,
    ProviderError,
    RateLimited,
    SubscriptionError,
    SymbolNotFound,
)
from app.schemas import (
    AnalyticsResponse,
    CreditRequest,
    CreditResponse,
    ErrorResponse,
    PortfolioRequest,
    PortfolioResponse,
)
from app.services.creditlab import CreditLabService
from app.services.portfolio import PortfolioService

app = FastAPI(
    title="Portfolio Analytics",
    description="Portfolio performance, risk analytics, and corporate credit assessment.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_STATUS = {
    SymbolNotFound: (404, "symbol_not_found"),
    InsufficientData: (422, "insufficient_data"),
    RateLimited: (429, "rate_limited"),
    SubscriptionError: (402, "subscription_required"),
}


@app.exception_handler(ProviderError)
async def _provider_error(request: Request, exc: ProviderError) -> JSONResponse:
    status, code = _STATUS.get(type(exc), (502, "provider_error"))
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(code=code, message=str(exc)).model_dump(),
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/portfolio", response_model=PortfolioResponse)
def portfolio(
    request: PortfolioRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioResponse:
    return service.build_portfolio(request)


@app.post("/api/analytics", response_model=AnalyticsResponse)
def analytics(
    request: PortfolioRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> AnalyticsResponse:
    return service.build_analytics(request)


@app.post("/api/credit", response_model=CreditResponse)
def credit(
    request: CreditRequest,
    service: CreditLabService = Depends(get_creditlab_service),
) -> CreditResponse:
    return service.compare(request)
