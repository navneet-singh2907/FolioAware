import { describe, expect, it } from "vitest";

import {
  parseAskResponse,
  parseProblemResponse,
  ResponseContractError,
} from "../src/contracts";

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

describe("parseAskResponse", () => {
  it("accepts an exact answered response", () => {
    expect(parseAskResponse(answeredResponse())).toEqual(answeredResponse());
  });

  it("accepts a knowledge gap without citations", () => {
    const response = {
      ...answeredResponse(),
      answer: "I don't have verified information about that.",
      answerStatus: "knowledge_gap",
      citations: [],
    };

    expect(parseAskResponse(response)).toEqual(response);
  });

  it.each([
    { ...answeredResponse(), extra: true },
    { ...answeredResponse(), answerStatus: "partial" },
    { ...answeredResponse(), citations: [] },
    {
      ...answeredResponse(),
      answerStatus: "knowledge_gap",
    },
    {
      ...answeredResponse(),
      citations: [
        {
          sourceId: "project-atlas",
          title: "Project Atlas",
          url: "javascript:alert(1)",
        },
      ],
    },
    {
      ...answeredResponse(),
      citations: Array.from({ length: 6 }, () => ({
        sourceId: "project-atlas",
        title: "Project Atlas",
        url: "/projects/atlas",
      })),
    },
    { ...answeredResponse(), answer: "a".repeat(2001) },
  ])("rejects a response outside the exact contract", (response) => {
    expect(() => parseAskResponse(response)).toThrow(ResponseContractError);
  });
});

describe("parseProblemResponse", () => {
  const problem = {
    type: "https://folioaware.dev/problems/invalid-question",
    title: "Question failed validation",
    status: 422,
    code: "INVALID_QUESTION",
    requestId: "request-2",
  };

  it("accepts an exact problem matching the HTTP status", () => {
    expect(parseProblemResponse(problem, 422)).toEqual(problem);
  });

  it.each([
    [{ ...problem, status: 500 }, 422],
    [{ ...problem, code: "invalid-question" }, 422],
    [{ ...problem, detail: "internal" }, 422],
  ])("rejects malformed or mismatched problem response", (value, status) => {
    expect(() => parseProblemResponse(value, status)).toThrow(ResponseContractError);
  });
});
