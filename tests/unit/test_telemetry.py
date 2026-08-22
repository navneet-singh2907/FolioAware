from folioaware.security import TelemetrySanitizer


def test_redacts_email_and_phone_and_pseudonymizes_session() -> None:
    sanitizer = TelemetrySanitizer("test-secret-at-least-16-characters")

    redacted = sanitizer.redact(
        "Email person@example.com or call +1 (317) 555-0199 about FastAPI"
    )
    first_hash = sanitizer.session_hash("browser-session")

    assert "person@example.com" not in redacted
    assert "317" not in redacted
    assert redacted.count("[REDACTED_") == 2
    assert first_hash == sanitizer.session_hash("browser-session")
    assert first_hash != TelemetrySanitizer(
        "a-different-test-secret-value"
    ).session_hash("browser-session")
    assert sanitizer.session_hash(None) is None


def test_rejects_weak_session_hash_secret() -> None:
    try:
        TelemetrySanitizer("too-short")
    except ValueError as error:
        assert "at least 16" in str(error)
    else:
        raise AssertionError("weak secrets must be rejected")
