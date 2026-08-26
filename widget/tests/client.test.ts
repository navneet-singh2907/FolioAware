import { afterEach, describe, expect, it, vi } from "vitest";

import { FolioAwareClient, FolioAwareClientError } from "../src/client";

function answeredResponse(): Record<string, unknown> {
  return {
    requestId: "request-1",
    answer: "Project Atlas was deployed to Cloud Run.",
    answerStatus: "answered",
    citations: [
      {
        sourceId: "project-atlas",
        title: "Project Atlas",
        url: "/projects/atlas",
      },
    ],
    knowledgeVersion: "knowledge-1",
  };
}

function jsonResponse(
  payload: unknown,
  options: { status?: number; contentType?: string; contentLength?: string } = {},
): Response {
  const headers = new Headers({
    "Content-Type": options.contentType ?? "application/json; charset=utf-8",
  });
  if (options.contentLength !== undefined) {
    headers.set("Content-Length", options.contentLength);
  }
  return new Response(JSON.stringify(payload), {
    status: options.status ?? 200,
    headers,
  });
}

function asFetch(
  implementation: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
): typeof globalThis.fetch {
  return implementation as typeof globalThis.fetch;
}

function expectClientError(error: unknown, code: string): boolean {
  expect(error).toBeInstanceOf(FolioAwareClientError);
  expect((error as FolioAwareClientError).code).toBe(code);
  return true;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("FolioAwareClient", () => {
  it("sends a normalized credential-free request to the fixed endpoint", async () => {
    let capturedInput: RequestInfo | URL | undefined;
    let capturedInit: RequestInit | undefined;
    const fetchImplementation = asFetch(async (input, init) => {
      capturedInput = input;
      capturedInit = init;
      return jsonResponse(answeredResponse());
    });
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation,
    });

    const result = await client.ask("  How   was Atlas deployed?  ", {
      sessionId: "ephemeral-session",
    });

    expect(capturedInput?.toString()).toBe("https://api.example/v1/ask");
    expect(capturedInit?.method).toBe("POST");
    expect(capturedInit?.credentials).toBe("omit");
    expect(capturedInit?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(capturedInit?.body as string)).toEqual({
      question: "How was Atlas deployed?",
      sessionId: "ephemeral-session",
    });
    expect(result.answerStatus).toBe("answered");
  });

  it("omits the optional session identifier", async () => {
    let requestBody = "";
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: asFetch(async (_input, init) => {
        requestBody = init?.body as string;
        return jsonResponse(answeredResponse());
      }),
    });

    await client.ask("How was Atlas deployed?");

    expect(JSON.parse(requestBody)).toEqual({
      question: "How was Atlas deployed?",
    });
  });

  it.each(["", "  ", "ab", "a".repeat(501)])(
    "rejects invalid question %j before fetch",
    async (question) => {
      const fetchImplementation = vi.fn();
      const client = new FolioAwareClient({
        apiBaseUrl: "https://api.example",
        fetchImplementation: fetchImplementation as typeof globalThis.fetch,
      });

      await expect(client.ask(question)).rejects.toSatisfy((error: unknown) =>
        expectClientError(error, "invalid_question"),
      );
      expect(fetchImplementation).not.toHaveBeenCalled();
    },
  );

  it.each(["", "a".repeat(129)])(
    "rejects invalid session identifier before fetch",
    async (sessionId) => {
      const fetchImplementation = vi.fn();
      const client = new FolioAwareClient({
        apiBaseUrl: "https://api.example",
        fetchImplementation: fetchImplementation as typeof globalThis.fetch,
      });

      await expect(
        client.ask("How was Atlas deployed?", { sessionId }),
      ).rejects.toSatisfy((error: unknown) =>
        expectClientError(error, "invalid_session"),
      );
      expect(fetchImplementation).not.toHaveBeenCalled();
    },
  );

  it("accepts a valid knowledge-gap response", async () => {
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: asFetch(async () =>
        jsonResponse({
          ...answeredResponse(),
          answer: "I don't have verified information about that.",
          answerStatus: "knowledge_gap",
          citations: [],
        }),
      ),
    });

    await expect(client.ask("Have they used Kafka?")).resolves.toMatchObject({
      answerStatus: "knowledge_gap",
      citations: [],
    });
  });

  it.each([
    [{ ...answeredResponse(), extra: "unsafe" }, "application/json"],
    [{ ...answeredResponse(), citations: [] }, "application/json"],
    [answeredResponse(), "text/html"],
  ])("rejects malformed or wrongly typed success response", async (payload, type) => {
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: asFetch(async () =>
        jsonResponse(payload, { contentType: type }),
      ),
    });

    await expect(client.ask("How was Atlas deployed?")).rejects.toSatisfy(
      (error: unknown) => expectClientError(error, "invalid_response"),
    );
  });

  it("returns only sanitized status and request ID from a valid problem", async () => {
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: asFetch(async () =>
        jsonResponse(
          {
            type: "https://folioaware.dev/problems/invalid-question",
            title: "Question failed validation",
            status: 422,
            code: "INVALID_QUESTION",
            requestId: "request-2",
          },
          { status: 422, contentType: "application/problem+json" },
        ),
      ),
    });

    await expect(client.ask("How was Atlas deployed?")).rejects.toMatchObject({
      code: "api_error",
      status: 422,
      requestId: "request-2",
      message: "The question could not be completed",
    });
  });

  it("does not expose malformed problem details", async () => {
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: asFetch(async () =>
        jsonResponse(
          { title: "raw vendor exception" },
          { status: 503, contentType: "application/problem+json" },
        ),
      ),
    });

    await expect(client.ask("How was Atlas deployed?")).rejects.toMatchObject({
      code: "api_error",
      status: 503,
      requestId: undefined,
      message: "The question could not be completed",
    });
  });

  it.each(["999999", "not-a-number"])(
    "rejects unsafe declared response length %s",
    async (contentLength) => {
      const client = new FolioAwareClient({
        apiBaseUrl: "https://api.example",
        maxResponseBytes: 256,
        fetchImplementation: asFetch(async () =>
          jsonResponse(answeredResponse(), { contentLength }),
        ),
      });

      await expect(client.ask("How was Atlas deployed?")).rejects.toBeInstanceOf(
        FolioAwareClientError,
      );
    },
  );

  it("stops reading an undeclared response that exceeds the byte limit", async () => {
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      maxResponseBytes: 32,
      fetchImplementation: asFetch(async () => jsonResponse(answeredResponse())),
    });

    await expect(client.ask("How was Atlas deployed?")).rejects.toSatisfy(
      (error: unknown) => expectClientError(error, "response_too_large"),
    );
  });

  it("maps fetch failure to a generic network error", async () => {
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: asFetch(async () => {
        throw new Error("private network detail");
      }),
    });

    await expect(client.ask("How was Atlas deployed?")).rejects.toMatchObject({
      code: "network_error",
      message: "The API could not be reached",
    });
  });

  it("aborts a request after the configured timeout", async () => {
    vi.useFakeTimers();
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      timeoutMs: 10,
      fetchImplementation: asFetch(
        async (_input, init) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            );
          }),
      ),
    });

    const expectation = expect(client.ask("How was Atlas deployed?")).rejects.toSatisfy(
      (error: unknown) => expectClientError(error, "timeout"),
    );
    await vi.advanceTimersByTimeAsync(11);
    await expectation;
  });

  it("maps a stalled response body abort to timeout", async () => {
    vi.useFakeTimers();
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      timeoutMs: 10,
      fetchImplementation: asFetch(async (_input, init) => {
        const body = new ReadableStream({
          start(controller) {
            init?.signal?.addEventListener("abort", () =>
              controller.error(new DOMException("aborted", "AbortError")),
            );
          },
        });
        return new Response(body, {
          headers: { "Content-Type": "application/json" },
        });
      }),
    });

    const expectation = expect(client.ask("How was Atlas deployed?")).rejects.toSatisfy(
      (error: unknown) => expectClientError(error, "timeout"),
    );
    await vi.advanceTimersByTimeAsync(11);
    await expectation;
  });

  it("supports caller cancellation", async () => {
    const caller = new AbortController();
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: asFetch(
        async (_input, init) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            );
          }),
      ),
    });

    const expectation = expect(
      client.ask("How was Atlas deployed?", { signal: caller.signal }),
    ).rejects.toSatisfy((error: unknown) => expectClientError(error, "aborted"));
    caller.abort();
    await expectation;
  });

  it("rejects an already-cancelled request before fetch", async () => {
    const caller = new AbortController();
    caller.abort();
    const fetchImplementation = vi.fn();
    const client = new FolioAwareClient({
      apiBaseUrl: "https://api.example",
      fetchImplementation: fetchImplementation as typeof globalThis.fetch,
    });

    await expect(
      client.ask("How was Atlas deployed?", { signal: caller.signal }),
    ).rejects.toSatisfy((error: unknown) => expectClientError(error, "aborted"));
    expect(fetchImplementation).not.toHaveBeenCalled();
  });

  it("rejects invalid client configuration", () => {
    expect(
      () =>
        new FolioAwareClient({
          apiBaseUrl: "http://api.example",
        }),
    ).toThrow(FolioAwareClientError);
    expect(
      () =>
        new FolioAwareClient({
          apiBaseUrl: "https://api.example",
          timeoutMs: 0,
        }),
    ).toThrow(FolioAwareClientError);
    expect(
      () =>
        new FolioAwareClient({
          apiBaseUrl: "https://api.example",
          maxResponseBytes: 300_000,
        }),
    ).toThrow(FolioAwareClientError);
  });
});
