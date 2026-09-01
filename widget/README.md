# FolioAware Widget

The FolioAware widget is a framework-independent custom element for an
independently hosted portfolio. It sends a visitor's question to a FolioAware
API deployment and renders either a cited answer or an explicit knowledge gap.

This package is source-installable for the MVP. It is not published to npm and
the repository does not host its built assets.

## Build and embed

Node.js 22.13 or later is required. Install the exact locked dependency graph
and build the browser module:

```bash
cd widget
npm ci --ignore-scripts --no-audit --no-fund
npm run check
```

Copy `dist/folio-aware.js` to the adopter portfolio's own static assets, then
load and configure the element:

```html
<script type="module" src="/assets/folio-aware.js"></script>

<folio-aware
  api-base-url="https://api.example"
  assistant-name="Portfolio assistant"
></folio-aware>
```

`api-base-url` is required. Production URLs must use HTTPS; loopback HTTP is
accepted for local development. `assistant-name` is optional and accepts 1–80
characters after whitespace normalization.

The API deployment must list the portfolio's exact origin in
`FOLIOAWARE_ALLOWED_ORIGINS`, for example:

```dotenv
FOLIOAWARE_ALLOWED_ORIGINS=["https://portfolio.example"]
```

Do not use `*`. CORS only controls which browser origins can read responses; it
is not authentication, rate limiting, bot protection, or a spending limit.

## Theme

Shadow DOM prevents adopter styles from accidentally changing internal widget
controls. Branding is available through these CSS custom properties:

```css
folio-aware {
  --folio-aware-accent: #0f766e;
  --folio-aware-accent-hover: #115e59;
  --folio-aware-background: #ffffff;
  --folio-aware-surface: #f8fafc;
  --folio-aware-text: #172033;
  --folio-aware-muted: #526071;
  --folio-aware-border: #cbd5e1;
  --folio-aware-danger: #b42318;
  --folio-aware-radius: 1rem;
  --folio-aware-shadow: 0 1rem 2.5rem rgb(15 23 42 / 18%);
  --folio-aware-z-index: 1000;
}
```

Keep sufficient color contrast after overriding the defaults.

## Local demonstration

Start the synthetic local API from the repository root:

```bash
FOLIOAWARE_ALLOWED_ORIGINS='["http://127.0.0.1:4173"]' \
  uv run uvicorn folioaware.api.main:app --reload
```

In another terminal:

```bash
cd widget
npm run build
npm run preview:demo
```

Open `http://127.0.0.1:4173/demo/`. The demo contains fictional portfolio
content only and creates no cloud resource.

## Security and privacy boundary

- The bundle contains no Google SDK, API key, owner token, or browser secret.
- It sends only the normalized question and an ephemeral in-memory session ID.
- It uses no cookies, analytics, browser cache, IndexedDB, or persistent web
  storage.
- API data is runtime-validated and bounded before rendering.
- Answers and labels are written as text, never interpreted as HTML or
  Markdown.
- Citations must be HTTPS or root-relative; invalid responses fail closed.
- A semantic answer cache is intentionally absent because stale answers could
  outlive a corrected or removed knowledge version.

The browser never decides what is verified evidence. That policy remains in
the API, and visitor questions or generated answers never become portfolio
facts.

## Tests and browser support

```bash
npm run check
npm run test:browser
```

`check` runs formatting, linting, strict TypeScript checks, unit/component
coverage, a production build, and bundle policy verification. The browser test
loads the built module in headless Chromium and checks keyboard focus, mobile
layout, malicious answer text, citations, knowledge gaps, and axe accessibility
rules.

The MVP supports current evergreen browsers with custom elements, open Shadow
DOM, `fetch`, `AbortController`, Web Crypto, and ES2022 module support. Automated
accessibility checks catch common regressions but do not replace keyboard and
screen-reader review in the adopter's real portfolio.
