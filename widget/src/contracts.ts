import { isSafeCitationUrl } from "./url-policy";

export type AnswerStatus = "answered" | "knowledge_gap";

export interface Citation {
  readonly sourceId: string;
  readonly title: string;
  readonly url: string;
}

export interface AskResponse {
  readonly requestId: string;
  readonly answer: string;
  readonly answerStatus: AnswerStatus;
  readonly citations: readonly Citation[];
  readonly knowledgeVersion: string;
}

export interface ProblemResponse {
  readonly type: string;
  readonly title: string;
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
}

export class ResponseContractError extends Error {
  override readonly name = "ResponseContractError";
}

function failContract(): never {
  throw new ResponseContractError("Response did not match the public contract");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return actual.length === expected.length && expected.every((key) => key in value);
}

function isBoundedString(
  value: unknown,
  minimum: number,
  maximum: number,
): value is string {
  if (typeof value !== "string") {
    return false;
  }
  const length = Array.from(value).length;
  return length >= minimum && length <= maximum;
}

function parseCitation(value: unknown): Citation {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["sourceId", "title", "url"]) ||
    !isBoundedString(value.sourceId, 1, 100) ||
    !isBoundedString(value.title, 1, 120) ||
    !isBoundedString(value.url, 1, 2048) ||
    !isSafeCitationUrl(value.url)
  ) {
    return failContract();
  }
  return {
    sourceId: value.sourceId,
    title: value.title,
    url: value.url,
  };
}

export function parseAskResponse(value: unknown): AskResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "requestId",
      "answer",
      "answerStatus",
      "citations",
      "knowledgeVersion",
    ]) ||
    !isBoundedString(value.requestId, 1, 100) ||
    !isBoundedString(value.answer, 1, 2000) ||
    (value.answerStatus !== "answered" && value.answerStatus !== "knowledge_gap") ||
    !Array.isArray(value.citations) ||
    value.citations.length > 5 ||
    !isBoundedString(value.knowledgeVersion, 1, 100)
  ) {
    return failContract();
  }

  const citations = value.citations.map(parseCitation);
  if (
    (value.answerStatus === "answered" && citations.length === 0) ||
    (value.answerStatus === "knowledge_gap" && citations.length !== 0)
  ) {
    return failContract();
  }

  return {
    requestId: value.requestId,
    answer: value.answer,
    answerStatus: value.answerStatus,
    citations,
    knowledgeVersion: value.knowledgeVersion,
  };
}

export function parseProblemResponse(
  value: unknown,
  expectedStatus: number,
): ProblemResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["type", "title", "status", "code", "requestId"]) ||
    !isBoundedString(value.type, 1, 2048) ||
    !isBoundedString(value.title, 1, 200) ||
    !Number.isInteger(value.status) ||
    value.status !== expectedStatus ||
    !isBoundedString(value.code, 1, 100) ||
    !/^[A-Z0-9_]+$/.test(value.code) ||
    !isBoundedString(value.requestId, 1, 100)
  ) {
    return failContract();
  }

  return {
    type: value.type,
    title: value.title,
    status: value.status,
    code: value.code,
    requestId: value.requestId,
  };
}
