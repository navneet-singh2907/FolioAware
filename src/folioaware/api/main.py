"""FastAPI application composition root."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from folioaware.api.dependencies import ApplicationContainer, build_container
from folioaware.api.schemas import AskRequest, AskResponse, ProblemResponse
from folioaware.domain.exceptions import (
    InvalidModelOutputError,
    KnowledgeUnavailableError,
    ModelUnavailableError,
)


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


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    """Create an application using explicit dependencies and no network I/O."""
    dependencies = container or build_container()
    application = FastAPI(
        title="FolioAware",
        summary="A portfolio agent that stays current.",
        version="0.1.0",
    )
    application.state.container = dependencies

    def next_request_id() -> str:
        return dependencies.identifiers.new()

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _problem(
            request_id=next_request_id(),
            status=422,
            code="INVALID_QUESTION",
            title="Question failed validation",
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

    return application


app = create_app()
