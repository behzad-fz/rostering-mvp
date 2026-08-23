# Disruption Recovery Engine (Crew) — Technical Architecture & MVP Roadmap
## The wedge product for a modern airline crew rostering platform

> Companion to `airline-rostering-research.md`. Scope: the crew **irregular-operations (IROPS) recovery** problem — the highest-pain, fastest-ROI wedge recommended in the research report. Written from domain expertise; the regulatory basis (EASA FTL / FAR 117 limits) was subsequently **verified against primary sources** — see the companion report §5.1 for the **[verified]** numbers. All figures here are directional estimates to be validated against your target carrier(s).

---

## 1. Product Thesis (one paragraph)

During irregular operations, crew legality is the most time-critical resource in the airline. Legacy systems re-plan overnight; schedulers fight fires with spreadsheets. The **Disruption Recovery Engine** ingests the airline's schedule/pairing/roster state in real time, detects disruptions that threaten crew legality or coverage, generates **ranked, legally-valid re-rostering proposals in minutes**, lets a scheduler approve one, and writes the outcome back — all as an add-on decision-support layer that never asks the airline to replace its core planning system.

**Design principles:**
- **Decision support, not autopilot** — every change requires a human approval (lowers certification/liability burden, earns union and safety-department trust).
- **Incremental delta optimization** — never re-plan the world; repair only what the disruption touches.
- **Legality before optimality** — the rule engine is the contract; the optimizer plays inside it.
- **Explainable outputs** — every proposal carries cost, legality-margin, fatigue, and knock-on rationale.
- **Read-only first** — Phase 0 publishes legality-risk visibility; only later phases write back.

---

## 2. System Context

```
                          ┌─────────────────────────────────────────────┐
   Incumbent systems      │           Recovery Engine (ours)            │
 ┌──────────────────────┐ │ ┌─────────┐  ┌──────────┐  ┌─────────────┐  │
 │ Pairing/Roster (SABRE│ │ │ Ingestion & World   │  │ Detection &  │  │
 │ Jeppesen/AD OPT/...) │◄┼►│ Model   │  │ Impact    │  │              │
 │ OCC / Flight Ops     │ │ └─────────┘  └──────────┘  └─────────────┘  │
 │ Crew tracking/sign-in│ │ ┌─────────┐  ┌──────────┐  ┌─────────────┐  │
 │ Aircraft recovery    │ │ │ Rule &  │  │ Recourse │  │ What-if /   │  │
 │ (AOC, delays, swaps) │ │ │ Legality │  │ Optimizer│  │ Simulation  │  │
 └──────────────────────┘ │ └─────────┘  └──────────┘  └─────────────┘  │
                          │ ┌─────────┐  ┌──────────┐                    │
   External feeds         │ │ Decision│  │ Approval │  ┌─────────────┐  │
   Weather/ATC/airport    │ │ & Audit │  │ Workflow │  │ Notification│  │
 ───────────────────────► │ └─────────┘  └──────────┘  └─────────────┘  │
   Crew app / mobile      │                                              │
   (read status, swaps)   │◄─────────────────────────────────────────────│
                          └─────────────────────────────────────────────┘
```

**Inputs we need (data contract with the carrier):**
1. **Static/master:** fleet, bases, crew groups (pilot/FA), qualifications, aircraft-type entitlements, current CBA rule pack, fatigue-model parameters.
2. **Planned state:** flight legs (numbers, times, aircraft, stations), pairings, current rosters, reserve list, open time.
3. **Operational state (real-time streams):** actual/estimated times, cancellations, aircraft swaps, delay causes, crew check-in/sick/position status, legality state (accumulators per crew: duty/flight-time windows).
4. **External:** weather, ATC, airport ops events (for forward-looking severity).

**Egress:**
- Scheduler workbench (web UI) with ranked proposals, filters, what-if.
- REST API + event bus to existing OCC workbenches and crew apps.
- Audit/export feeds for compliance (fatigue reports, unions).

---

## 3. Core Concepts

### 3.1 The crew recovery subproblem
Given a disruption (delay, cancellation, aircraft swap, crew legality break), find the least-cost, fully-legal set of changes — crew swaps, duty extensions (where allowed), reserve callouts, deadheads, re-pairing of open segments, re-timing — that restores coverage. Formally an **assignment/rescheduling problem under legality constraints**, usually decomposed: *which flights lost crew coverage* → *which pairings are at risk* → *candidate recourse actions per crew* → *optimal selection*.

### 3.2 Delta vs. global re-optimization
- **Delta layer (always on):** repair only the disrupted neighborhood; keeps changes minimal (fewer knock-ons, cheaper, more acceptable to crews).
- **Escalation:** if delta repair fails (e.g., a network-wide weather event), escalate to a wider corridor re-optimization over a defined horizon (× hours) rather than the full month.

### 3.3 Legality as a stateful service
Crew legality is *cumulative and clock-based*: duty-period limits, rest windows (with reduction rules), 7/28/365-day accumulators, night-duty, timezone rules, augmentation eligibility, and CBA clauses (reserve callouts, min days off, credit caps). The engine maintains a **per-crew legality state** updated on every event and validates any candidate change against it *before* proposing.

### 3.4 Severity and propagation
Delay in one flight propagates: crew legality expiring mid-duty, connection breaks, subsequent pairings at risk. The detection layer scores each event by projected impact (crew legality bust, uncovered flights, cascade tomorrow) so schedulers see **"what will break next"**, not just what already broke.

---

## 4. Architecture (Cloud-Native)

| Layer | Component | Notes |
|---|---|---|
| **Ingestion** | Feed adapters (SFTP/file poll, REST, message queue, CDC on legacy DB if allowed; screen-scraping last resort) | Normalize all feeds into one schema; flag staleness per feed |
| **Streaming core** | Event bus (e.g., Kafka-compatible) + time-series store | Ops events ordered by timestamp; replay for what-if |
| **State** | Postgres (SQL) for flight/pairing/roster state + per-crew legality accumulators; read models for UI | All state versioned (event-sourcing-lite) so what-if forks a version |
| **Detection** | Disruption detector + impact propagator + severity scorer | Rules + light ML on delay forecasts; emits "risk events" |
| **Rule & legality** | Declarative rule engine (see §5) exposed as validation microservice | Single source of truth; unit- and regression-tested |
| **Recourse generation** | Candidate-action generator per affected flight/crew | Uses domain heuristics: legal swaps, reserves, deadheads, extensions |
| **Optimizer** | MIP/CP picker over candidate actions; LNS for larger cases | Bounded runtimes (targets in §7); deterministic seeds |
| **What-if / simulation** | Fork current world model → apply candidate plans → roll forward over lookahead window | Answers "what happens if we do X by 22:00?" |
| **Fatigue scorer** | Bio-mathematical model adapter (vendor: SAFTE/FAID-lineage, FAST, or partner) | Output as margin/alert, feeding constraint softening |
| **Decision layer** | Scheduler workbench UI, ranked proposals, approval workflow, audit log (immutable) | Human approves → engine writes back via egress |
| **Egress** | API + event bus notifications; exports for fatigue/HR/unions | Write-back only with carrier's integration endpoint |

**Cross-cutting:** authN/Z (SSO/SAML, role-based: scheduler, supervisor, safety, union-read), observability (metrics: proposal latency, legality breaches, adoption), tenant model ready from day one (multi-airline), and a **sandbox environment** that runs the full stack on simulated data.

---

## 5. Rule & Constraint Engine (the moat)

- **Declarative rules** compiled to a validation service: EASA FTL (EU 83/2014) limits, FAR 117 regimes, per-contract CBA clauses (seniority, CBCs, reserve rules, days-off guarantees, credit caps), company SOPs.
- **Rule structure:** (condition × obligation, plus exception/carryover logic) — e.g., "FDP from 06:00 start, 2 sectors ≤ 13h; extension +1h allowed with in-flight rest ≥ 90 min and augmented crew" — encoded once, validated everywhere.
- **Versioning:** rule packs versioned per jurisdiction/contract; every proposal records which rule version was used.
- **Regression suite:** a corpus of known-good / known-bad scenarios per rule run in CI on every change — this corpus is itself a moat asset.
- **Rule audit API:** "why is this legal/illegal?" returns the exact violated or satisfied clauses — the explainability backbone.
- Scope discipline: MVP encodes **EASA scheme + one reference CBA** fully; other regimes are pluggable rule packs.

---

## 6. Optimizer Design (pragmatic, not academic overkill)

- **Stage 1 — legality filter:** rule engine prunes invalid actions in microseconds per candidate (batch).
- **Stage 2 — cost scoring:** per action compute crew cost delta (block+duty+per-diem), deadhead cost, delay cost avoided, fairness shift (who gets called/how uneven), fatigue margin delta.
- **Stage 3 — selection:** small neighborhoods → exact MIP/CP; larger → large neighbourhood search with deterministic seeds; targets under §7.
- **Stage 4 — ranking:** proposals ranked by total cost with explicit trade-off tags (“cheapest”, “fewest crews touched”, “best fatigue margin”, “most seniority-fair”).
- **Determinism:** same inputs → same outputs (configurable randomness off by default) — non-negotiable for trust and audit.
- Optimizer state kept small via *bounding*: only crews and flights within reach of the disruption (bases, aircraft near, legality windows) enter the model.

---

## 7. Performance Targets (directional)

| Capability | Target |
|---|---|
| Legality validation per candidate action | < 50 ms |
| Proposal generation for a single-aircraft/crew disruption | < 2 min from event |
| Hub-wide (multi-aircraft, e.g., 30+ disrupted flights) proposal set | < 10 min |
| What-if scenario (fork + roll forward 24 h) | < 1 min per scenario |
| Detection-to-alert latency (risk events) | < 1 min |
| System availability | 99.9% during ops window, with graceful degradation to read-only |

---

## 8. MVP Roadmap

### Phase 0 — Foundations & Legality Visibility *(weeks 1–4)*
- Data ingestion adapters for target carrier (planned + ops feeds); world model for a chosen base/date range.
- Rule engine v1: EASA FTL host of limits + one CBA rule pack; legality state per crew.
- **Read-only dashboard:** "legality risk radar" — crews at risk of busting limits today, flights with uncovered/at-risk coverage, reserve availability.
- Exit criteria: scheduler team agrees the risk radar is accurate against their own manual checks (2-week shadow run, no decisions made on our output).

### Phase 1 — Proposal Engine (MVP) *(weeks 5–14)*
- Recourse generation (swaps, reserves, deadheads, extensions) + cost/fatigue/fairness scoring + MIP/CP picker.
- Scheduler workbench: ranked proposals, filters, approve/reject, notes; immutable audit log.
- Write-back API for the carrier's OCC integration (reserve callout, roster update).
- **No mobile yet; no what-if yet.**
- Exit criteria: ≥ 80% of covered disruption types get a proposal the scheduler accepts within 2 min; measured acceptance rate ≥ 50% in the first month; zero illegality from our proposals (regression-tested).

### Phase 2 — What-if & Fatigue *(weeks 15–20)*
- World-model fork + roll forward (digital-twin of the operation); "what if we divert / swap / wait?" scenarios.
- Fatigue-model integration (partner vendor) surfaced as margins and as soft constraints in scoring.
- Multi-user concurrent sessions, approval hierarchy, SSO.
- Exit criteria: schedulers use what-if in ≥ 1 real decision per week; fatigue margins attached to ≥ 95% of proposals.

### Phase 3 — Scale & Platform Traction *(weeks 21+)*
- Second jurisdiction/second carrier pilot (validates multi-tenant + rule-pack pluggability).
- Broader disruption types (weather mass events → corridor re-optimization), crew mobile view (read-only status, later lightweight trading), analytics (fairness & cost reports).
- Feed the roadmap to the full rostering platform (native pairing/rostering construction behind the same rule/optimizer stack).

**Sequencing rationale:** Phase 0 de-risks data access and trust before we ever propose an action; Phase 1 proves ROI on measurable disruption savings; Phases 2–3 compound the moat (fatigue, rule packs, fairness analytics).

---

## 9. Success Metrics (KPIs to put in the commercial contract)

- Δ **crew-attributable delay/cancellation minutes** vs. baseline (adjudicated per event).
- **Time-to-proposal** and **proposal acceptance rate**.
- **Legality-breach events avoided** (near-miss detection count).
- **Scheduler adoption**: % of IROPS crew decisions made in the workbench after 3 months.
- **Knock-on reduction**: fewer next-day uncovered flights.
- **Fairness index** improvement (distribution of callouts across a crew group).

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Feed data quality/staleness from legacy systems | Per-feed staleness telemetry; graceful degradation; normalize & flag; shadow-run validation in Phase 0 |
| Rule coverage gaps (new CBA clause) → proposal rejected or illegal | Rule packs versioned + regression corpus; human approval gate; "not covered" is an explicit proposal state, never a silent assumption |
| Trust deficit (schedulers/unions) | Start read-only; explainable rationale strings on every row; audit log; joint governance with union observer |
| Latency expectations vs. optimizer scale | Bounded neighborhoods, escalation corridor only, deterministic runtimes with hard caps |
| Single-carrier dependency | Multi-tenant day one; second pilot in Phase 3; simulator harness for demo/R&D independent of any carrier |
| Fatigue-model vendor dependency | Adapter interface; at least two candidate vendors; internal fallback model option |
| Wrong write-back causes roster chaos | Two-phase write-back (staging → approve), checksums, rollback journal, readonly mode switch |

---

## 11. Team & Rough Costing (directional)

- **Core team (Phase 0–1):** 1 OR/optimization engineer (the scarcest hire), 1 senior backend/data engineer, 1 frontend engineer, 1 domain SME (ex-airline crew scheduler — non-negotiable), 0.5 product/PM. ≈ 4.5 FTE.
- **Phase 2 adds:** 1 simulation engineer, 0.5 data scientist, fatigue-model licensing budget.
- **Capex:** standard cloud (managed K8s, PG, event bus) — modest; the cost is *domain build*, not compute.
- **Note:** start sales/partner conversations in parallel with Phase 0 engineering — the pilot carrier's data access and OCC access are on the critical path far more than code is.

---

## 12. Open Questions That Need a Carrier

1. Which feed formats can the pilot carrier actually expose (files/API/queue)? What is the latency schema of "planned vs. actual"?
2. Who approves crew changes in the OCC workflow today — where does our decision layer slot in without breaking authority?
3. Which rule regime + one CBA do we encode first for them (EASA vs. FAR 117)?
4. Which fatigue model does their FRMS/medical department already trust?
5. What is the carrier's measured baseline for crew-attributable delay/cancellation cost today (needed to contract on KPIs)?

---

## 13. One-Page Summary

- **What:** real-time crew IROPS recovery decision support; legality-first, human-approved, explainable.
- **Why now:** legacy batch systems + manual firefighting cost millions per year in avoidable crew delay/cancellation; modern streaming/cloud + OR tools make minute-scale recovery feasible for the first time.
- **Wedge:** add-on, no core replacement ask; Phase 0 is read-only legality visibility (trust first).
- **Moat:** versioned rule packs + regression corpus, fatigue integration, fairness analytics, audit trails.
- **Sequence:** visibility (4 wk) → proposals (10 wk) → what-if + fatigue (6 wk) → multi-carrier scale.
- **First hire:** the OR engineer. **First partnership:** the pilot carrier. **First contract KPI:** crew-attributable delay minutes avoided.