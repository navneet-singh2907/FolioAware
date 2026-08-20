# ADR-0005: Evidence-gated generation and application-owned citations

- Status: Proposed
- Date: 2026-08-20

## Context

The model is useful for synthesis but cannot be trusted to decide whether a
claim is verified or to invent citation targets. Retrieved content can itself
contain adversarial instructions.

## Options considered

1. **Let the model retrieve and cite freely.** Flexible, but sources and
   thresholds are opaque and citation fabrication is difficult to prevent.
2. **Generate prose and add citations afterward by similarity.** Produces neat
   responses, but can attach evidence that does not actually support a claim.
3. **Gate evidence first and constrain the model to retrieved evidence IDs.**
   More validation work, but creates enforceable provenance and abstention.

## Decision

The application retrieves a bounded evidence set from the active version and
applies deterministic sufficiency rules before generation. If insufficient, it
returns an application-authored abstention without calling the generation
model.

If sufficient, Vertex AI receives the question, delimited evidence, and an
instruction that evidence text is data rather than instructions. It must return
a structured candidate answer referencing only supplied evidence IDs. The
application validates the schema, ID membership, active version, public
visibility, and citation metadata. Any failure becomes a safe error or
abstention, never an uncited answer.

## Consequences

- Source selection and citation objects are application-owned.
- Structured model output improves parsing but does not replace validation.
- Model, prompt, response-schema, evidence-policy, and knowledge versions must
  be observable for evaluation and incident analysis.
- The MVP will evaluate answer coverage, abstention correctness, citation
  validity, and prompt-injection resistance.
- Claim-level entailment checking may be added later, but cannot weaken the
  evidence-ID membership checks.

