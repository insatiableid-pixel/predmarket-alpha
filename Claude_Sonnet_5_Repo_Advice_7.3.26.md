The fact that reorganizes all six answers: near-resolution informed flow is the only family blocked by compute rather than calendar. MLB, World Cup, and ATP are gated by how many independent real-world events have happened — no amount of engineering effort makes a baseball game finish faster. Informed flow already has 485 observations, 249 contracts, 306 settlement-label rows, 236 forward-quote pairs sitting idle because no candidate hypothesis has been generated against it yet. That's a today problem, not a wait problem.

Also worth registering before the specifics: your numbers are internally consistent. MLB's 22 + World Cup's 24 + ATP's 10 = 56, matching the stated total deficit exactly. MLB's 8 + World Cup's 6 = 14, matching independent labels counted. The gates are doing real filtering — 58 exact labels producing only 14 independent ones means roughly three-quarters of your genuine settlement data is being correctly excluded as correlated, not padding the count. That's the system working as designed, not a leak.

**1. Next 24–72 hours**

- Generate and falsify a near-resolution informed-flow candidate now. It's the only lever here that isn't rate-limited by the outside world.
- Confirm the ATP probe window fires at 2026-07-04T06:00:00Z and that Wimbledon match volume actually lands the same day. ATP needs only 10 independent labels — the lowest bar of any directional family — against a live tournament resolving matches daily. This is your fastest-closing directional deficit.
- Diagnose the World Cup number. Six independent labels after three-plus weeks and dozens of completed group and Round-of-32 matches is low. Two explanations, two different actions: either the family was instrumented recently and completed matches were never backfilled — pull exact settlement history for every already-resolved World Cup contract via Kalshi's public, unauthenticated settlement data, which stays queryable after the fact — or the dedup logic is correctly excluding correlated contracts on the same match, and the family is genuinely capped near the ~16 knockout matches remaining (R16 through final, July 6–19). If it's the second case, 24 more independent labels may not be reachable from match-winner contracts alone before the tournament ends, and no amount of pressure should change that.
- Start real fill-label accumulation for passive liquidity in paper mode now, if it isn't running already. Proxy labels can't satisfy your own falsification requirement — only actual paper fills can, and that clock only runs while order-resting logic is live.
- Leave crypto alone. Full pipeline, correctly waiting on a candidate. Nothing to fix.

**2. Next 2–4 weeks**

- Treat MLB, World Cup match-winner, and ATP as background processes, not active engineering targets. The lever isn't more code, it's more games. Monitor; don't push.
- Redirect freed capacity to the two fronts that respond to effort: getting the informed-flow candidate(s) from step 1 through OOS/FDR, and letting passive-liquidity fills accumulate toward a real, non-proxy N.
- Resolve the independence definition for World Cup specifically. If "independent" is scored at the outcome level rather than the match level, total-goals and both-teams-to-score are genuinely distinct resolutions from the same matches, not duplicates of match-winner — instrument them now and start a second label clock in parallel instead of discovering the option in week three. If independence is scored at the match level, this doesn't apply, and the family is exactly as calendar-capped as it looks.
- ATP is the most likely family to actually clear OOS/FDR in this window. Make sure cost/capacity/correlation/decay get genuinely exercised on it the moment it clears, not waved through — see 5.

**3. Next 3–6 months — build vs. avoid**

Build:
- A prior-only donor layer for cold-starting future thin-data families (a new league, a rare event, a new category). Restricted to informing p̂ pre-falsification; it must never write to the label ledger and must never be able to satisfy an independent-label count on its own. Fully consistent with your existing guardrail against promoting donor probabilities directly to tradable ones.
- A calendar/event-velocity forecast per family — known remaining MLB games, known remaining WC matches, known ATP schedule, projected against each family's threshold — so "blocked, insufficient labels" becomes "blocked, ETA N days."
- Full nine-gate treatment for informed flow and passive liquidity once each has a validated candidate. Same rigor as directional sports, not a lighter side path.

Avoid:
- New market families beyond the current seven. More surface area doesn't fix the bottleneck, which is labels and hypothesis generation on what's already running.
- Further live-execution hardening beyond the existing guarded subsystem. Zero live eligible means nothing to execute yet.
- Weather. Correctly deprioritized; the post-hardening block is a data-integrity feature working as intended, not a fire.

**4. Where effort goes first**

In order: near-resolution informed flow, then passive liquidity, then directional-sports monitoring and diagnostics (not active engineering), then nothing on new non-sports families, then nothing on live-execution hardening. The ranking follows directly from what each bottleneck actually is — compute-bound beats calendar-bound beats not-yet-relevant.

**5. Most dangerous traps right now**

- Loosening the independent-label definition under pressure from a stuck deficit. The guardrail exists precisely for the moment a family has been stuck for weeks and someone wants to see the number move.
- Expanding World Cup labels to the outcome level without correspondingly telling the correlation-cluster gate that those signals share risk with match-winner on the same match. Fixing independence for hypothesis-testing without fixing correlation for portfolio construction reopens exactly the correlated-exposure risk axioms 2 and 3 exist to prevent.
- A rushed informed-flow candidate. 104 settled contracts and 48 forward-quote labels is a small base. If hypothesis generation produces many candidate variants against it, the FDR correction has to be severe — small N, many hypotheses is the classic false-discovery setup, and it's the single most likely place right now for something to look significant and not be.
- Treating cost/capacity/correlation/decay as a formality once something finally clears OOS/FDR. After a long stretch at zero live-eligible, there's real pressure to wave the next four gates through. Each has independently killed real edges before — real-but-uneconomic-after-fees, real-but-uncapturable-given-actual-depth are both still correct rejections.

**6. Fastest path to small, safe, autonomous profitability without violating no-discretion or falsification**

Zero live-eligible after this much infrastructure is the system working correctly, not a warning sign. The fastest legitimate path doesn't touch that fact — it runs through the two fronts that respond to effort in the next two to four weeks (informed flow, passive liquidity) plus the one directional family genuinely close on the calendar (ATP), while everything else keeps running in the background at its own pace. There isn't a faster path that doesn't also require relaxing a gate — and relaxing a gate isn't a faster path to profitability. It's a faster path to a false positive that gets discovered later, expensively.