// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  defineFolioAwareElement,
  FOLIO_AWARE_TAG_NAME,
  type FolioAwareElement,
} from "../src/component";

function answeredResponse(
  answer = "Project Atlas was deployed to Cloud Run.",
): Record<string, unknown> {
  return {
    requestId: "request-1",
    answer,
    answerStatus: "answered",
    citations: [
      {
        sourceId: "project-atlas",
        title: "Project Atlas",
        url: "https://portfolio.example/projects/atlas",
      },
    ],
    knowledgeVersion: "knowledge-1",
  };
}

function jsonResponse(
  payload: unknown,
  options: { status?: number; contentType?: string } = {},
): Response {
  return new Response(JSON.stringify(payload), {
    status: options.status ?? 200,
    headers: {
      "Content-Type": options.contentType ?? "application/json; charset=utf-8",
    },
  });
}

function attachWidget(
  options: { apiBaseUrl?: string; assistantName?: string } = {},
): FolioAwareElement {
  defineFolioAwareElement();
  const widget = document.createElement(FOLIO_AWARE_TAG_NAME) as FolioAwareElement;
  if (options.apiBaseUrl !== undefined) {
    widget.setAttribute("api-base-url", options.apiBaseUrl);
  }
  if (options.assistantName !== undefined) {
    widget.setAttribute("assistant-name", options.assistantName);
  }
  document.body.append(widget);
  return widget;
}

function shadow(widget: FolioAwareElement): ShadowRoot {
  const root = widget.shadowRoot;
  if (root === null) {
    throw new Error("Expected an open shadow root");
  }
  return root;
}

function query<T extends Element>(widget: FolioAwareElement, selector: string): T {
  const match = shadow(widget).querySelector<T>(selector);
  if (match === null) {
    throw new Error(`Missing component element: ${selector}`);
  }
  return match;
}

function openWidget(widget: FolioAwareElement): void {
  query<HTMLButtonElement>(widget, ".launcher").click();
}

function submitQuestion(widget: FolioAwareElement, question: string): void {
  const input = query<HTMLTextAreaElement>(widget, ".question");
  input.value = question;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  query<HTMLFormElement>(widget, ".form").dispatchEvent(
    new SubmitEvent("submit", { bubbles: true, cancelable: true }),
  );
}

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("FolioAwareElement", () => {
  it("exposes labelled open and closed states and returns focus on Escape", () => {
    const widget = attachWidget({ assistantName: "  Alex's   assistant  " });
    const launcher = query<HTMLButtonElement>(widget, ".launcher");
    const panel = query<HTMLElement>(widget, ".panel");
    const input = query<HTMLTextAreaElement>(widget, ".question");

    expect(launcher.textContent).toBe("Ask Alex's assistant");
    expect(launcher.getAttribute("aria-expanded")).toBe("false");
    expect(panel.hidden).toBe(true);
    expect(panel.getAttribute("role")).toBe("dialog");
    expect(panel.getAttribute("aria-modal")).toBe("false");
    expect(panel.getAttribute("aria-labelledby")).toBe(
      query<HTMLHeadingElement>(widget, ".heading").id,
    );
    expect(input.labels?.item(0)?.textContent).toBe("Ask about this portfolio");
    expect(query(widget, ".status").getAttribute("aria-live")).toBe("polite");

    launcher.click();
    expect(panel.hidden).toBe(false);
    expect(launcher.getAttribute("aria-expanded")).toBe("true");
    expect(shadow(widget).activeElement).toBe(input);

    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true, composed: true }),
    );
    expect(panel.hidden).toBe(true);
    expect(launcher.getAttribute("aria-expanded")).toBe("false");
    expect(shadow(widget).activeElement).toBe(launcher);
  });

  it("falls back to the default name when a cosmetic label is invalid", () => {
    const widget = attachWidget({ assistantName: "x".repeat(81) });

    expect(query(widget, ".heading").textContent).toBe("Portfolio assistant");
    widget.setAttribute("assistant-name", "Recruiter Q&A");
    expect(query(widget, ".heading").textContent).toBe("Recruiter Q&A");
  });

  it.each(["", "ab", "x".repeat(501)])(
    "blocks invalid question %j before network access",
    (question) => {
      const fetchImplementation = vi.fn();
      vi.stubGlobal("fetch", fetchImplementation);
      const widget = attachWidget({ apiBaseUrl: "https://api.example" });
      openWidget(widget);

      submitQuestion(widget, question);

      expect(fetchImplementation).not.toHaveBeenCalled();
      expect(query(widget, ".validation").textContent).toContain("between 3 and 500");
      expect(query(widget, ".validation").hasAttribute("hidden")).toBe(false);
      expect(query(widget, ".question").getAttribute("aria-invalid")).toBe("true");
    },
  );

  it("renders answered text and validated citations without interpreting markup", async () => {
    const maliciousLookingAnswer = '<img src=x onerror="globalThis.pwned=true">';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(answeredResponse(maliciousLookingAnswer))),
    );
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });
    openWidget(widget);

    submitQuestion(widget, "How was Atlas deployed?");

    await vi.waitFor(() => {
      expect(query(widget, ".status").textContent).toBe("Answer ready.");
    });
    expect(query(widget, ".answer").textContent).toBe(maliciousLookingAnswer);
    expect(shadow(widget).querySelector("img")).toBeNull();
    expect(shadow(widget).querySelector("script")).toBeNull();
    const link = query<HTMLAnchorElement>(widget, ".sources a");
    expect(link.textContent).toBe("Project Atlas");
    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noopener noreferrer");
    expect(query(widget, ".result").getAttribute("data-status")).toBe("answered");
  });

  it("submits with Enter while preserving Shift+Enter for a newline", async () => {
    const fetchImplementation = vi.fn(async () => jsonResponse(answeredResponse()));
    vi.stubGlobal("fetch", fetchImplementation);
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });
    openWidget(widget);
    const input = query<HTMLTextAreaElement>(widget, ".question");
    input.value = "How was Atlas deployed?";

    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true }),
    );
    expect(fetchImplementation).not.toHaveBeenCalled();

    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await vi.waitFor(() => {
      expect(fetchImplementation).toHaveBeenCalledOnce();
      expect(query(widget, ".form").getAttribute("aria-busy")).toBe("false");
    });
  });

  it("renders a knowledge gap without a source section", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          ...answeredResponse(),
          answer: "I don't have verified information about that.",
          answerStatus: "knowledge_gap",
          citations: [],
        }),
      ),
    );
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });

    submitQuestion(widget, "Has Alex used Kafka?");

    await vi.waitFor(() => {
      expect(query(widget, ".status").textContent).toBe(
        "No verified answer was found.",
      );
    });
    expect(query(widget, ".result").getAttribute("data-status")).toBe("knowledge_gap");
    expect(query(widget, ".sources-heading").hasAttribute("hidden")).toBe(true);
    expect(query(widget, ".sources").hasAttribute("hidden")).toBe(true);
    expect(shadow(widget).querySelectorAll(".sources a")).toHaveLength(0);
  });

  it("shows a generic error without exposing server problem details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            type: "https://folioaware.dev/problems/dependency",
            title: "SECRET_VENDOR_FAILURE",
            status: 503,
            code: "DEPENDENCY_UNAVAILABLE",
            requestId: "request-2",
          },
          { status: 503, contentType: "application/problem+json" },
        ),
      ),
    );
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });

    submitQuestion(widget, "How was Atlas deployed?");

    await vi.waitFor(() => {
      expect(query(widget, ".result").getAttribute("data-status")).toBe("error");
    });
    expect(query(widget, ".answer").textContent).toContain("couldn't complete");
    expect(shadow(widget).textContent).not.toContain("SECRET_VENDOR_FAILURE");
    expect(query(widget, ".submit").hasAttribute("disabled")).toBe(false);
  });

  it("renders a specific recoverable timeout without exposing the exception", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (_input: RequestInfo | URL, init?: RequestInit) =>
          await new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new Error("sensitive timeout detail")),
            );
          }),
      ),
    );
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });
    submitQuestion(widget, "How was Atlas deployed?");

    await vi.advanceTimersByTimeAsync(20_000);

    expect(query(widget, ".answer").textContent).toBe(
      "The request took too long. Please try again.",
    );
    expect(shadow(widget).textContent).not.toContain("sensitive timeout detail");
    expect(query(widget, ".form").getAttribute("aria-busy")).toBe("false");
  });

  it("allows a new attempt after a recoverable API error", async () => {
    const fetchImplementation = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            type: "https://folioaware.dev/problems/dependency",
            title: "Unavailable",
            status: 503,
            code: "DEPENDENCY_UNAVAILABLE",
            requestId: "request-2",
          },
          { status: 503, contentType: "application/problem+json" },
        ),
      )
      .mockResolvedValueOnce(jsonResponse(answeredResponse()));
    vi.stubGlobal("fetch", fetchImplementation);
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });

    submitQuestion(widget, "How was Atlas deployed?");
    await vi.waitFor(() => {
      expect(query(widget, ".result").getAttribute("data-status")).toBe("error");
    });
    submitQuestion(widget, "How was Atlas deployed?");

    await vi.waitFor(() => {
      expect(query(widget, ".result").getAttribute("data-status")).toBe("answered");
    });
    expect(fetchImplementation).toHaveBeenCalledTimes(2);
  });

  it("reports invalid configuration without attempting a request", async () => {
    const fetchImplementation = vi.fn();
    vi.stubGlobal("fetch", fetchImplementation);
    const widget = attachWidget();

    submitQuestion(widget, "How was Atlas deployed?");

    await vi.waitFor(() => {
      expect(query(widget, ".answer").textContent).toContain("not configured");
    });
    expect(fetchImplementation).not.toHaveBeenCalled();
  });

  it("replaces rapid submissions and aborts the active request when closed", async () => {
    const capturedSignals: AbortSignal[] = [];
    const fetchImplementation = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        const capturedSignal = init?.signal;
        if (capturedSignal === null || capturedSignal === undefined) {
          throw new Error("Expected a request signal");
        }
        capturedSignals.push(capturedSignal);
        return await new Promise<Response>((_resolve, reject) => {
          capturedSignal.addEventListener("abort", () => reject(new Error("aborted")));
        });
      },
    );
    vi.stubGlobal("fetch", fetchImplementation);
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });
    openWidget(widget);
    submitQuestion(widget, "How was Atlas deployed?");
    submitQuestion(widget, "Can this replace the active request?");

    await vi.waitFor(() => expect(capturedSignals).toHaveLength(2));
    expect(fetchImplementation).toHaveBeenCalledTimes(2);
    expect(capturedSignals[0]?.aborted).toBe(true);
    expect(capturedSignals[1]?.aborted).toBe(false);
    query<HTMLButtonElement>(widget, ".close").click();

    expect(capturedSignals[1]?.aborted).toBe(true);
    expect(query<HTMLElement>(widget, ".panel").hidden).toBe(true);
    expect(query(widget, ".result").hasAttribute("hidden")).toBe(true);
    expect(query(widget, ".submit").hasAttribute("disabled")).toBe(false);
  });

  it("cancels work when disconnected and remains reusable after reconnection", async () => {
    let firstSignal: AbortSignal | undefined;
    const fetchImplementation = vi
      .fn()
      .mockImplementationOnce(async (_input: RequestInfo | URL, init?: RequestInit) => {
        firstSignal = init?.signal ?? undefined;
        return await new Promise<Response>((_resolve, reject) => {
          firstSignal?.addEventListener("abort", () => reject(new Error("aborted")));
        });
      })
      .mockResolvedValueOnce(jsonResponse(answeredResponse()));
    vi.stubGlobal("fetch", fetchImplementation);
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });
    submitQuestion(widget, "How was Atlas deployed?");
    await vi.waitFor(() => expect(firstSignal).toBeDefined());

    widget.remove();

    expect(firstSignal?.aborted).toBe(true);
    expect(query(widget, ".submit").hasAttribute("disabled")).toBe(false);
    document.body.append(widget);
    submitQuestion(widget, "How was Atlas deployed?");
    await vi.waitFor(() => {
      expect(query(widget, ".result").getAttribute("data-status")).toBe("answered");
    });
    expect(fetchImplementation).toHaveBeenCalledTimes(2);
  });

  it("keeps state and ephemeral sessions isolated between instances", async () => {
    const requestBodies: Array<Record<string, unknown>> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        requestBodies.push(JSON.parse(init?.body as string) as Record<string, unknown>);
        return jsonResponse(answeredResponse());
      }),
    );
    const first = attachWidget({ apiBaseUrl: "https://api.example" });
    const second = attachWidget({ apiBaseUrl: "https://api.example" });

    submitQuestion(first, "How was Atlas deployed?");
    submitQuestion(second, "What did Atlas use?");

    await vi.waitFor(() => {
      expect(requestBodies).toHaveLength(2);
      expect(query(first, ".answer").textContent).toContain("Cloud Run");
      expect(query(second, ".answer").textContent).toContain("Cloud Run");
    });
    expect(requestBodies[0]?.sessionId).not.toBe(requestBodies[1]?.sessionId);
    expect(query(first, ".question")).not.toBe(query(second, ".question"));
  });

  it("uses same-tab navigation for a validated root-relative citation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          ...answeredResponse(),
          citations: [
            {
              sourceId: "project-atlas",
              title: "Project Atlas",
              url: "/projects/atlas",
            },
          ],
        }),
      ),
    );
    const widget = attachWidget({ apiBaseUrl: "https://api.example" });

    submitQuestion(widget, "How was Atlas deployed?");

    await vi.waitFor(() =>
      expect(shadow(widget).querySelector(".sources a")).not.toBeNull(),
    );
    const link = query<HTMLAnchorElement>(widget, ".sources a");
    expect(link.getAttribute("href")).toBe("/projects/atlas");
    expect(link.target).toBe("");
    expect(link.rel).toBe("");
  });
});
