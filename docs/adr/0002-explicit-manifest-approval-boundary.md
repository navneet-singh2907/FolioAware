# ADR-0002: Explicit manifest approval boundary

- Status: Proposed
- Date: 2026-08-20

## Context

Automatic freshness must not turn arbitrary website content into verified
facts. Adopting developers need readable source files and stable public
citations, while ingestion needs a strict schema.

## Options considered

1. **Scrape the deployed portfolio.** Minimizes authoring, but layout changes,
   duplicated navigation, third-party content, and prompt injection make the
   approval boundary ambiguous.
2. **One strict JSON knowledge file.** Easy to validate and canonicalize, but
   awkward for authors maintaining long-form portfolio content.
3. **A YAML manifest that explicitly lists approved Markdown or structured
   records.** Human-friendly and auditable while allowing validation into one
   canonical typed model. It introduces YAML/parser and path-validation risks.

## Decision

Use a versioned `folioaware.yaml` manifest as the approval boundary. It lists
only repository-relative approved sources and their required public citation
metadata. Sources may be Markdown or structured YAML/JSON, but all are parsed
into the same Pydantic knowledge-source contract before chunking.

A file is verified input only when it is explicitly referenced by a valid
manifest on the synchronized revision. Being public, present in the repository,
or linked from a visitor question is not approval.

## Consequences

- The CLI must reject absolute paths, parent traversal, remote includes,
  duplicate IDs, unsafe YAML tags, missing citation URLs, and unknown schema
  versions.
- The manifest and source bytes participate in deterministic content hashes.
- Git review and branch protection form the human approval step.
- CMS and crawler adapters may be added later only if their output passes the
  same canonical contract and explicit approval gate.

