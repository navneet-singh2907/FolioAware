"""FastAPI application composition root."""

from collections.abc import Awaitable, Callable
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from folioaware.api.dependencies import ApplicationContainer, build_container
from folioaware.api.schemas import (
    AskRequest,
    AskResponse,
    InsightReportRequest,
    InsightReportResponse,
    ProblemResponse,
)
from folioaware.config import Settings
from folioaware.domain.exceptions import (
    InsightsUnavailableError,
    InvalidModelOutputError,
    KnowledgeUnavailableError,
    ModelUnavailableError,
)
from folioaware.security import PublicRequestGuard


def _problem(*, request_id: str, status: int, code: str, title: str) -> JSONResponse:
    body = ProblemResponse(
        type=f"https://folioaware.dev/problems/{code.casefold().replace('_', '-')}",
        title=title,
        status=status,
        code=code,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json", by_alias=True),
        media_type="application/problem+json",
    )


def create_app(
    container: ApplicationContainer | None = None,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    """Create an application using explicit dependencies and no network I/O."""
    resolved_settings = settings or Settings()
    dependencies = container or build_container(resolved_settings)
    application = FastAPI(
        title="FolioAware",
        summary="A portfolio agent that stays current.",
        version="0.1.0",
    )
    application.state.container = dependencies
    bearer = HTTPBearer(auto_error=False)
    request_guard = PublicRequestGuard(
        per_client_limit=resolved_settings.rate_limit_per_client_requests,
        global_limit=resolved_settings.rate_limit_global_requests,
        window_seconds=resolved_settings.rate_limit_window_seconds,
        max_clients=resolved_settings.rate_limit_max_clients,
        max_concurrent=resolved_settings.answer_concurrency_limit,
    )

    def next_request_id() -> str:
        return dependencies.identifiers.new()

    def require_owner(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None or not compare_digest(
            credentials.credentials,
            dependencies.owner_report_token.get_secret_value(),
        ):
            raise HTTPException(status_code=401, detail="owner authentication required")

    @application.middleware("http")
    async def protect_public_answers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "POST" or request.url.path != "/v1/ask":
            return await call_next(request)

        client_key = request.client.host if request.client is not None else "unknown"
        decision = request_guard.admit(client_key)
        if not decision.admitted:
            if decision.reason == "rate_limited":
                response = _problem(
                    request_id=next_request_id(),
                    status=429,
                    code="RATE_LIMITED",
                    title="Too many questions were submitted",
                )
            else:
                response = _problem(
                    request_id=next_request_id(),
                    status=503,
                    code="ANSWER_CAPACITY_EXCEEDED",
                    title="Answer capacity is temporarily unavailable",
                )
            response.headers["Retry-After"] = str(decision.retry_after_seconds)
            return response

        try:
            return await call_next(request)
        finally:
            request_guard.release()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        is_question = request.url.path == "/v1/ask"
        return _problem(
            request_id=next_request_id(),
            status=422,
            code="INVALID_QUESTION" if is_question else "INVALID_REQUEST",
            title=(
                "Question failed validation"
                if is_question
                else "Request failed validation"
            ),
        )

    @application.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == 401:
            response = _problem(
                request_id=next_request_id(),
                status=401,
                code="OWNER_AUTHENTICATION_REQUIRED",
                title="Owner authentication is required",
            )
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        return _problem(
            request_id=next_request_id(),
            status=error.status_code,
            code="HTTP_ERROR",
            title="The request could not be completed",
        )

    @application.exception_handler(KnowledgeUnavailableError)
    async def knowledge_error(
        _request: Request, _error: KnowledgeUnavailableError
    ) -> JSONResponse:
        return _problem(
            request_id=next_request_id(),
            status=503,
            code="KNOWLEDGE_UNAVAILABLE",
            title="Verified knowledge is temporarily unavailable",
        )

    @application.exception_handler(InsightsUnavailableError)
    async def insights_error(
        _request: Request, _error: InsightsUnavailableError
    ) -> JSONResponse:
        return _problem(
            request_id=next_request_id(),
            status=503,
            code="INSIGHTS_UNAVAILABLE",
            title="Owner insights are temporarily unavailable",
        )

    @application.exception_handler(ModelUnavailableError)
    async def model_error(
        _request: Request, _error: ModelUnavailableError
    ) -> JSONResponse:
        return _problem(
            request_id=next_request_id(),
            status=503,
            code="MODEL_UNAVAILABLE",
            title="Answer generation is temporarily unavailable",
        )

    @application.exception_handler(InvalidModelOutputError)
    async def invalid_model_output(
        _request: Request, _error: InvalidModelOutputError
    ) -> JSONResponse:
        return _problem(
            request_id=next_request_id(),
            status=500,
            code="INVALID_MODEL_OUTPUT",
            title="The generated answer failed validation",
        )

    @application.get("/healthz", tags=["operations"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post(
        "/v1/ask",
        response_model=AskResponse,
        response_model_by_alias=True,
        tags=["answers"],
    )
    def ask(payload: AskRequest) -> AskResponse:
        result = dependencies.answer_question.execute(
            question=payload.question,
            session_id=payload.session_id,
        )
        return AskResponse.from_result(result)

    @application.post(
        "/v1/owner/insights/report",
        response_model=InsightReportResponse,
        response_model_by_alias=True,
        dependencies=[Depends(require_owner)],
        tags=["owner insights"],
    )
    def generate_insight_report(
        payload: InsightReportRequest,
    ) -> InsightReportResponse:
        report = dependencies.generate_insights.execute(
            period_start=payload.period_start,
            period_end=payload.period_end,
        )
        return InsightReportResponse.from_report(report)

    return application


app = create_app()
