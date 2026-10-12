# Run the experiment

Use Python 3.10+ on macOS or Linux, AWS CLI 2.32+, and a dedicated AWS account on
an active Free plan. The supplied configuration uses GLM 5 in `us-east-2`.
The runner checks model availability, plan state, identity, and current token
prices before inference.

## Setup

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.json config.local.json
```

Set `expected_account_id` in `config.local.json` to your account ID. That file and
all files under `private/` are ignored by Git. The CLI wrapper uses the isolated
`decodingai-lab` profile, removes ambient AWS settings, and keeps credentials
under `private/`.

For Builder ID accounts, sign in at [AWS Settings](https://settings.aws.com), open
your project's AWS Console, and use that browser for CLI authorization. The
runner requires a non-root principal.

```sh
.venv/bin/python aws-lab.py login
.venv/bin/python tools/run_experiment.py pin
.venv/bin/python tools/run_experiment.py validate
.venv/bin/python tools/run_experiment.py check
```

`pin` verifies your account and saves the expected principal privately. It refuses
to replace an existing, different principal. Renew expired credentials with the
same login command. `validate` checks the corpus and questions without AWS calls.

`check` chooses a new directory under `measurements/runs/` and prints its run ID.
Subsequent commands resume that run. To start a separate run, use
`tools/run_experiment.py --new-run check`; to resume a named run, pass
`--run-id NAME` before the command.

The lab principal needs permission to manage the experiment's S3 bucket, S3
Vectors index, Knowledge Base, and its IAM service role, including `iam:PassRole`,
as well as invoke Bedrock and read plan state. Provisioning creates a scoped role
for Knowledge Bases to read the source bucket and write the vector index.

## Run and clean up

```sh
.venv/bin/python tools/run_experiment.py prepare
.venv/bin/python tools/run_experiment.py pilot
.venv/bin/python tools/run_experiment.py run
.venv/bin/python tools/run_experiment.py cleanup
```

`prepare` provisions the resources, ingests the documents, and selects retrieval
depth from the development questions. `pilot` checks one question through the
four execution flows. `run` evaluates all 24 questions; the first draft of the
checking flow supplies the fifth comparison.

The runner records each attempt before making a model call. Completed attempts
are resumed without another call. Failed or interrupted attempts are preserved
and stop automatic execution. Inputs are hashed when the run begins; changing
them prevents a silent continuation. Preparing an existing run is refused.

A run allows at most $0.65 in model charges and reservations. The shared local
ledger caps total model charges and reservations at $1.70 and 1,200 attempted
calls. Infrastructure is billed separately. The remaining $0.30 of the $2 lab
budget is a planning allowance, not an enforced infrastructure spending cap.
Cleanup is required even after a failed run.

If cleanup reports pending deletion, run it again after the Knowledge Base has
been deleted. It removes only the resources listed in that run's private state.
The recorded dataset in `measurements/recorded/` is never used for new run output.

## Score and report

Prepare review packets from the saved answers:

```sh
.venv/bin/python tools/report.py --run-dir measurements/runs/NAME
```

The command prints a report directory under `results/`. Inspect
`review-packets.json` using the [scoring method](method.md). `review-key.json` maps
packet IDs to answer variants. Create `review.json` in the run directory with
this structure:

```json
{
  "reviewer": "Your evaluation method",
  "blinding": "Describe what the evaluator could see",
  "judgments": [
    {
      "packet_id": "ID_FROM_REVIEW_PACKETS",
      "source_sha256": "HASH_FROM_REVIEW_PACKET",
      "pass": true,
      "reason": "Why this answer meets the scoring rules"
    }
  ]
}
```

Copy `source_sha256` from each review packet. Both the first draft and its
checked answer use the checking record's hash. Supply one judgment
for each of the 120 packets, then run the report command again. It builds
`summary.json`, `trials.json`, `trials.csv`, and `viewer/index.html` in a new
report directory. It does not call an evaluator model or generate judgments.

To regenerate reports from the supplied results, omit `--run-dir`. An optional
`--output-dir` must name a new directory outside `measurements/` and `explorer/`.

## Local checks

```sh
python3 tools/verify_results.py
python3 tools/check_privacy.py
python3 -m unittest discover -s tests
```

The result verifier checks the supplied dataset. Its fixed counts and scores are
not requirements for the output of a new model run.
