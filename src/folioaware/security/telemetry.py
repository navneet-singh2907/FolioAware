"""Best-effort telemetry redaction and session pseudonymization."""

import hashlib
import hmac
import re

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)")


class TelemetrySanitizer:
    def __init__(self, secret: str) -> None:
        if len(secret) < 16:
            raise ValueError("session hash secret must be at least 16 characters")
        self._secret = secret.encode("utf-8")
        self._key_id = hashlib.sha256(self._secret).hexdigest()[:8]

    def redact(self, question: str) -> str:
        redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", question)
        return PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)

    def session_hash(self, session_id: str | None) -> str | None:
        if session_id is None:
            return None
        digest = hmac.new(
            self._secret,
            session_id.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"hmac-sha256:{self._key_id}:{digest}"
