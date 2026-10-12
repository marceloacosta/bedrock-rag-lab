# Evaluation method

The corpus contains 24 fictional outdoor-store policy articles, totaling 29,023
bytes. The evaluation uses 24 questions: eight direct lookups, eight combining
policies, and eight asking for information the documents do not contain.

## Five versions

| Version | Procedure |
|---|---|
| Three passages | Retrieve three passages and answer. |
| Check the first answer | Give the model its draft and the same three passages for a second answer. |
| Nine passages | Retrieve nine passages and answer. |
| Search agent | Start with three passages; allow up to two additional searches of three passages each. |
| Every document | Supply all 24 complete documents in the answer prompt. |

The first draft of the checking version supplies the three-passage result.
The other versions run independently in a seeded shuffled order. The saved run
contains 96 execution records, 141 model calls, and 120 scored answers.

All versions use GLM 5, temperature zero, a 600-token output limit per call, and
common answer instructions. Customer facts stated in the question are accepted
as scenario facts. The agent additionally receives a search tool and planning
instructions. After the search or model-turn allowance is exhausted, the final
answer uses a fresh prompt with accumulated evidence and the common instructions.
This occurred in nine cases; the viewer identifies them.

Retrieved passages include IDs, source names, rank, and similarity score.
The all-document version supplies IDs, source names, and full text.
Knowledge Bases uses 200-token chunks with 15% overlap, Titan Text Embeddings V2
with 1,024 dimensions, and semantic retrieval over S3 Vectors.

## Choosing the retrieval depth

Eight development questions test depths of 3, 6, 9, and 12. The procedure chooses
the depth with the most complete required-phrase coverage, breaks ties on total
phrase coverage, then prefers the smaller depth. Coverage was 5/8, 7/8, 8/8, and
8/8, respectively, so the recorded setting is nine.

A development gift question resembles an evaluation case. These are known
synthetic cases, with one answer per version and question. Phrase coverage helps
locate evidence; it does not determine whether the answer is correct.

## Scoring

The scoring rules were defined before the model run. AI-assisted review applied
them to the saved answers and evidence. The evaluator had access to the question
set and experiment design. Domain experts should check a sample before using the
same judging process for production decisions.

An answer passes when it:

- Applies the correct policy and calculates amounts correctly.
- Answers every supported part of the question.
- Makes no unsupported material claim.
- Uses citations that support its policy claims.
- Identifies information that cannot be established.

An unresolved contradiction fails even if a correct number also appears.
An explicit correction replacing an earlier calculation can pass. General
inspection or approval conditions are acceptable. Questioning a customer fact
explicitly established in the scenario is not.

For an unanswerable request, identifying the gap and declining to invent the
requested fact can pass. Several policies explicitly state which information is
unavailable, making those cases easier. Citation-ID validation alone does not
prove that a cited passage supports an answer.

The recorded labels are 21, 21, 22, 20, and 22 passes for three passages, checking,
nine passages, the agent, and all documents. One checking answer (m02) identifies
a missing gift-return window but still opens with a definite refund. Accepting
that acknowledgment as sufficient would give checking 22 rather than 21.
The saved judgment fails its unresolved eligibility claim.

## Reading the failures

For m01, the three-passage and checking answers give the correct $113 refund.
The other versions give $107 by subtracting a separately paid delivery charge
again. Repeated nonrefundable-delivery wording is a possible cause, requiring
a separate test.

For m03, the agent receives the store-collection rule but contradicts itself
about when the return window begins. For m06, the agent misses the standard
return window and uses an invalid citation identifier. Correcting only that
citation would leave the unsupported eligibility claim.

## Costs and timings

Model cost is derived from each call's reported input and output tokens at $1/M
input and $3.20/M output. API time sums retrieval and model calls, excluding
identity checks. The shared first draft is counted once in the total evaluation
cost. Embeddings, vector operations, storage, and end-to-end user latency are
outside that token-cost measurement.

The saved requests and responses preserve the actual prompts and evidence.
`tools/verify_results.py` reconciles the packaged data and hashes. Running the
experiment again can produce different answers and timings.
