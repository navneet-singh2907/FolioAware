# Portfolio Widget MVP Plan

## Goal

Prove that an adopter can add an accessible FolioAware question interface to an
independently hosted portfolio without a frontend framework, cloud credential,
or unsafe HTML rendering.

The local demonstration must submit a visitor question to the existing
`POST /v1/ask` endpoint and display either an evidence-grounded answer with
safe citations or the normal `knowledge_gap` outcome.

## Success criteria

The slice is complete when:

1. A plain HTML page can load and configure `<folio-aware>` as an ES module.
2. The widget sends only `question` and an ephemeral `sessionId` to the API.
3. Answered responses render answer text and validated citations.
4. Knowledge gaps render the application-owned abstention without citations.
5. Problem responses, timeouts, offline failures, malformed JSON, and invalid
   success bodies render a generic recoverable error without internal details.
6. No response field is interpreted as HTML.
7. Keyboard navigation, labels, focus management, status announcements, and
   reduced motion pass automated and manual checks.
8. FastAPI returns CORS headers only for explicitly configured origins and does
   not allow credentialed cross-origin requests or the owner authorization
   header.
9. Widget build, formatting, type checks, tests, and the existing Python,
   container, and infrastructure checks pass in CI.
10. No package is published and no cloud resource is created.

## Included scope

- Top-level `widget/` package with its own manifest and reproducible lock.
- Native custom element authored in TypeScript and built as an ES module.
- Shadow DOM styles with documented CSS custom properties.
- Open, idle, submitting, answered, knowledge-gap, and error states.
- One question at a time, 3–500 characters after whitespace normalization.
- In-memory `crypto.randomUUID()` session identifier when supported, with a
  standards-based random fallback that contains no visitor data.
- Bounded fetch timeout and request cancellation.
- Runtime validation of success and problem responses.
- HTTPS and root-relative citation URL validation.
- Synthetic local demonstration page.
- Explicit FastAPI CORS configuration and integration tests.
- Widget unit/component tests and a small real-browser smoke/accessibility test.
- CI, README, threat-model, repository-structure, and environment documentation
  updates.

## Deliberately excluded

- React, Vue, or Svelte wrappers.
- Chat history, model memory, streaming, voice, uploads, feedback, or Markdown.
- Cookies, browser analytics, fingerprinting, or persistent browser storage.
- Owner insights or administrative controls in the widget.
- Google SDKs, API keys, tokens, or Firestore access in browser code.
- CAPTCHA, CDN hosting, npm publication, Cloud Run deployment, Terraform apply,
  or billable infrastructure.
- Multiple themes, localization, rich animations, or a complete design system.
- Server-side rate limiting; it remains a required pre-deployment branch rather
  than a client control.

## Browser/API contract

### Configuration

The element requires an absolute API base URL. Production accepts HTTPS. Local
development may use loopback HTTP. The implementation must normalize one
trailing slash and construct the fixed `/v1/ask` path; callers cannot configure
an arbitrary route.

Cosmetic configuration is limited to safe text attributes and CSS custom
properties. Attribute values are never parsed as HTML or executable code.

### Request

```json
{
  "question": "How was Project Atlas deployed?",
  "sessionId": "ephemeral-random-value"
}
```

The widget normalizes whitespace, blocks invalid lengths before network I/O,
sets `Content-Type: application/json`, sends no cookies, and includes no
authorization header.

### Response

The widget accepts only the documented `AskResponse` shape with:

- non-empty `requestId` and `knowledgeVersion` strings;
- bounded answer text;
- `answerStatus` equal to `answered` or `knowledge_gap`;
- an array of bounded citation objects; and
- no citations for a knowledge gap.

An answered result without citations, an unknown status, an invalid citation
URL, oversized response text, or an unexpected content type fails closed to a
generic error state. The browser does not display raw problem titles or vendor
responses as trusted diagnostic text.

## Accessibility contract

- The launcher has an accessible name and exposes expanded state.
- The dialog/panel has a labelled landmark and does not trap keyboard focus in
  the first slice.
- Every input has a persistent visible label and validation message.
- Submit is disabled only when invalid or submitting; progress is announced.
- Completion and errors use a polite live region without repeatedly reading the
  complete transcript.
- Closing returns focus to the launcher.
- Escape closes the panel when focus is inside it.
- Color is not the only status signal, focus indicators remain visible, and
  animation respects `prefers-reduced-motion`.

## Planned implementation sequence

### Commit 1: Architecture and contract

Record ADR-0012 and this bounded implementation plan. No production behavior
changes.

### Commit 2: Explicit API CORS boundary

Status: implemented on `feature/portfolio-widget`.

Add validated allowed-origin settings, narrowly configured middleware,
environment/Terraform documentation, and integration tests for allowed,
disallowed, wildcard, production-HTTP, preflight, credential, and owner-header
cases.

### Commit 3: Widget toolchain and transport

Status: implemented on `feature/portfolio-widget`.

Create the locked TypeScript package, response validators, URL policy, request
client, state types, and focused tests. Verify that no runtime framework or
credential configuration enters the bundle.

### Commit 4: Accessible custom-element slice

Status: implemented on `feature/portfolio-widget`.

Implement the custom element, plain-text rendering, citations, focus/state
behavior, theming hooks, synthetic demo, and component/browser tests.

### Commit 5: CI, documentation, and adversarial review

Status: implemented on `feature/portfolio-widget`.

Run widget checks in CI, document adopter integration, update the threat model
and repository structure, and verify malicious HTML, bad URLs, malformed
responses, timeouts, rapid submissions, and knowledge gaps.

## Test matrix

### Transport and validation

- Answered and knowledge-gap success bodies.
- `application/problem+json` for validation and dependency failures.
- Timeout, abort, offline rejection, non-JSON, oversized body, and HTTP error.
- Unknown and extra response fields, wrong types, empty IDs, unsupported status,
  answered-without-citation, gap-with-citation, and too many citations.
- HTTPS, root-relative, JavaScript, data, protocol-relative, malformed, and
  cross-origin citation URLs.

### Rendering and interaction

- Text containing tags, entities, bidirectional controls, and injection strings
  remains text and creates no executable node.
- Submit by button and Enter, invalid-length prevention, double-submit abort,
  retry after error, close/reopen, Escape, focus return, and live status.
- Multiple element instances do not share questions, results, or session IDs.
- Adopter styles do not leak through Shadow DOM; documented theme variables do.

### CORS

- Configured origin receives the expected allow-origin response.
- Unknown and `null` origins receive no allow-origin response.
- Wildcards and production HTTP origins fail configuration validation.
- Preflight permits only `POST` and `Content-Type`.
- Credentials are not allowed and `Authorization` is not allowed.
- Same-origin and non-browser API clients remain usable.

## Stop conditions

Stop for explicit direction before:

- publishing a package or hosting widget assets;
- deploying the API or applying Terraform;
- adding visitor tracking, persistent browser storage, cookies, or a third-party
  analytics/error-reporting service;
- adding a frontend framework or an iframe service;
- weakening response validation, URL policy, CORS, or plain-text rendering; or
- expanding into chat memory, streaming, authentication, multi-tenancy, or
  owner administration.
