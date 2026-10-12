# Evaluation and production

The recorded scores use a custom runner and AI-assisted review of saved outputs.
The following tools can support recurring evaluation and deployment.

## Evaluate retrieval and answers separately

[Bedrock RAG evaluations](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-kb.html)
accept responses and passages from a custom application through the
bring-your-own-responses option. Prepare a dataset for each version with the same
questions. Keep the exact answers and evidence, including mistakes.

Check whether retrieval supplied the required information, then whether the
answer used it correctly. Bedrock provides
[metrics](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-metrics.html)
for evidence coverage and answer quality. Have policy experts label a sample and
resolve disagreements with the AI evaluator. Keep exact numeric and citation-ID
checks in code.

Use representative customer questions and a separate test set that is not used
for tuning. Repeat runs, compare paired failures, and set acceptable error rates,
latency, and cost before selecting a release.

## Connect trusted business data

Verify customer identity, order ownership, payments, and return history before
approving a refund. Use an existing returns service for a quote where available.
Check the chosen amounts and applicable rules as well as arithmetic: a calculator
will still produce the wrong refund from the wrong inputs.

Enforce document access before text enters a prompt. Record document versions,
handle stale or conflicting policies, bound searches and retries, and provide a
support handoff. Test instructions embedded in retrieved documents and attempts
to access another customer's data.

[Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)
can add content, sensitive-information, and grounding checks. Application code
still owns authorization and business rules.

## Observe the sequence of calls

[AgentCore Evaluations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html)
can assess agent traces, including tool behavior. Configure
[OpenTelemetry delivery and CloudWatch](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/supported-frameworks-telemetry.html)
so a wrong or slow answer can be traced through its searches and model calls.
Keep sensitive content out of routine logs, restrict detailed traces, and set
retention limits.

Measure the full customer wait, retries, and timeouts. Include retrieval,
inference, storage, monitoring, and evaluation in the operating cost. Roll out
changes to limited traffic first and keep a rollback path.

## Choose when to search again

An agent is useful when each result determines the next query.
[AWS's retrieval guidance](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)
recommends standard retrieval for direct lookups and agentic retrieval for
multi-part, comparative, or exploratory questions and evidence across knowledge
bases. Test the extra loop against a well-configured single search on your own
traffic.
