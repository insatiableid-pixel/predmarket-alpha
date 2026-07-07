I cloned the repo and audited bd56a254 (PR #21 head) directly, including the full diff vs main, the falsification/gate code, collectors, and docs/codex/current-state.md (which matches your supplied numbers). Everything below is grounded in repo evidence unless marked [inference]. One line of framing: this is engineering and research-process advice, not investment advice -- I'm not a licensed advisor, and nothing here is a recommendation to deploy capital.

Verdict
The statistics are fine. The data supply chain is starving them. You have 30 pre-registered hypotheses (3 divergence rules x 8 thresholds + 6 price buckets, each requiring 30 independent / 10 OOS labels -- sports_consensus_falsification.py) fed exclusively by a forward-clock labeler that only labels contracts it happened to observe live. At ~20-30 labels/day spread across cells, the grid stays at "0 testable" for months. Meanwhile the single highest-leverage asset -- Kalshi's own resolved-market archive (settled markets + candlestick/trade history) -- is touched nowhere in the codebase (no candlestick/history fetch exists anywhere). And your #2 declared edge family, stale quotes, has zero instrumentation: kalshi_websocket.py exists, subscribes to the ticker channel only, and is imported by nothing outside its own tests. It is dead code while unrecoverable tick history evaporates daily.

The repo is overbuilt in control-plane meta-reporting (advice audits, blocker-clearance cycles, sequencing reports, ETA reports -- reports about reports) and underbuilt in raw data acquisition (one consensus provider, ~4 sports, no tick capture, no backfill). The next move is more label collection -- and critically, historical labels, not just waiting on the forward clock.

Also, PR #21 should merge: it's green, and the head commit (bounded 429 retry with Retry-After cap + regression test) is a genuine, well-tested fix. But a 350-file / +94k-line branch labeled "chore: repo hygiene" is a process smell -- stop shipping omnibus branches.

1. Short-horizon plan
Next 6 hours

Merge PR #21. Acceptance: main green, tagged. Then adopt a rule: no PR >~2k lines.
Start recording ticks immediately -- before any analysis exists. Wire KalshiWebSocketClient into an append-only JSONL recorder for all observed sports tickers (ticker channel now; add orderbook_delta next). Files: new scripts/kalshi_tick_recorder.py + systemd/tmux under the always-on collector. Acceptance: replayable JSONL with monotonic timestamps, sha256 in a safety artifact, survives reconnects. Every hour not recording is permanently lost stale-quote evidence.
Backfill feasibility spike (read-only): confirm Kalshi public endpoints for settled-market pagination and per-ticker candlesticks/trades; confirm The Odds API historical snapshot granularity and credit cost for MLB h2h. Acceptance: one settled MLB ticker fully reconstructed offline (price series + Kalshi settlement label).
Run the due 22:00Z consensus probe and keep the ATP 2026-07-07T06:00Z clock. No new code needed.
Next 24 hours

Resolved-archive backfill collector v1 (Kalshi-only). Iterate settled markets for covered series -> entry-price-at-horizon x settlement -> feed the resolved_archive_price_bucket_bias family (explicitly allowed by your doctrine, and it needs no consensus join). Target: >=1,000 independent labels, >=10 OOS per bucket via the existing chronological split. Acceptance: consensus/bucket falsification reports >0 tested hypotheses -- an honest test at real power, survivor or not.
Fix the informed-flow null. kalshi_near_resolution_informed_flow_evidence_gate.py line ~399 tests OOS accuracy against binomial_survival(wins, n, 0.5). Near resolution, 0.5 is the wrong null -- a coin that always picks the side priced >0.5 beats it. Replace with a price-implied null (predicted side's timestamp-matched Kalshi price, cost-adjusted). This raises rigor, so it's allowed under your constraints. If the family no longer survives, demote its paper rows mechanically. This matters because informed flow is currently your only family in paper.
Historical-consensus skew check: if Odds API historical snapshots are 5-minute, nearest-match worst-case skew is 150s <= your 180s gate -- compliant without loosening anything. If 10-minute, the divergence backfill is out; bucket-bias backfill still stands.
Next 72 hours

Backfill at full scale (all covered sports, back to Kalshi's sports launch); freeze as hashed, replayable artifacts.
If skew-compliant, run the historical consensus-divergence join and re-run the full 30-cell grid with real power.
Breadth: enumerate in-season Kalshi sports series vs Odds API sharp coverage; onboard the top two by events/day (likely additional MLB markets and club soccer). Time-critical [calendar inference]: the World Cup ends ~July 19 -- capture every remaining match now; MLB's All-Star break (~mid-July) pauses your biggest daily label engine for several days.
Stale-quote feature packet v0 spec (pre-registered rules only; no fitting yet).
2. Long-horizon plan
7 days: Backfill complete and frozen; first fully powered falsification pass on divergence + bucket grids; survivors (if any) routed through the existing cost/capacity/correlation/decay chain into paper. Tick recorder hardened (reconnect gaps accounted, rotation). Ops cleanup: the hardcoded /home/mrwatson/... paths in kalshi_always_on_collector.py, passive-fill loop, and labeled-observation builder move to config -- they're a portability and disaster-recovery liability.

30 days: Second consensus source (Betfair exchange API and/or a Pinnacle-lineage feed where legally available) for redundancy and better timestamps; provider-disagreement metrics. First stale-quote falsification on 3-4 weeks of proprietary ticks + line-move log, pre-registered via your existing hypothesis registry. Unify per-family ledgers into one cross-family correlation-controlled portfolio ledger. NFL onboarding prep (August preseason).

90 days: NFL/CFB season readiness on day one -- that's Kalshi's deepest sports volume and your capacity-through-breadth axiom depends on it. By then you hold ~90 days of tick + line-move history nobody can retroactively buy: that's the moat. Live pilot only if a family clears FDR + cost + capacity + correlation + decay and >=30 days of paper P&L consistent with replay -- your existing preflight/arming gates already encode this order correctly; don't touch them.

3. Highest-leverage bottleneck
Label velocity into pre-registered cells, and specifically the missing resolved-archive backfill. Blunt version: you built a courtroom with no witnesses. The grid needs ~30 independent/10 OOS per cell; nearest cell is 5/10 OOS; forward clock delivers tens of labels per day across all cells. The archive of already-settled Kalshi sports contracts can deliver thousands in one tranche without lowering a single threshold or inferring a single label. Second bottleneck: stale-quote capture not running. More modeling is worth approximately nothing right now.

4. Architecture audit
Over-focusing on consensus divergence? Directionally right, operationally yes: it got 8,700 lines of adapters/policy/falsification while its evidence pipe stayed a trickle. Also note sub-1c divergence thresholds live inside spread/fee noise; your cost-replay gate must remain the filter there (it exists -- keep it mandatory).
Under-instrumenting stale lines? Yes, severely. Declared family, zero capture, dead websocket client, no line-move history anywhere.
Falsification too slow/conservative/strict? The design (per-cell floors, chronological OOS, BH-FDR at alpha=0.10, no post-hoc rules) is correctly strict -- do not loosen. What's slow is evidence supply. The one genuine miscalibration runs the other way: the informed-flow 0.5 null is too weak (see above).
Paper/live gate order? Correct. Verified chain: EV ledger -> paper decisions (fee-aware, covariance-normalized, cluster caps) -> settlement reconcile -> decay/retirement -> live preflight -> deliberate arming gates (execution_enabled, env arm, balance). Live is blocked for the right reasons. Don't harden live further while 0-eligible.
Near-resolution flow treated correctly? Mostly -- independence clustering, official terms capture, fee-aware EV, and real orderbook snapshots at preflight are all right. Two flaws: the 0.5 null, and [inference] taker fills against near-resolution asks are adverse-selection-prone; keep the paper burn-in long before trusting replay fills.
Passive liquidity? Not now. Labels are literally proxy_only_no_real_fill_label ("would_touch_within_ttl" != filled: queue position and adverse selection are unmodeled), and the machine already reports 0 FDR survivors with negative best net EV. Keep collecting the proxy data passively (marginal cost ~0 since it rides microstructure snapshots), spend zero dev effort, revisit only after real maker fills exist post-live.
5. Next 3 implementation tranches
T1 -- Resolved-archive backfill + bucket-bias falsification at power. Purpose: convert the label bottleneck from months to days. Scope: settled-market paginator, per-ticker candlestick/trade fetch, entry-price-at-horizon builder, join to Kalshi settlements, feed existing falsification; hashed replayable raw snapshots. Non-goals: no consensus join, no new hypotheses, no threshold edits, no EV/paper changes. Acceptance: >=1,000 independent labels; every bucket cell >=30/10; falsification emits tested hypotheses with q-values; artifacts latest-kalshi-resolved-archive-backfill.{json,csv}. Failure modes: API pagination/throttle (reuse PR #21's 429 backoff), survivorship (must enumerate all settled markets in a series, not just observed ones), duplicate labels with forward archive (dedupe on ticker). North star: this is exactly "many weak edges across many markets" -- measured from resolved contracts, as the doctrine specifies.

T2 -- Stale-quote instrumentation (tick recorder + line-move log). Purpose: begin the unrecoverable data clock for edge family #2. Scope: wire KalshiWebSocketClient (add orderbook_delta/trade channels) into an append-only recorder; a 60s Odds API poller that records only deltas (line moves with timestamps) to conserve credits; gap/reconnect accounting. Non-goals: no signal logic, no features, no hypotheses yet -- capture only. Acceptance: 72h continuous capture, <1% gap time, replayable, safety-flagged artifacts. Failure modes: silent disconnects (heartbeat + gap ledger), disk growth (rotation), credit burn (delta-only writes). North star: enables stale_quote_slow_update_after_consensus_move, already on your allowed-families list, currently unfundable for lack of data.

T3 -- Null hardening + paper re-qualification. Purpose: make the one live-ish family's statistics as strict as the rest of the machine. Scope: price-implied null in the informed-flow gate (and audit binomial_survival(..., 0.5) usage across all family gates); mechanical demotion path if the family fails the stronger test. Non-goals: no new features, no threshold lowering (this raises them). Acceptance: gate re-runs on existing labels; artifact records old-null vs new-null q-values; paper ledger reflects outcome automatically. Failure modes: paired-test miscalibration (use per-row price as Bernoulli null, aggregate via exact or simulation), accidental retro-fitting (pre-register the null change before running). North star: prevents a false-confidence family from becoming your first live candidate.

6. Do-not-build list
Elo/projections/simulations as probability sources (doctrine already bans; keep it banned).
Any new control-plane meta layer: more advice audits, blocker-clearance variants, sequencing/ETA elaborations. Freeze this layer -- it's the most overbuilt part of the repo.
Per-domain copy-paste falsification stacks (the weather/crypto/world-cup *_proxy_feature_model_falsification scripts are near-duplicates); consolidate later, do not extend now -- and don't dilute into weather/crypto while the sports mission is label-starved.
Passive-liquidity queue simulators or fill models without real fills.
Live-execution hardening beyond current preflight while 0-eligible.
Kelly/sizing sophistication before any admitted signal exists.
Dashboards/UI.
Exotic Kalshi props with no sharp coverage (unfalsifiable against consensus).
More root-level audit markdowns (move the nine existing ones into docs/audits/).
7. Missing data/sources, ranked by edge leverage
Kalshi resolved-market archive (settled markets + candlesticks/trades) -- free, public, feeds bucket-bias at scale and boosts independent counts everywhere. Build first.
Kalshi live tick + orderbook stream, persisted -- free, unrecoverable, prerequisite for stale-quote and better flow/capacity/fill evidence.
Historical no-vig consensus snapshots (Odds API historical) -- paid; unlocks divergence backfill iff snapshot cadence keeps skew <=180s. Verify granularity and terms/cost before committing.
Sharp line-move event log (60s current-odds delta polling) -- cheap, feeds stale-quote forward labels.
Second sharp/exchange source (Betfair API; Pinnacle-lineage where legal) -- timestamp quality + redundancy; your provider policy already models these.
Higher-cadence Kalshi orderbook snapshots for capacity/adverse-selection work.
Settlement labels -- already correctly solved (public Kalshi only); just scale breadth.
Injury/lineup news timestamps -- later, and only as stale-quote trigger annotations, never as model inputs.
8. Final checklist (hand to Codex/Droid, in order)
Merge PR #21; adopt a <=2k-line PR cap going forward.
Ship kalshi_tick_recorder.py and start it today (ticker + orderbook_delta, append-only, gap ledger).
Spike: reconstruct one settled MLB ticker offline from Kalshi public history; confirm Odds API historical granularity/cost.
Build T1 resolved-archive backfill; run bucket-bias falsification at >=1,000 independent labels.
If 5-min historical snapshots confirmed: historical consensus join; re-run the 30-cell divergence grid.
Build T3 null hardening; re-gate informed flow; let paper demote mechanically if it fails.
Ship the 60s line-move delta logger (T2 completion).
Breadth: onboard the next two in-season Kalshi sports surfaces with sharp coverage; max World Cup capture before ~July 19; plan around the MLB All-Star gap.
Move /home/mrwatson paths to config; relocate root audit markdowns; freeze the meta-report layer.
Keep all existing clocks (22:00Z consensus probe, ATP 07-07T06:00Z), all thresholds, and the paper->live gate order exactly as they are.
Nothing above lowers a threshold, infers a label from a sportsbook, promotes a probability past your gates, or recommends live execution -- it redirects effort from meta-instrumentation to evidence acquisition, which is where the machine is actually starving.
