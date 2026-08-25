# ADR-0012: Framework-Independent Portfolio Widget

- Status: Accepted
- Date: 2026-08-25

## Context

FolioAware has a stable public `POST /v1/ask` contract, but an adopter still
has to build the complete visitor interface. The portfolio frontend is hosted
independently from the FastAPI service and may use plain HTML, React, Vue,
Svelte, or another framework. The first client must therefore be portable
without exposing Google credentials or weakening the evidence boundary.

The browser receives untrusted visitor input and untrusted response data. Even
an application-validated answer can contain characters that become dangerous
if a client interprets them as HTML. Citation URLs also require client-side
scheme validation before navigation.

## Options considered

### Native Web Component distributed as an ES module

A custom element works in standards-compliant browsers and can be embedded by
any frontend with one module import and one HTML element. Shadow DOM provides
style isolation. TypeScript, a small build step, and browser-oriented tests add
tooling, but the shipped component needs no framework runtime.

### Hosted iframe application

An iframe gives the strongest CSS and DOM isolation and permits independent
updates. It also requires FolioAware to host and version a second application,
adds cross-origin sizing and accessibility coordination, and makes adopter
branding more difficult. That is premature for a single-repository MVP.

### React component package

A React package is familiar and easy to integrate into React portfolios, but
it makes one framework a prerequisite and introduces peer-version management.
Other adopters would need wrappers or a second implementation.

## Decision

Build a native custom element named `<folio-aware>` in a top-level `widget/`
package. Author it in TypeScript and distribute a browser ES module. The
package has no runtime framework dependency. Its build and test dependencies
are locked independently from the Python application.

The element accepts a required API base URL plus a small allowlist of cosmetic
attributes. It calls only `POST /v1/ask` with JSON. It never receives a Google
credential, owner-report token, WIF value, or Firestore identifier.

The first slice displays one current question and result rather than preserving
a conversation. It creates one random, in-memory session identifier per widget
instance. It stores no question, answer, or identifier in cookies,
`localStorage`, or `sessionStorage`.

The widget owns a deterministic client state machine:

```text
closed <-> idle -> submitting -> answered | knowledge_gap | error
                         ^             |
                         +-------------+
```

Only one request may be active. A replacement submission aborts the previous
request. Requests have a fixed client timeout and all controls have bounded
input lengths consistent with the API contract.

API responses are runtime-validated before display. The widget uses DOM text
properties, not `innerHTML`, Markdown rendering, or template injection, for
questions, answers, errors, citation titles, and source IDs. Citation URLs must
be HTTPS or root-relative. Root-relative citations resolve against the adopter
portfolio document, not the API origin. New-window links use `noopener` and
`noreferrer`.

FastAPI receives an explicit allowlist from
`FOLIOAWARE_ALLOWED_ORIGINS`. The default is empty. CORS allows credentials
`false`, method `POST`, and header `Content-Type`. It does not allow the
`Authorization` header used by the owner endpoint. Wildcard origins are
rejected, and production origins must use HTTPS. Localhost HTTP origins may be
used only outside production.

The component provides a labelled form, keyboard-operable open/close and
submit controls, visible focus styles, status announcements through an ARIA
live region, focus return on close, reduced-motion behavior, and themeable CSS
custom properties with accessible defaults.

## Consequences

- One widget can be embedded in static HTML or framework applications.
- Adopter CSS cannot accidentally restyle internal controls, while documented
  CSS custom properties still permit branding.
- The repository gains a second locked toolchain and CI path; this is justified
  by an independently consumable browser package.
- CORS limits ordinary browser origins but is not authentication, bot
  protection, or a spending limit. Server-side rate and cost controls remain a
  separate requirement before public cloud launch.
- No deployment or npm publication is part of this slice. The local demo uses
  synthetic data and the existing local API.
- A React wrapper can be added later without changing the custom element.

## Revisit when

- browser support requirements exclude native custom elements;
- the widget needs server-rendered content before JavaScript loads;
- multiple widgets on one page need shared state;
- conversation history or streaming becomes a verified product requirement;
- an independently hosted iframe provides a demonstrated security or release
  advantage; or
- a second framework integration proves that the custom-element contract is
  insufficient.
