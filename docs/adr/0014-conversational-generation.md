# ADR-0014: Conversational answers from retrieved evidence

- Status: Accepted
- Date: 2026-09-05

## Problem and options

The Vertex adapter selected a numbered extract and the application required
substring equality with cited content. That produced snippets, not answers.
Changing temperature alone cannot change that restriction.

1. Keep extraction: lowest generation risk, but cannot answer naturally or
   synthesize multiple passages.
2. Structured, evidence-constrained synthesis: one generation request, natural
   prose, source IDs validated by the application, separate semantic evaluation.
3. Synthesis plus a second model judge per request: extra latency, spend, and
   failure modes; a judge is still not a deterministic proof of truth.

Choose option 2 for this single-turn portfolio assistant. Multi-turn history,
streaming, retrieval changes, new providers, and front-end redesign are excluded.

## Contract and safeguards

The generator returns bounded plain text, `answered` or `knowledge_gap`, and
evidence IDs. Answered responses require citations; abstentions require none.
Unknown/duplicate IDs and malformed output are rejected. Citation titles and
URLs remain application-owned. No tools, external retrieval, or model-supplied
links are enabled. A model abstention uses trusted application text, not free
prose. A parsing failure is an error, not a fabricated knowledge gap or a silent
extractive fallback.

The prompt requests direct answers, useful specifics, synthesis, and clear
limits. Skill listings cannot establish project usage; plans cannot establish
production experience. Questions and evidence cannot override the instructions.
Mixed questions can receive a supported answer with explicit missing details.

The production model remains Gemini 2.5 Flash on Vertex AI using ADC. Its
thinking budget is 256 for these short structured outputs, with 1024 output tokens
and temperature 0.3. Other models retain their default thinking configuration.
This bounds thinking while leaving room for JSON. See
[Google's thinking guidance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking).
There is no additional model call per question; the maximum output allowance
increases from 512 to 1024 tokens. Existing request and concurrency limits remain.

## What is and is not guaranteed

The application guarantees citation provenance and response structure, not
semantic entailment. Correct source IDs do not prove every generated claim is
supported. Prompt injection and hallucinations remain model risks. Substring
checks would defeat paraphrasing without solving contextual misrepresentation.

The existing 24-case offline baseline still tests the local extractive adapter;
it must not be reported as Vertex conversational quality. This revisits ADR-0013
without replacing its historical baseline.

## Release evaluation

`evals/fixtures/conversation-v1.json` defines eight fixed synthetic cases with
human-readable expectations: typo/RAG, broad stack, AWS skill versus project,
missing metric, mixed question, false premise, and question/evidence injection.
Run explicitly (paid, never automatic CI):

```powershell
.venv/Scripts/python.exe evals/run_conversation.py --project YOUR_PROJECT --run-live
```

The runner uses only synthetic evidence, writes no telemetry or cloud state,
and prints prompt/suite digests, model configuration, answers, and latency.
Review every factual claim against supplied evidence, relevance to the question,
coverage, readability, and citation necessity. Any invented fact, harmful
instruction compliance, false project attribution, or malformed output blocks
release. Record the reviewed run separately; passing eight cases is a smoke
gate, not a statistical accuracy or adversarial robustness claim.

Also test the actual published question in the browser after deployment and
verify live citations. Retain the prior immutable image for rollback.
