# PROJECT_MGT.md - World-Class Goal-to-Result Rules

Updated: 2026-08-31 11:45 EDT
Owner: Hermes. Applies to EPIC Transcript Machine immediately and to future Epic build projects unless superseded.

## Prime directive

Hermes owns the result until RAD: Reviewed, Approved when required, Delivered with proof. A project is not done because a message was sent, a worker was assigned, a build passed, or a link exists. It is done only when the acceptance gates are proven and the proof is written down.

## Version lanes run in parallel

Do not pause later phases just because an earlier phase is not fully cleared. Run independent lanes at the same time.

- Version 1 / Phase 1: Bulletproof YouTube transcripts.
- Version 2 / Phase 2: Any video or audio.
- Version 3 / Phase 3: Video intelligence.

Each lane has its own owner, tests, evidence, blockers, and exact next action. If work can move without another lane, it moves.

## Always-on execution loop

Every active project cycle must do all of this:

1. Read `PROJECT_STATE.md`, `ACCEPTANCE_TESTS.md`, open task list, live URLs, and latest test results.
2. Pick the highest-value unblocked action in every independent lane.
3. Dispatch agents for parallel lanes instead of serializing work behind one person.
4. Make a concrete change or run a concrete verification.
5. Record proof in `PROJECT_STATE.md` and, when gate evidence changes, `ACCEPTANCE_TESTS.md`.
6. Report status in the origin thread in Version 1 / Version 2 / Version 3 format.
7. Schedule or confirm the next autonomous cycle. Never rely on Trevor pinging again.

## Status cadence

- Active build sprint: status every 10 minutes minimum until all lanes are either moving, blocked, or complete.
- Stable watchdog after release: health alert only when broken, plus scheduled summaries if requested.
- Every update must say: what moved, what is next, blocker if any, ETA or next check time, and proof link/output.

## Red-flag blocker rules

A blocker is not a reason to stop the project. It is a routing event.

When blocked:

1. Name the exact owner: Trevor, Len, Fizz, Honey, Hermes, Jesus, Midas, QC, or external provider.
2. State the exact object needed: credential, approval, account access, source file, legal/content decision, or irreversible architecture choice.
3. State the safe fallback path that continues without the blocker.
4. Ping the owner immediately.
5. Continue every other lane.
6. Re-ping on the project cadence until cleared or replaced by a better path.

## Three-strike cutoff

Do not burn credits forever on an impossible path.

For the same failure mode:

- Strike 1: retry once after reading the error and adjusting the hypothesis.
- Strike 2: try one different implementation path or provider path.
- Strike 3: stop that path. Write the failure evidence, name the root cause if known, and choose one:
  - alternate technical path,
  - human escalation,
  - architecture change proposal,
  - explicit de-scope recommendation.

Never attempt Strike 4 without documenting why the architecture changed.

## Evidence standards

A claim must have proof.

Acceptable proof:
- public URL returned HTTP 200 anonymously with expected markers,
- API returned HTTP 200/202 and credible nonempty result,
- transcript has nonempty credible beginning, middle/ending when relevant, timestamps, word count, and provider path,
- downloads return HTTP 200 with expected content type/bytes,
- automated tests pass,
- screenshot/visual evidence for UI work,
- readback after deletes/writes/external mutations.

Not acceptable proof:
- “I built it,”
- “the code looks right,”
- local-only proof for a public-release gate,
- cached repeat pretending to be an independent fallback,
- a 422 helpful error counted as transcript success.

## Agent routing rules

Use enough agents to keep work moving:

- Hermes: owns orchestration, integration, proof, final reporting.
- Jesus: build/code/deploy/infrastructure.
- Midas: metrics, performance, release evidence, cost/risk analysis.
- Honey: research, product patterns, workflow recommendations, external options.
- QC: independent verification only. QC does not build the work it checks.
- Fizz: project manager/status pressure. Fizz keeps the loop honest and escalates blockers.

One task per agent. If there are three independent lanes, spin up three agents. Do not bury all work in one queue.

## Human escalation rules

Ask a human only when needed for:
- credentials or account access,
- money/provider spend approval,
- legal/content rights,
- irreversible client-facing launch,
- top-level brand/naming/strategy decision.

Everything else defaults to GO.

## Release gate rules

A version is release-clear only when:

1. Its acceptance tests are listed in `ACCEPTANCE_TESTS.md`.
2. Each required test has PASS/FAIL/OPEN status.
3. PASS rows include proof.
4. OPEN rows include owner and next action.
5. QC has independently checked the evidence.
6. The public URL works for a no-login visitor.

## Communication format

Use this format every project update:

```text
Version 1 / Phase 1: [status]. Proof: [one line]. Next: [one line].
Version 2 / Phase 2: [status]. Proof: [one line]. Next: [one line].
Version 3 / Phase 3: [status]. Proof: [one line]. Next: [one line].
Blockers: [owner + exact ask, or None].
Next check: [time].
```

Short. Direct. No filler. No silent pauses.
