import { FolioAwareClient, FolioAwareClientError } from "./client";
import type { AskResponse, Citation } from "./contracts";
import { createEphemeralSessionId } from "./session";

export const FOLIO_AWARE_TAG_NAME = "folio-aware";

type WidgetPhase = "idle" | "submitting" | "answered" | "knowledge_gap" | "error";

const DEFAULT_ASSISTANT_NAME = "Portfolio assistant";
const MINIMUM_QUESTION_LENGTH = 3;
const MAXIMUM_QUESTION_LENGTH = 500;

let instanceCount = 0;

const HTMLElementBase = (
  typeof globalThis.HTMLElement === "undefined" ? class {} : globalThis.HTMLElement
) as typeof HTMLElement;

function codePointLength(value: string): number {
  return Array.from(value).length;
}

function normalizedQuestion(value: string): string {
  return value.trim().replace(/\s+/gu, " ");
}

function boundedLabel(value: string | null): string {
  if (value === null) {
    return DEFAULT_ASSISTANT_NAME;
  }
  const normalized = value.trim().replace(/\s+/gu, " ");
  return codePointLength(normalized) >= 1 && codePointLength(normalized) <= 80
    ? normalized
    : DEFAULT_ASSISTANT_NAME;
}

function element<K extends keyof HTMLElementTagNameMap>(
  tagName: K,
  className?: string,
): HTMLElementTagNameMap[K] {
  const created = document.createElement(tagName);
  if (className !== undefined) {
    created.className = className;
  }
  return created;
}

const styles = `
  :host {
    --folio-aware-accent: #0f766e;
    --folio-aware-accent-hover: #115e59;
    --folio-aware-background: #ffffff;
    --folio-aware-surface: #f8fafc;
    --folio-aware-text: #172033;
    --folio-aware-muted: #526176;
    --folio-aware-border: #cbd5e1;
    --folio-aware-danger: #b42318;
    --folio-aware-radius: 1rem;
    --folio-aware-shadow: 0 18px 45px rgb(15 23 42 / 22%);
    --folio-aware-z-index: 1000;
    position: fixed;
    right: 1.25rem;
    bottom: 1.25rem;
    z-index: var(--folio-aware-z-index);
    color: var(--folio-aware-text);
    font: 400 1rem/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  *, *::before, *::after { box-sizing: border-box; }
  [hidden] { display: none !important; }

  button, textarea { font: inherit; }

  button:focus-visible,
  textarea:focus-visible,
  a:focus-visible {
    outline: 3px solid #0ea5e9;
    outline-offset: 3px;
  }

  .launcher {
    display: block;
    margin-left: auto;
    border: 0;
    border-radius: 999px;
    padding: 0.75rem 1rem;
    background: var(--folio-aware-accent);
    color: #ffffff;
    box-shadow: var(--folio-aware-shadow);
    cursor: pointer;
    font-weight: 700;
    transition: background-color 160ms ease, transform 160ms ease;
  }

  .launcher:hover { background: var(--folio-aware-accent-hover); }
  .launcher:active { transform: translateY(1px); }

  .panel {
    width: min(23rem, calc(100vw - 2rem));
    max-height: min(38rem, calc(100vh - 6rem));
    margin-bottom: 0.75rem;
    overflow: auto;
    border: 1px solid var(--folio-aware-border);
    border-radius: var(--folio-aware-radius);
    background: var(--folio-aware-background);
    box-shadow: var(--folio-aware-shadow);
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1rem 0.75rem;
    border-bottom: 1px solid var(--folio-aware-border);
  }

  .heading { margin: 0; font-size: 1.05rem; line-height: 1.3; }

  .close {
    width: 2.25rem;
    height: 2.25rem;
    border: 1px solid var(--folio-aware-border);
    border-radius: 999px;
    background: var(--folio-aware-background);
    color: var(--folio-aware-text);
    cursor: pointer;
    font-size: 1.25rem;
    line-height: 1;
  }

  .body { padding: 1rem; }
  .form { display: grid; gap: 0.65rem; }
  .label { font-weight: 700; }

  .question {
    width: 100%;
    min-height: 6.5rem;
    resize: vertical;
    border: 1px solid var(--folio-aware-border);
    border-radius: 0.65rem;
    padding: 0.7rem 0.75rem;
    background: var(--folio-aware-background);
    color: var(--folio-aware-text);
  }

  .question[aria-invalid="true"] { border-color: var(--folio-aware-danger); }
  .validation { margin: 0; color: var(--folio-aware-danger); font-size: 0.875rem; }

  .submit {
    justify-self: start;
    border: 0;
    border-radius: 0.65rem;
    padding: 0.65rem 0.9rem;
    background: var(--folio-aware-accent);
    color: #ffffff;
    cursor: pointer;
    font-weight: 700;
  }

  .submit:hover:not(:disabled) { background: var(--folio-aware-accent-hover); }
  .submit:disabled { cursor: wait; opacity: 0.7; }

  .status {
    min-height: 1.5rem;
    margin: 0.75rem 0 0;
    color: var(--folio-aware-muted);
    font-size: 0.9rem;
  }

  .result {
    margin-top: 0.75rem;
    border-top: 1px solid var(--folio-aware-border);
    padding-top: 0.9rem;
  }

  .result[data-status="knowledge_gap"] {
    border: 1px solid var(--folio-aware-border);
    border-radius: 0.65rem;
    padding: 0.8rem;
    background: var(--folio-aware-surface);
  }

  .answer { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  .sources-heading { margin: 0.9rem 0 0.35rem; font-size: 0.9rem; }
  .sources { margin: 0; padding-left: 1.25rem; }
  .sources li + li { margin-top: 0.3rem; }
  .sources a { color: var(--folio-aware-accent-hover); overflow-wrap: anywhere; }
  .error { color: var(--folio-aware-danger); }

  @media (max-width: 30rem) {
    :host { right: 1rem; bottom: 1rem; left: 1rem; }
    .panel { width: 100%; max-height: calc(100vh - 5.5rem); }
  }

  @media (prefers-reduced-motion: reduce) {
    .launcher { transition: none; }
  }
`;

export class FolioAwareElement extends HTMLElementBase {
  static readonly observedAttributes = ["assistant-name"];

  readonly #launcher: HTMLButtonElement;
  readonly #panel: HTMLElement;
  readonly #heading: HTMLHeadingElement;
  readonly #form: HTMLFormElement;
  readonly #question: HTMLTextAreaElement;
  readonly #validation: HTMLParagraphElement;
  readonly #submit: HTMLButtonElement;
  readonly #status: HTMLParagraphElement;
  readonly #result: HTMLElement;
  readonly #answer: HTMLParagraphElement;
  readonly #sourcesHeading: HTMLHeadingElement;
  readonly #sources: HTMLUListElement;
  #phase: WidgetPhase = "idle";
  #activeRequest: AbortController | undefined;
  #requestSequence = 0;
  #sessionId: string | undefined;

  constructor() {
    super();
    instanceCount += 1;
    const identifier = `folio-aware-${instanceCount}`;
    const root = this.attachShadow({ mode: "open" });

    const style = element("style");
    style.textContent = styles;

    this.#panel = element("section", "panel");
    this.#panel.id = `${identifier}-panel`;
    this.#panel.hidden = true;
    this.#panel.setAttribute("role", "dialog");
    this.#panel.setAttribute("aria-modal", "false");

    const header = element("header", "header");
    this.#heading = element("h2", "heading");
    this.#heading.id = `${identifier}-heading`;
    this.#panel.setAttribute("aria-labelledby", this.#heading.id);

    const close = element("button", "close");
    close.type = "button";
    close.setAttribute("aria-label", "Close portfolio assistant");
    close.textContent = "×";
    header.append(this.#heading, close);

    const body = element("div", "body");
    this.#form = element("form", "form");
    this.#form.noValidate = true;
    const label = element("label", "label");
    label.htmlFor = `${identifier}-question`;
    label.textContent = "Ask about this portfolio";

    this.#question = element("textarea", "question");
    this.#question.id = label.htmlFor;
    this.#question.name = "question";
    this.#question.rows = 4;
    this.#question.required = true;
    this.#question.minLength = MINIMUM_QUESTION_LENGTH;
    this.#question.maxLength = MAXIMUM_QUESTION_LENGTH;
    this.#question.autocomplete = "off";
    this.#question.placeholder = "What would you like to know?";

    this.#validation = element("p", "validation");
    this.#validation.id = `${identifier}-validation`;
    this.#validation.hidden = true;
    this.#question.setAttribute("aria-describedby", this.#validation.id);

    this.#submit = element("button", "submit");
    this.#submit.type = "submit";
    this.#submit.textContent = "Ask question";
    this.#form.append(label, this.#question, this.#validation, this.#submit);

    this.#status = element("p", "status");
    this.#status.id = `${identifier}-status`;
    this.#status.setAttribute("role", "status");
    this.#status.setAttribute("aria-live", "polite");
    this.#status.setAttribute("aria-atomic", "true");

    this.#result = element("section", "result");
    this.#result.hidden = true;
    this.#result.setAttribute("aria-label", "Portfolio answer");
    this.#answer = element("p", "answer");
    this.#sourcesHeading = element("h3", "sources-heading");
    this.#sourcesHeading.textContent = "Sources";
    this.#sources = element("ul", "sources");
    this.#result.append(this.#answer, this.#sourcesHeading, this.#sources);
    body.append(this.#form, this.#status, this.#result);
    this.#panel.append(header, body);

    this.#launcher = element("button", "launcher");
    this.#launcher.type = "button";
    this.#launcher.setAttribute("aria-haspopup", "dialog");
    this.#launcher.setAttribute("aria-expanded", "false");
    this.#launcher.setAttribute("aria-controls", this.#panel.id);

    root.append(style, this.#panel, this.#launcher);
    this.#updateAssistantName();

    this.#launcher.addEventListener("click", () => this.open());
    close.addEventListener("click", () => this.close());
    this.#form.addEventListener("submit", (event) => {
      void this.#handleSubmit(event);
    });
    this.#question.addEventListener("input", () => this.#clearValidation());
    this.#question.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        this.#form.requestSubmit();
      }
    });
    root.addEventListener("keydown", (event) => {
      if (
        event instanceof KeyboardEvent &&
        event.key === "Escape" &&
        !this.#panel.hidden
      ) {
        event.preventDefault();
        this.close();
      }
    });
  }

  attributeChangedCallback(name: string): void {
    if (name === "assistant-name" && this.#heading !== undefined) {
      this.#updateAssistantName();
    }
  }

  disconnectedCallback(): void {
    if (this.#activeRequest !== undefined) {
      this.#requestSequence += 1;
      this.#activeRequest.abort();
      this.#activeRequest = undefined;
      this.#setBusy(false);
      this.#setPhase("idle");
      this.#clearResult();
      this.#status.textContent = "";
    }
  }

  open(): void {
    this.#panel.hidden = false;
    this.#launcher.setAttribute("aria-expanded", "true");
    this.#question.focus();
  }

  close(): void {
    if (this.#activeRequest !== undefined) {
      this.#requestSequence += 1;
      this.#activeRequest.abort();
      this.#activeRequest = undefined;
      this.#setBusy(false);
      this.#setPhase("idle");
      this.#clearResult();
      this.#status.textContent = "";
    }
    this.#panel.hidden = true;
    this.#launcher.setAttribute("aria-expanded", "false");
    this.#launcher.focus();
  }

  #updateAssistantName(): void {
    const assistantName = boundedLabel(this.getAttribute("assistant-name"));
    this.#heading.textContent = assistantName;
    this.#launcher.textContent = `Ask ${assistantName}`;
  }

  #setPhase(phase: WidgetPhase): void {
    this.#phase = phase;
    this.#result.dataset.status = phase;
  }

  #setBusy(busy: boolean): void {
    this.#question.disabled = busy;
    this.#submit.disabled = busy;
    this.#submit.textContent = busy ? "Checking…" : "Ask question";
    this.#form.setAttribute("aria-busy", busy ? "true" : "false");
  }

  #clearValidation(): void {
    this.#validation.hidden = true;
    this.#validation.textContent = "";
    this.#question.removeAttribute("aria-invalid");
  }

  #showValidation(): void {
    this.#validation.textContent = "Enter a question between 3 and 500 characters.";
    this.#validation.hidden = false;
    this.#question.setAttribute("aria-invalid", "true");
    this.#question.focus();
  }

  #clearResult(): void {
    this.#result.hidden = true;
    this.#answer.textContent = "";
    this.#answer.classList.remove("error");
    this.#sources.replaceChildren();
    this.#sourcesHeading.hidden = true;
    this.#sources.hidden = true;
  }

  #renderCitations(citations: readonly Citation[]): void {
    this.#sources.replaceChildren();
    for (const citation of citations) {
      const item = element("li");
      const link = element("a");
      link.href = citation.url;
      link.textContent = citation.title;
      if (citation.url.startsWith("https://")) {
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      item.append(link);
      this.#sources.append(item);
    }
    this.#sourcesHeading.hidden = citations.length === 0;
    this.#sources.hidden = citations.length === 0;
  }

  #renderResponse(response: AskResponse): void {
    this.#clearResult();
    this.#setPhase(response.answerStatus);
    this.#answer.textContent = response.answer;
    this.#renderCitations(response.citations);
    this.#result.hidden = false;
    this.#status.textContent =
      response.answerStatus === "answered"
        ? "Answer ready."
        : "No verified answer was found.";
  }

  #renderError(error: unknown): void {
    this.#clearResult();
    this.#setPhase("error");
    let message = "I couldn't complete that question. Please try again.";
    if (error instanceof FolioAwareClientError) {
      if (error.code === "timeout") {
        message = "The request took too long. Please try again.";
      } else if (error.code === "invalid_configuration") {
        message = "This portfolio assistant is not configured correctly.";
      }
    }
    this.#answer.textContent = message;
    this.#answer.classList.add("error");
    this.#result.hidden = false;
    this.#status.textContent = "Question could not be completed.";
  }

  async #handleSubmit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (this.#phase === "submitting") {
      this.#requestSequence += 1;
      this.#activeRequest?.abort();
      this.#activeRequest = undefined;
      this.#setBusy(false);
      this.#setPhase("idle");
    }

    this.#clearValidation();
    const question = normalizedQuestion(this.#question.value);
    const length = codePointLength(question);
    if (length < MINIMUM_QUESTION_LENGTH || length > MAXIMUM_QUESTION_LENGTH) {
      this.#showValidation();
      return;
    }

    let client: FolioAwareClient;
    try {
      client = new FolioAwareClient({
        apiBaseUrl: this.getAttribute("api-base-url") ?? "",
      });
      this.#sessionId ??= createEphemeralSessionId();
    } catch (error) {
      this.#renderError(error);
      return;
    }

    this.#clearResult();
    this.#setPhase("submitting");
    this.#setBusy(true);
    this.#status.textContent = "Looking for verified evidence…";
    const requestSequence = ++this.#requestSequence;
    const controller = new AbortController();
    this.#activeRequest = controller;

    try {
      const response = await client.ask(question, {
        sessionId: this.#sessionId,
        signal: controller.signal,
      });
      if (requestSequence === this.#requestSequence) {
        this.#renderResponse(response);
      }
    } catch (error) {
      if (
        requestSequence === this.#requestSequence &&
        !(error instanceof FolioAwareClientError && error.code === "aborted")
      ) {
        this.#renderError(error);
      }
    } finally {
      if (requestSequence === this.#requestSequence) {
        this.#activeRequest = undefined;
        this.#setBusy(false);
      }
    }
  }
}

export function defineFolioAwareElement(
  registry: CustomElementRegistry | undefined = globalThis.customElements,
): void {
  if (registry !== undefined && registry.get(FOLIO_AWARE_TAG_NAME) === undefined) {
    registry.define(FOLIO_AWARE_TAG_NAME, FolioAwareElement);
  }
}
