import { describe, expect, it } from "vitest";

import { buildAskUrl, isSafeCitationUrl } from "../src/url-policy";

describe("buildAskUrl", () => {
  it.each([
    ["https://api.example", "https://api.example/v1/ask"],
    ["https://API.Example:443/", "https://api.example/v1/ask"],
    ["http://localhost:8000", "http://localhost:8000/v1/ask"],
    ["http://127.0.0.1:8000/", "http://127.0.0.1:8000/v1/ask"],
    ["http://[::1]:8000", "http://[::1]:8000/v1/ask"],
  ])("builds the fixed ask path from %s", (baseUrl, expected) => {
    expect(buildAskUrl(baseUrl).toString()).toBe(expected);
  });

  it.each([
    "api.example",
    " https://api.example",
    "https://*.example",
    "http://api.example",
    "ftp://api.example",
    "https://user@api.example",
    "https://api.example/base",
    "https://api.example?debug=true",
    "https://api.example#fragment",
  ])("rejects unsafe or non-origin base URL %s", (baseUrl) => {
    expect(() => buildAskUrl(baseUrl)).toThrow(TypeError);
  });
});

describe("isSafeCitationUrl", () => {
  it.each([
    "/projects/atlas",
    "/projects/atlas?view=full#deployment",
    "https://portfolio.example/projects/atlas",
  ])("accepts safe citation URL %s", (url) => {
    expect(isSafeCitationUrl(url)).toBe(true);
  });

  it.each([
    "",
    " /projects/atlas",
    "//malicious.example/path",
    "/projects\\atlas",
    "javascript:alert(1)",
    "data:text/html,unsafe",
    "http://portfolio.example/project",
    "https://user@portfolio.example/project",
    "https://portfolio.example/unsafe\\path",
    "https://portfolio.example/path\nnext",
  ])("rejects unsafe citation URL %s", (url) => {
    expect(isSafeCitationUrl(url)).toBe(false);
  });
});
