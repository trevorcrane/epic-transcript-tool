# PROJECT_MGT.md - EPIC Transcript Machine P2R Contract

Updated: 2026-08-31 18:05 EDT
Scope: EPIC Transcript Machine only. This standard does not apply to future EPIC projects unless a human explicitly adopts it for that project.

## Ownership

Fizz is the accountability owner and project manager through independent closure.
Hermes is the engineering owner.

Fizz owns independent public QC disposition. Hermes owns implementation, deployment, and engineering evidence. Hermes cannot mark a release gate done while Fizz QC says that gate is open or failed.

## Prime directive

One owner, one result, one test, one evidence standard, one thread.

A project phase is not done because code changed, a build passed, a link exists, or a server endpoint returned. A phase is done only when the original Trevor gate for that phase passes in the public, no-login product and Fizz posts an independent PASS.

## Original Trevor gates remain authoritative

- Phase 1: every required YouTube case, download, mobile, and accessibility test passes publicly.
- Phase 2: uploads and links work, plus real browser transcription proves both WebGPU and no-WebGPU/WASM paths with credible multilingual transcript output and timestamps.
- Phase 3: every AI output is useful, timestamp-grounded, downloadable, and the 100 assets are genuinely distinct with citations that support the actual claim.
- Whole project: done only after Fizz independently passes all three phases against the public product.

The cron, engineering logs, source checks, HTTP checks, or Hermes status reports must not call Phase 1 or Phase 2 done while Fizz QC shows open browser/mobile or WebGPU/WASM failures.

## Evidence standards

A claim must have proof.

Availability proof:
- A public URL returning HTTP 200 anonymously with expected markers proves that the file or route is available.
- HTTP 200 and source markers do not prove a browser workflow, visual rendering, mobile behavior, accessibility, or a release gate.

Release-gate proof requires the relevant real user workflow:
- browser proof for UI, history, keyboard, accessibility, mobile, and copy/download flows,
- public no-login transcript proof with credible content, timestamps, word count, and provider path,
- first-run and cached-repeat proof where the gate requires both,
- real WebGPU and forced/no-WebGPU WASM browser model runs for Phase 2,
- citation support checks for Phase 3 generated claims,
- screenshots or stable public evidence links for visual work,
- readback after external writes, deletes, or deploys.

Not acceptable proof:
- “I built it,”
- “the code looks right,”
- local-only proof for a public-release gate,
- cached repeat pretending to be an independent fallback,
- a 422 helpful error counted as transcript success,
- server upload success substituted for browser WebGPU/WASM proof,
- timestamps appended to generated copy when the cited segment does not support the claim.

## Always-on execution loop

Every active cycle must inspect current evidence and move the highest-value unblocked action.

1. Read `PROJECT_STATE.md`, `ACCEPTANCE_TESTS.md`, this contract, open tasks, public URLs, and latest Fizz disposition.
2. Inspect active evidence every 10 minutes while the release is under active sprint.
3. Make a concrete engineering change, run a concrete verification, or record that no material evidence changed.
4. Publish only material changes: new deploys, new evidence, a PASS, a QC FAIL, a blocker, a changed ETA, or a route change.
5. Stay quiet when nothing material changed. Mandatory 10-minute channel posts create noise and are not P2R.
6. Keep the cron evidence checks active, but do not use them to spam the channel.

## Fizz reviewer deadline

For every material Hermes milestone:

- Fizz begins inspection within 10 minutes.
- Fizz posts PASS, QC FAIL, or exact still-testing status within 30 minutes.
- Silence after 30 minutes is recorded as a P2R failure, not as approval.

## Blocker and routing rules

A blocker is a routing event, not a reason to stop other unblocked work.

When blocked:
1. Name the exact human/account/system that can clear it.
2. Send one exact ask with the object needed.
3. Do not re-ping humans every cadence.
4. If the ask is not answered, change route, use an authorized backup, or document the blocked path and continue elsewhere.
5. Stay within explicit or clearly implied authorization. Do not use blanket-go defaults.

## Engineering routing rules

Do not route work to invented or unverified roles.

For this project:
- Fizz: accountability owner and independent public QC.
- Hermes: engineering owner, implementation, deployment, evidence collection, and status reporting.
- Human approvers remain as originally assigned by Trevor or the Epic team.

Additional builders/reviewers can only be used when they are real, available, and explicitly authorized for the task.

## Three-route cutoff

For the same failure mode:

- Route 1: retry once after reading the error and adjusting the hypothesis.
- Route 2: try a meaningfully different implementation or verification path.
- Route 3: stop that path, write the evidence, and choose an authorized alternate route, human escalation, architecture change proposal, or de-scope recommendation.

Do not silently attempt a fourth version of the same route.

## Communication format

Only publish when material evidence changes or a required reviewer deadline/status needs posting.

Use this format:

```text
Phase 1: [PASS / QC FAIL / OPEN / STILL TESTING]. Proof: [one line]. Next: [one line].
Phase 2: [PASS / QC FAIL / OPEN / STILL TESTING]. Proof: [one line]. Next: [one line].
Phase 3: [PASS / QC FAIL / OPEN / STILL TESTING]. Proof: [one line]. Next: [one line].
Blockers: [one exact ask, authorized backup route, or None].
Next material check: [time or condition].
```

Short. Direct. No filler. No 10-minute noise when evidence did not change.
