import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from folioaware.domain.knowledge import ApprovedSource, Visibility
from folioaware.evaluation import (
    EvaluationStatus,
    EvaluationSuite,
    EvaluationTag,
    EvaluationValidationError,
    load_evaluation_suite,
)
from folioaware.ingestion import load_approved_sources

SUITE_PATH = Path("evals/fixtures/synthetic-portfolio-v1.yaml")
CONTENT_ROOT = Path("examples/synthetic-portfolio")


def _approved_sources() -> tuple[ApprovedSource, ...]:
    return load_approved_sources(CONTENT_ROOT)


def _suite_mapping() -> dict[str, Any]:
    parsed = yaml.safe_load(SUITE_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _write_suite(tmp_path: Path, value: object, suffix: str = ".yaml") -> Path:
    path = tmp_path / f"suite{suffix}"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def test_loads_balanced_synthetic_release_suite() -> None:
    suite = load_evaluation_suite(
        SUITE_PATH,
        approved_sources=_approved_sources(),
    )

    assert suite.suite_id == "synthetic-portfolio-v1"
    assert len(suite.cases) == 24
    assert (
        sum(case.expected_status is EvaluationStatus.ANSWERED for case in suite.cases)
        == 12
    )
    assert (
        sum(
            case.expected_status is EvaluationStatus.KNOWLEDGE_GAP
            for case in suite.cases
        )
        == 12
    )
    assert all(
        EvaluationTag.ANSWERABLE in case.tags
        for case in suite.cases
        if case.expected_status is EvaluationStatus.ANSWERED
    )
    assert all(
        EvaluationTag.UNANSWERABLE in case.tags
        for case in suite.cases
        if case.expected_status is EvaluationStatus.KNOWLEDGE_GAP
    )


def test_normalizes_question_reference_and_passage_whitespace(tmp_path: Path) -> None:
    value = _suite_mapping()
    case = value["cases"][0]
    case["question"] = "  What   is\nProject Atlas?  "
    case["referenceAnswer"] = "  Project Atlas is an inventory\nforecasting API. "
    case["relevantPassages"][0]["text"] = (
        "Project Atlas is a synthetic inventory forecasting API\n"
        "built with Python and FastAPI."
    )

    suite = load_evaluation_suite(
        _write_suite(tmp_path, value),
        approved_sources=_approved_sources(),
    )

    loaded = suite.cases[0]
    assert loaded.question == "What is Project Atlas?"
    assert loaded.reference_answer == ("Project Atlas is an inventory forecasting API.")
    assert loaded.relevant_passages[0].text.endswith("Python and FastAPI.")


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (
            lambda value: value.update({"unexpectedField": True}),
            "failed contract validation",
        ),
        (
            lambda value: value["cases"].append(value["cases"][0].copy()),
            "failed contract validation",
        ),
        (
            lambda value: value["cases"][12].update(
                {"referenceAnswer": "Unsupported answer"}
            ),
            "failed contract validation",
        ),
        (
            lambda value: value["cases"][0].update(
                {"requiredCitationSourceIds": ["project-lantern"]}
            ),
            "failed contract validation",
        ),
        (
            lambda value: value["cases"][0].update(
                {"tags": ["answerable", "answerable"]}
            ),
            "failed contract validation",
        ),
    ],
)
def test_rejects_invalid_contract_combinations(
    tmp_path: Path,
    mutate: Any,
    expected_message: str,
) -> None:
    value = _suite_mapping()
    mutate(value)

    with pytest.raises(EvaluationValidationError, match=expected_message):
        load_evaluation_suite(
            _write_suite(tmp_path, value),
            approved_sources=_approved_sources(),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["cases"][0]["relevantPassages"][0].update(
            {"sourceId": "Invalid ID"}
        ),
        lambda value: value["cases"][0]["relevantPassages"][0].update({"text": "   "}),
        lambda value: value["cases"][0].update({"caseId": "Invalid ID"}),
        lambda value: value["cases"][0].update({"question": "   "}),
        lambda value: value["cases"][0].update({"referenceAnswer": "   "}),
        lambda value: value["cases"][0].update(
            {"requiredCitationSourceIds": ["project-atlas", "project-atlas"]}
        ),
        lambda value: value["cases"][0].update(
            {"requiredCitationSourceIds": ["Invalid ID"]}
        ),
        lambda value: value["cases"][0]["relevantPassages"].append(
            value["cases"][0]["relevantPassages"][0].copy()
        ),
        lambda value: value["cases"][0].update({"referenceAnswer": None}),
        lambda value: value["cases"][0].update(
            {"relevantPassages": [], "requiredCitationSourceIds": []}
        ),
        lambda value: value["cases"][0].update({"requiredCitationSourceIds": []}),
        lambda value: value["cases"][0].update({"tags": ["unanswerable"]}),
        lambda value: value["cases"][12].update({"referenceAnswer": "Not allowed"}),
        lambda value: value["cases"][12].update(
            {"relevantPassages": value["cases"][0]["relevantPassages"]}
        ),
        lambda value: value["cases"][12].update(
            {"requiredCitationSourceIds": ["project-atlas"]}
        ),
        lambda value: value["cases"][12].update({"tags": ["answerable"]}),
        lambda value: value.update({"suiteId": "Invalid ID"}),
        lambda value: value.update({"description": "   "}),
        lambda value: value["cases"].append(value["cases"][0].copy()),
    ],
)
def test_strict_models_reject_each_invalid_label_shape(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    value = _suite_mapping()
    mutate(value)

    with pytest.raises(ValidationError):
        EvaluationSuite.model_validate(value)


def test_rejects_unknown_source_reference(tmp_path: Path) -> None:
    value = _suite_mapping()
    value["cases"][0]["relevantPassages"][0]["sourceId"] = "unknown-project"
    value["cases"][0]["requiredCitationSourceIds"] = ["unknown-project"]

    with pytest.raises(EvaluationValidationError, match="references an unknown source"):
        load_evaluation_suite(
            _write_suite(tmp_path, value),
            approved_sources=_approved_sources(),
        )


def test_rejects_passage_absent_from_approved_source(tmp_path: Path) -> None:
    value = _suite_mapping()
    value["cases"][0]["relevantPassages"][0]["text"] = (
        "This invented sentence is not approved evidence."
    )

    with pytest.raises(EvaluationValidationError, match="passage is absent"):
        load_evaluation_suite(
            _write_suite(tmp_path, value),
            approved_sources=_approved_sources(),
        )


def test_rejects_non_public_source_reference(tmp_path: Path) -> None:
    sources = _approved_sources()
    private_atlas = sources[0].model_copy(update={"visibility": Visibility.PRIVATE})

    with pytest.raises(EvaluationValidationError, match="non-public source"):
        load_evaluation_suite(
            _write_suite(tmp_path, _suite_mapping()),
            approved_sources=(private_atlas, *sources[1:]),
        )


def test_rejects_duplicate_approved_source_ids(tmp_path: Path) -> None:
    sources = _approved_sources()

    with pytest.raises(EvaluationValidationError, match="source IDs must be unique"):
        load_evaluation_suite(
            _write_suite(tmp_path, _suite_mapping()),
            approved_sources=(*sources, sources[0]),
        )


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        ("- not-a-mapping\n", "must be a mapping"),
        ("cases: [\n", "is malformed"),
        ("!!python/object/apply:os.system ['whoami']\n", "is malformed"),
    ],
)
def test_rejects_unsafe_or_malformed_yaml(
    tmp_path: Path, content: str, expected_message: str
) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(EvaluationValidationError, match=expected_message):
        load_evaluation_suite(path, approved_sources=_approved_sources())


def test_rejects_unsupported_file_type(tmp_path: Path) -> None:
    path = _write_suite(tmp_path, _suite_mapping(), suffix=".toml")

    with pytest.raises(EvaluationValidationError, match="must be JSON or YAML"):
        load_evaluation_suite(path, approved_sources=_approved_sources())


def test_rejects_oversized_suite(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_bytes(b"x" * 1_000_001)

    with pytest.raises(EvaluationValidationError, match="exceeds size limit"):
        load_evaluation_suite(path, approved_sources=_approved_sources())


def test_rejects_non_utf8_suite(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_bytes(b"\xff\xfe")

    with pytest.raises(EvaluationValidationError, match="valid UTF-8"):
        load_evaluation_suite(path, approved_sources=_approved_sources())


def test_loads_json_suite(tmp_path: Path) -> None:
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(_suite_mapping()), encoding="utf-8")

    suite = load_evaluation_suite(path, approved_sources=_approved_sources())

    assert len(suite.cases) == 24


def test_rejects_unreadable_suite_path(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(EvaluationValidationError, match="unable to read"):
        load_evaluation_suite(path, approved_sources=_approved_sources())
