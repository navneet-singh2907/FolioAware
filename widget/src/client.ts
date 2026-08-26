import {
  parseAskResponse,
  parseProblemResponse,
  ResponseContractError,
  type AskResponse,
} from "./contracts";
import { buildAskUrl } from "./url-policy";

const DEFAULT_TIMEOUT_MS = 20_000;
const DEFAULT_MAX_RESPONSE_BYTES = 65_536;

export type ClientErrorCode =
  | "invalid_configuration"
  | "invalid_question"
  | "invalid_session"
  | "timeout"
  | "aborted"
  | "network_error"
  | "api_error"
  | "invalid_response"
  | "response_too_large";

export class FolioAwareClientError extends Error {
  override readonly name = "FolioAwareClientError";
  readonly status?: number;
  readonly requestId?: string;

  constructor(
    readonly code: ClientErrorCode,
    message: string,
    options: { cause?: unknown; status?: number; requestId?: string } = {},
  ) {
    super(message, { cause: options.cause });
    if (options.status !== undefined) {
      this.status = options.status;
    }
    if (options.requestId !== undefined) {
      this.requestId = options.requestId;
    }
  }
}

export interface FolioAwareClientOptions {
  readonly apiBaseUrl: string;
  readonly timeoutMs?: number;
  readonly maxResponseBytes?: number;
  readonly fetchImplementation?: typeof globalThis.fetch;
}

export interface AskOptions {
  readonly sessionId?: string;
  readonly signal?: AbortSignal;
}

function codePointLength(value: string): number {
  return Array.from(value).length;
}

function normalizeQuestion(question: string): string {
  const normalized = question.trim().replace(/\s+/gu, " ");
  const length = codePointLength(normalized);
  if (length < 3 || length > 500) {
    throw new FolioAwareClientError(
      "invalid_question",
      "Question must contain between 3 and 500 characters",
    );
  }
  return normalized;
}

function validateSessionId(sessionId: string | undefined): void {
  if (sessionId === undefined) {
    return;
  }
  const length = codePointLength(sessionId);
  if (length < 1 || length > 128) {
    throw new FolioAwareClientError(
      "invalid_session",
      "Session identifier failed validation",
    );
  }
}

function mediaType(response: Response): string {
  return (
    response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() ?? ""
  );
}

async function readBoundedText(
  response: Response,
  maximumBytes: number,
): Promise<string> {
  const declaredLength = response.headers.get("content-length");
  if (declaredLength !== null) {
    if (!/^\d+$/.test(declaredLength)) {
      throw new FolioAwareClientError(
        "invalid_response",
        "API returned an invalid response",
      );
    }
    if (Number(declaredLength) > maximumBytes) {
      throw new FolioAwareClientError(
        "response_too_large",
        "API response exceeded the allowed size",
      );
    }
  }

  if (response.body === null) {
    return "";
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let byteCount = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      byteCount += value.byteLength;
      if (byteCount > maximumBytes) {
        await reader.cancel().catch(() => undefined);
        throw new FolioAwareClientError(
          "response_too_large",
          "API response exceeded the allowed size",
        );
      }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } catch (error) {
    if (error instanceof FolioAwareClientError) {
      throw error;
    }
    throw new FolioAwareClientError(
      "invalid_response",
      "API returned an invalid response",
      { cause: error },
    );
  } finally {
    reader.releaseLock();
  }
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    throw new FolioAwareClientError(
      "invalid_response",
      "API returned an invalid response",
      { cause: error },
    );
  }
}

export class FolioAwareClient {
  readonly #askUrl: URL;
  readonly #timeoutMs: number;
  readonly #maxResponseBytes: number;
  readonly #fetch: typeof globalThis.fetch;

  constructor(options: FolioAwareClientOptions) {
    try {
      this.#askUrl = buildAskUrl(options.apiBaseUrl);
    } catch (error) {
      throw new FolioAwareClientError(
        "invalid_configuration",
        "API configuration failed validation",
        { cause: error },
      );
    }

    this.#timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.#maxResponseBytes = options.maxResponseBytes ?? DEFAULT_MAX_RESPONSE_BYTES;
    if (
      !Number.isInteger(this.#timeoutMs) ||
      this.#timeoutMs < 1 ||
      this.#timeoutMs > 60_000
    ) {
      throw new FolioAwareClientError(
        "invalid_configuration",
        "Request timeout failed validation",
      );
    }
    if (
      !Number.isInteger(this.#maxResponseBytes) ||
      this.#maxResponseBytes < 1 ||
      this.#maxResponseBytes > 262_144
    ) {
      throw new FolioAwareClientError(
        "invalid_configuration",
        "Response limit failed validation",
      );
    }
    this.#fetch = options.fetchImplementation ?? globalThis.fetch.bind(globalThis);
  }

  async ask(question: string, options: AskOptions = {}): Promise<AskResponse> {
    const normalizedQuestion = normalizeQuestion(question);
    validateSessionId(options.sessionId);
    if (options.signal?.aborted) {
      throw new FolioAwareClientError("aborted", "Request was cancelled");
    }

    const controller = new AbortController();
    let timedOut = false;
    const abortFromCaller = (): void => controller.abort();
    options.signal?.addEventListener("abort", abortFromCaller, { once: true });
    const timeout = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.#timeoutMs);

    try {
      const body: { question: string; sessionId?: string } = {
        question: normalizedQuestion,
      };
      if (options.sessionId !== undefined) {
        body.sessionId = options.sessionId;
      }
      const response = await this.#fetch(this.#askUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "omit",
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      const expectedMediaType = response.ok
        ? "application/json"
        : "application/problem+json";
      if (mediaType(response) !== expectedMediaType) {
        await response.body?.cancel();
        throw new FolioAwareClientError(
          response.ok ? "invalid_response" : "api_error",
          response.ok
            ? "API returned an invalid response"
            : "The question could not be completed",
          { status: response.status },
        );
      }

      const payload = parseJson(
        await readBoundedText(response, this.#maxResponseBytes),
      );
      if (!response.ok) {
        let requestId: string | undefined;
        try {
          requestId = parseProblemResponse(payload, response.status).requestId;
        } catch (error) {
          if (!(error instanceof ResponseContractError)) {
            throw error;
          }
        }
        throw new FolioAwareClientError(
          "api_error",
          "The question could not be completed",
          {
            status: response.status,
            ...(requestId === undefined ? {} : { requestId }),
          },
        );
      }

      try {
        return parseAskResponse(payload);
      } catch (error) {
        if (!(error instanceof ResponseContractError)) {
          throw error;
        }
        throw new FolioAwareClientError(
          "invalid_response",
          "API returned an invalid response",
          { cause: error },
        );
      }
    } catch (error) {
      if (timedOut) {
        throw new FolioAwareClientError("timeout", "Request timed out", {
          cause: error,
        });
      }
      if (options.signal?.aborted || controller.signal.aborted) {
        throw new FolioAwareClientError("aborted", "Request was cancelled", {
          cause: error,
        });
      }
      if (error instanceof FolioAwareClientError) {
        throw error;
      }
      throw new FolioAwareClientError("network_error", "The API could not be reached", {
        cause: error,
      });
    } finally {
      globalThis.clearTimeout(timeout);
      options.signal?.removeEventListener("abort", abortFromCaller);
    }
  }
}
