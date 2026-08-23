# Building a Modern Airline Crew Rostering System
## Research Report — Can a New Platform Beat the Legacy Incumbents?

> **Methodology note:** This report began as a synthesis from expert domain knowledge (background research sub-agents were unavailable and the in-GUI web_search provider lacked credentials). A subsequent **live verification pass** fetched and checked primary sources directly: the EASA FTL regulation from **EUR-Lex** (CELEX 32014R0083), **14 CFR Part 117** from the **eCFR XML API**, plus vendor and reference pages (Jeppesen product site, Wikipedia vendor pages, an industry software roundup). Regulatory numbers verified that way are marked **[verified]**; unverified figures (crew-cost shares, delay costs, savings rates) remain directional and are flagged for validation in §11. One notable correction from the pass: **FAR 117 caps flight time at 1,000 h/year, not 900 h (the 900 h figure is EASA's)** — see §5.1.

---

## 1. Executive Summary

Airline crew rostering — deciding which pilot or flight attendant flies which trips, in which order, on which days — is one of the most constrained and most consequential scheduling problems in the world. Crew costs are typically an airline's **second-largest expense after fuel**, and a roster sits at the intersection of:

- **Safety regulation** (flight-time limits, minimum rest, fatigue science),
- **Labor law and collective bargaining** (seniority, bidding, custom bidding credits, reserves),
- **Operational efficiency** (crew utilization, training pipelines, base coverage),
- **Human preference** (pilots and cabin crew bid for what they want to fly), and
- **Chaos** (disruptions — weather, ATC, aircraft issues — that invalidate plans in minutes).

Most airlines run this problem on **systems designed 20–40 years ago**: mainframe-era or client-server architectures, nightly batch optimization, rigid data models, opaque interfaces, and little to no real-time recovery capability.

**Thesis:** There is a genuine, defensible opportunity to build a modern rostering platform that is decisively superior to the legacy incumbents — not by marginally improving the same batch optimization, but by re-founding the product on:

1. **Real-time, event-driven recovery** (re-rostering in minutes, not overnight),
2. **Modern optimization** (column generation / branch-and-price, constraint programming, metaheuristics — dramatically more tractable on today's hardware),
3. **Fatigue science and Fatigue Risk Management Systems (FRMS) built in** (bio-mathematical models, not just prescriptive rule checks),
4. **Crew-first, mobile-grade UX** (bidding, swapping, transparent explanations of "why this roster?"),
5. **Cloud-native, API-first architecture** (event streams, integration with Operations Control Centers, airline data lakes, partner tools), and
6. **Explainable, human-in-the-loop optimization** (outputs schedulers and unions can trust, contest, and audit).

The countervailing forces are real and should shape any go-to-market plan: **regulatory inertia, safety-culture risk aversion, long sales cycles, data-access barriers, and incumbent lock-in**. But the pain is measurable — crew shortage, disruption cost, and crew dissatisfaction are all pressing airline problems — and the gap between what legacy systems deliver and what is now possible is the largest it has ever been.

**Recommendation:** pursue this not as a "me-too full platform" from day one, but as a **wedge** — a disruption-recovery engine or a crew-experience (bidding/trading) layer that plugs into existing systems, proves value in weeks-to-months, and grows into a full platform. Details in §9.

---

## 2. Background: What Airline Crew Scheduling Actually Is

### 2.1 The pipeline

Crew scheduling is classically split into two linked problems:

- **Crew Pairing (pairings / rotations):** Partition the flight schedule into duty sequences ("pairings") a crew can legally and efficiently fly — e.g., LAX–SFO–LAX as one pairing with a layover, or multi-day sequences for long-haul. Pairings must *cover every flight* at minimum cost while respecting flight-time limits, rest, base (domicile), and aircraft-type constraints. Solved monthly at the network level, typically called "pairing generation."
- **Crew Rostering:** Assign individual crew to pairings across a roster period (usually a month), producing each person's **line** — a sequence of pairings, days off, training, vacation, and reserve duties. This must respect *individual* constraints: qualifications, recency, base, vacations, contractual minimums/maximums, and — critically — **seniority and preferences**, usually via preferential bidding.

### 2.2 Bidding regimes

- **Preferential bidding systems (PBS):** crew submit bids for trips, specific days off, patterns, etc. The optimizer constructs lines maximizing preference satisfaction weighted by seniority, subject to all rules. **"Player" bidding** optimizes per-crew; **"line" bidding** constructs generic "bidlines" that crew then rank overall. Regime differs by carrier and union contract.
- **Custom bidding credits (CBCs):** idiosyncratic crew preferences encoded as weighted credits, often heavily negotiated with unions.
- Seniority weighting is legally and culturally sensitive — "fairness" is a first-class requirement, not an afterthought.

### 2.3 Reserves, open time, and trading

- **Reserve (standby) systems** cover uncovered flying; callout rules are regulated and contractual, and reserve staffing is a significant cost (idle crew paid to wait).
- **Open time** (unassigned trips) is published for pick-up, often first-come-first-served.
- **Bid trading / swaps** let crew exchange trips with approval; modern systems increasingly support rule-aware automated matching.

### 2.4 Irregular operations (IROPS)

The plan is a fragile artifact. Disruptions — weather, ATC, aircraft unserviceability, crew legality expiring mid-sequence — cascade through pairing and rostering. Recovery means real-time re-pairing and re-rostering: reassigning crews, extending or curtailing duties, calling reserves, rerouting. **Legacy systems are weakest here**, and disruption cost is where modern systems can show the largest, most immediate dollar impact.

---

## 3. The Legacy Landscape and Its Pain Points

### 3.1 Market map (from domain knowledge)

| Vendor | Products | Characteristics |
|---|---|---|
| **Sabre** | AirCentre Crew suite (Crew Scheduling, Crew Manager, pairings/optimization modules) | Mainframe heritage; huge installed base among network and legacy carriers in the Americas and beyond; AirCentre integrates ops, network, and crew. |
| **Jeppesen (now Thoma Bravo)** | Jeppesen Crew Rostering (the "Merlot" family — also pairings, tracking) | Boeing acquired Jeppesen in 2000, then **divested it to private-equity firm Thoma Bravo (announced late 2024, closed 2025)** — [verified] via Wikipedia; long the crew-solutions specialist for Western network carriers; thick-client legacy with modernization layers. Product page: [ww2.jeppesen.com — Crew Rostering](https://ww2.jeppesen.com/airline-crew-optimization-solutions/crew-rostering/) |
| **Lufthansa Systems** | NetLine/Crew, NetLine/Ops (NetLine/Ops + Crew), crew portal (iPool-crewportal lineage) | Strong in Europe; tightly coupled ops/crew planning; long legacy of batch optimization; has been restructuring its airline-facing portfolio through the 2020s. |
| **AD OPT** | Altitude (pairing + rostering optimization) | Montreal-based OR specialist (roots in McGill research); long considered best-in-class on optimizer quality; the kind of pure-OR shop a challenger would love to hire from. |
| **IBS Software** | iCrew family | Trivandrum/Kochi-based airline IT vendor (PE-backed — acquired by Blackstone, 2019); cloud-forward positioning, big base in Asia/Middle East and among growth carriers. |
| **Navitaire / Accelya** | Crew modules within LCC reservations suites | Navitaire (ex-Accenture, then Travelport, then absorbed into Accelya, 2021) is primarily reservations/ancillaries for LCCs; crew depth is thinner than specialists. |
| **AIMS** | Ops/crew management systems | UK-based; popular among European regional/charter/specialist carriers; wide but older codebase. |
| **Hexaware** | AIRCREW | Indian IT-services product; used at a range of carriers; ODC-style delivery. |
| **Hitit** | Crew in the Crane suite | Turkish airline-IT vendor; mostly MENA/EMEA carriers. |
| **InteliSys** | Operational suite incl. crew scheduling | Canadian; serves regional/charter/air-cargo operators on web-based systems. |
| Plus: in-house builds | Many large airlines ran homegrown crew systems (and some still do) | Custom-built at a time when nothing off-the-shelf fit; costly to maintain; the origin of much legacy debt. |

*Confidence: vendor names and product names above are well established in the industry; the one-line characterizations are my domain-knowledge synthesis, and specifics (e.g., exact installed-base counts) should be verified.*

### 3.2 System-level weaknesses (the pain that motivates a challenger)

1. **Batch-oriented.** Optimization runs nightly; the plan is stale within hours. A disruption at 08:00 is often not reflected in any automated plan until the next run — or is handled manually.
2. **Rigid data models and rule engines.** Adding a rule (a new fatigue provision, a union concession, a new base) is a multi-month consulting project, not a configuration change. Rules are buried in code and proprietary rule syntax.
3. **Siloed.** Crew systems are weakly integrated with aircraft recovery, OCC tools, revenue management, and crew-facing mobile apps. Disruption recovery across aircraft + crew + passengers remains fragmented.
4. **Poor UX.** 1990s thick-client interfaces for schedulers; little self-service for crew; opaque "why did I get this roster" answers; no mobile.
5. **Lock-in.** Decades of customization make switching costly and behaviorally sticky; maintenance fees are high; data migration is painful.
6. **Weak FRMS support.** Prescriptive limit checks, yes; bio-mathematical fatigue prediction, rarely. Fatigue management is bolted on, not built in.
7. **Human firefighting.** Industry lore (and scheduling-department experience) says a large share of IROPS crew recovery decisions are still made by humans with spreadsheets and phone calls — precisely when speed and legality checks matter most.

---

## 4. The Science: What a Superior Optimizer Needs

### 4.1 Pairing construction

- Modeled as a **set partitioning/covering problem on flights**. Because enumerating legal pairings explodes combinatorially, the standard approach is **column generation**: generate promising pairings lazily via a pricing subproblem (typically a resource-constrained shortest-path with flight-time/window constraints) and solve the master LP/MIP over the current column pool, iterating until convergence. The academic state of the art is **branch-and-price** (Barnhart et al. on flight crew scheduling is the canonical reference; large-scale applications across major carriers exist).
- Objectives: minimize crew cost (block + duty + per-diem + deadhead + layover hotels), while producing *robust* pairings (buffer time, connection slack) to absorb delays.
- Side constraints: base coverage, maintenance-eligibility windows, training flows, contractual maxima per base, "stability" toward crew desirability.

### 4.2 Rostering construction

- Assign pairings to individuals: a **huge assignment/MIP** with individual legality and preference dimensions. Solved by column generation over candidate lines, by **constraint programming** (CP does well at the nasty feasibility side: rest, cumulatives, vacation), by **large neighbourhood search / metaheuristics** (simulated annealing, genetic algorithms, tabu search) for scale and robustness, and by decomposition into bidding and allocation steps.
- **Preferential bidding optimization:** score candidate assignments by seniority-weighted preference achievement; the optimizer maximizes the lexicographic/weighted satisfaction. Practical PBS systems trade off exactness vs. run time; modern hardware and better formulations let challengers push solution quality far beyond 20-year-old heuristics.
- **Fairness** as quantified metric (e.g., distribution of arduous duties, credit-hour equity across a crew group) is increasingly expected — a differentiator, since legacy systems rarely expose it.

### 4.3 Reserve and robustness

- Reserve optimization: set staffing levels per base/day to meet stochastic demand with coverage probabilities; minimize idle reserve cost; fair reserve distribution. Stochastic optimization and simulation are natural tools.
- Robustness: build slack (pairing buffer, "recovery windows") deliberately rather than only re-optimizing after the fact.

### 4.4 Disruption recovery (IROPS) — the modern frontier

- Literature and practice distinguish **aircraft recovery**, **crew recovery**, and **integrated recovery** (simultaneous aircraft + crew + passenger recovery is a long-standing research theme, e.g., the European airline disruption-management literature, Jesper Hansen/Larsen threads on stochastic recovery; column-generation-based re-optimization in real time).
- The practical gold standard to beat: **rapid re-rostering proposals** — "here are 5 re-rostering options ranked by cost, legality margin, fatigue impact, and crew knock-on effects" — computed in minutes on streaming delay data, with what-if simulation before committing.
- Legacy batch systems cannot do this; point solutions exist but are not integrated with the master plan.

### 4.5 AI/ML's honest role

- **Forecasting**: delay/disturbance prediction, crew no-show/sick rates, seasonal demand — feeding optimization parameters.
- **Preference learning**: implicit signals (swap patterns, past acceptances) to enrich bidding models — careful with union sensitivity.
- **Hybrid OR+ML**: ML to shrink/search the space (warm starts, predicting which pairings survive disruption), OR to guarantee legality and optimality. The optimizer stays the authority; ML enriches inputs and cools outcomes.
- What AI is *not*: a replace-the-optimizer black box that makes safety-critical assignments without reproducibility — airlines and regulators will reject that.

---

## 5. Regulation, Fatigue, and Labor: The Constraint Moat

### 5.1 Flight-time/duty limits (headline numbers — verify against primary text)

- **EU / EASA FTL — Regulation (EU) No 83/2014**, flight-time limits **[verified]** from EUR-Lex: **100 flight hours in any 28 consecutive days; 900 flight hours in any calendar year; 1,000 flight hours in any 12 consecutive calendar months**. Per-duty FDP maxima depend on start time, sectors, night operations, and augmentation (FTL annex); minimum daily rest typically 12 h (10 at base under conditions) with weekly rest ~36 h incl. two local nights, or adapted variants; timezone/circadian rules apply; member-state scheme deviations exist. Source: [EUR-Lex CELEX 32014R0083](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32014R0083)
- **US FAR Part 117** (passenger ops, effective Jan 2014), **[verified]** from eCFR: flight time — **100 hours in any 672 consecutive hours (= 28 days) and 1,000 hours in any 365 consecutive calendar days** (note: annual cap is **1,000 h, not 900 h** — 900 h/year is the EASA figure); duty limits — **60 flight-duty-period hours in any 168 consecutive hours (7 days) and 190 FDP hours in any 672 consecutive hours (28 days)**; per-duty FDP maxima by report time and augmentation live in Tables B/C of the rule (~9–14 h depending on start time/augmentation; flight time per FDP ~8–9 h unaugmented — approximate, per the tables); "physiological night's rest" = **10 h encompassing 0100–0700** at the acclimated location. Source: [eCFR, 14 CFR Part 117](https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-117)
- Universals: cumulative accumulators, minimum rest (reductions only under defined conditions), split/remote duty, augmented-crew rules, and record-keeping/reporting obligations (e.g., FAR 117 requires reporting any exceeded limit to the FAA within 10 days).

### 5.2 Fatigue Risk Management Systems (FRMS)

- **FRMS** lets an operator manage fatigue as a risk rather than pure checklist compliance: ICAO Annex 6 and **ICAO Doc 9966** (Manual for the Oversight of Fatigue Management Approaches), US **AC 120-103**, EU provisions under ORO.FTL. An FRMS can permit flexibility around prescriptive limits **only with a documented safety case**, monitoring, and (in some regimes) bio-mathematical model support.
- **Bio-mathematical fatigue models** used in practice: **SAFTE** (Sleep, Activity, Fatigue, Task Effectiveness), **FAID** (Fatigue Audit InterDyne, Australian lineage), **Boeing FAST** (Fatigue Avoidance Scheduling Tool), and successor/academic variants. They predict alertness/effectiveness from sleep-wake history, circadian phase, time-on-task — inputs a scheduler never had when the legacy systems were built.
- Implication: a modern system can **generate schedule options that are FRMS-aware** (predict fatigue exposure, keep margins, flag violations before publication) and produce regulator-friendly evidence — a genuine differentiator legacy systems lack, and a reason chiefs-of-pilot-training and fatigue offices would champion a new vendor.

### 5.3 Collective bargaining agreements (CBAs) and company rules

- The constraint layer multiplies per carrier: seniority bidding; **custom bidding credits (CBCs)**; reserve caps and callout windows; guaranteed days-off counts; vacation/training accommodations; min/max credit hours; deadhead, per-diem, and premium rules; base/domicile and equipment qualifications; recency (landings in N days); duty-position and rest-facility (e.g., lie-flat) eligibility.
- **Why this is a moat:** full rule coverage for even one airline is a multi-month engineering effort; each airline's contract is bespoke; errors are safety- and labor-grievance-relevant. The competitor who accumulates a **certified rule library** (per jurisdiction, per contract archetype) with regression-tested compliance engines owns the market's most defensible asset — and conversely, this complexity is the single biggest barrier to new entrants.

### 5.4 What this means for software

- Central **rule engine** (declarative constraints + validation) separate from the optimizer; exhaustive compliance audit logs; what-if "is this roster legal under EASA + contract X?" checks in seconds.
- Positioning: sell **decision support**, not a certified safety-critical controller — dramatically lowers the certification/liability hurdle while still transforming outcomes.

---

## 6. Gap Analysis: Where Legacy Systems Fail Modern Expectations

| Dimension | Legacy reality | Modern expectation |
|---|---|---|
| Freshness of plan | Nightly batch; stale within hours | Event-driven; delta re-optimization in real time |
| Disruption response | Manual re-rostering, spreadsheets, hours | Ranked re-rostering proposals in minutes with what-if |
| Crew experience | Call-centers, opaque rosters, no mobile | Mobile-first bidding, trading, transparency |
| Rule flexibility | New rule = multi-month project | Configurable rule engine with regression testing |
| Fatigue | Prescriptive limit checks only | Bio-mathematical model integration, proactive alerts |
| Fairness/explainability | Black-box seniority weighting | Quantified fairness metrics, contestable outputs |
| Integration | Point-to-point, fragile ETL | APIs, event streams, open data contracts |
| Cost | High maintenance fees, lock-in, deadhead/roster gaps | Utilization analytics, integrated pairing+rostering+recovery |
| Self-service | Manual swap/assignment workflows | Rule-aware automated trading/auctions |

---

## 7. Vision for a Modern Platform

### 7.1 Architecture sketch
- **Cloud-native microservices** on managed infrastructure: pairing engine, rostering engine, rule/fatigue services, bidding service, trading service, recovery service, notification bus, audit store.
- **Event-driven core:** flight changes, delay predictions, legality events, weather, ATC, and airport feeds stream in; each event triggers bounded delta re-optimization with configurable horizons (don't re-plan the world for every 5-minute delay — a key engineering discipline).
- **API-first with an OCC integration layer** and open data contracts for the airline's data lake; webhooks/event buses to adjacent systems (aircraft recovery, crew tracking, crew apps).
- **Optimizer stack:** exact methods (branch-and-price column generation) for construction; CP for legality feasibility; LNS/metaheuristics for scale and recovery; simulation for what-if (digital-twin of the operation).
- **Explainability layer:** every assignment carries a human-readable justification (seniority rank, fatigue margin, cost delta vs. alternative) so schedulers and crews can understand and contest.
- **Human-in-the-loop guardrails:** optimization as decision support; approval workflows; immutable audit trails for regulators, unions, and safety departments.
- **Fatigue & FRMS module:** bio-mathematical model integration, proactive exposure alerts, regulator-friendly reporting.

### 7.2 Product capabilities
- Preferential bidding with modern UX (mobile app; "what would improve my bid?").
- Rule-aware swap/trading marketplace with approval flows.
- FRMS-aware scheduling and reporting.
- Real-time recovery cockpit with what-if scenarios and ranked proposals.
- Analytics: utilization, fairness audits (e.g., distribution of arduous duty), CBA impact modeling ("what does a new reserve rule cost?").
- Compliance engine: per-jurisdiction, per-contract validated rule sets; continuous regression suites.

### 7.3 Unfair-advantage questions for the builder
- Can we run a **league-grade optimizer** (hiring OR talent from AD OPT/IBS/Sabre/Jeppesen lineages + academics) — the scarcest ingredient?
- Can we license or partner on a **validated fatigue model**?
- Can we build credibility via **airline-in-the-loop R&D partnerships** (co-design with an LCC's scheduling department) rather than pure sales?

---

## 8. Business Case, Competitive Landscape, and Risks

### 8.1 Business case (figures are directional — validate)
- **Crew cost magnitude:** crew, chiefly pilots, is typically cited as the **#2 airline cost after fuel**, in the range of roughly **10–20%** of operating expenses depending on carrier type (long-haul network carriers at the high end). A large network carrier's crew bill runs **hundreds of millions of dollars annually**; even **1–3%** improvement from better pairing/rostering/recovery — the range industry analyses commonly cite for optimization gains — is **single-digit millions per year per carrier**.
- **Disruption cost:** industry studies (e.g., IATA-era analyses) have cited **tens of dollars per delay minute** scaling with aircraft size (widebody figures well above $100/min in current terms), plus the multi-hundred-thousand-dollar cost of a cancelled long-haul rotation. A chunk of avoidable delay/cancellation cost is **crew-related**; cutting even a fraction pays for a modern tool.
- **Retention & shortage:** the widely reported **pilot shortage** (and post-2020 crew attrition) makes roster quality a retention lever; better bidding outcomes reduce turnover and sick-time, and improve reserve morale.
- **Sale geometry:** SaaS licenses per crew member + implementation + ongoing rule-library maintenance; the wedge product (recovery engine) can be priced against measured disruption savings with a fast payback narrative.

### 8.2 Competitive/innovation landscape
- Incumbents (Sabre, Jeppesen — now Thoma Bravo-owned, Lufthansa Systems, IBS, AD OPT, Navitaire/Accelya) hold near-total market share; consolidation has thinned the field and shifted owners (Boeing→Jeppesen 2000, then Jeppesen→Thoma Bravo 2025; Blackstone→IBS 2019; Travelport→Accelya absorbing Navitaire 2021), concentrating legacy portfolios and adding PE cost-pressure on incumbents.
- Challenger space includes **point tools** (crew bid assistants, swap/messaging apps, roster viewers) and **regional/niche suites** (InteliSys, Hexaware AIRCREW, Hitit), plus **airline in-house builds** — but no vendor has yet established itself as the dominant *modern, cloud-native* full-platform replacement at scale. That absence is simultaneously the opportunity and the proof of barriers.
- Adjacent innovation to borrow from: airline digital-twin/what-if practices in OCC technology, crew-messaging apps, and the broader airline-IT move to cloud/data platforms.

### 8.3 Risks and moats (the honest half)
- **Sales cycles:** 12–24+ months, multiple stakeholders (ops, HR/labor, IT, safety, finance), conservative safety culture. High trust barrier.
- **Data access:** airlines own their data; realistic pairings/rosters for R&D are scarce; a credible open-data simulator or partner carrier is needed, not just a dataset.
- **Rule coverage cost:** each CBA is bespoke; full coverage is a multi-year build; errors are safety- and grievance-relevant. This complexity is the top barrier to entry — and the top moat for whoever accumulates the rule library.
- **Certification/liability:** positioning as decision support mitigates, but fatigue/legality errors still carry reputational and legal exposure.
- **Incumbent countermoves:** discounts, roadmaps, and enormous switching costs (customization lock-in) protect installed bases.
- **Union/regulator scrutiny:** fairness, transparency, and auditability are existential requirements, not nice-to-haves.

---

## 9. Recommended Path to Market

1. **Wedge: Disruption Recovery Engine.** Ingest schedule + pairing + roster data from incumbent systems; deliver real-time re-rostering decision support with what-if. Pros: measured dollar savings fast, low integration risk, no "replace your core" ask, machine-readable ROI. Target: carriers with acute IROPS pain (network carriers, hubs).
2. **Layer: Crew Experience (bidding + trading + transparency).** Differentiated UX and fairness analytics sell themselves to crews and unions; creates internal champions and daily users; data feedback loop for the optimizer.
3. **Platform: full modern rostering suite** for **greenfield buyers** — new LCCs/regional/charter/cargo carriers without legacy debt, and carriers mid-system-integration — then migration plays for incumbents.
4. **Moat builders along the way:** certified rule library, fatigue-model integration, fairness analytics, audit trails, published benchmark (e.g., open solver benchmark vs. legacy batch on standard test cases).
5. **Partner to de-risk:** fatigue-model providers, OR academics, an anchor airline for co-design.

---

## 10. Key Questions Before Committing

- Which segment has the most acute pain and shortest sales cycle: regional, LCC, cargo, charter, or legacy network?
- What is the realistic price point vs. the quantified cost of a disruption event and of crew attrition?
- Can we license a validated bio-mathematical fatigue model, or must we partner/build?
- Decision-support-only positioning: does it clear the certification and liability hurdle with safety departments and unions?
- Can we obtain realistic schedule/pairing/roster data (partner carrier, or a high-fidelity open-data simulator) for R&D?
- Do we have (or can we hire) the OR talent to genuinely beat incumbents on solution quality — the product's core differentiator?

---

## 11. Sources and Verification Plan

### Fetched and verified this session (primary / authoritative)
- **EASA FTL — Regulation (EU) No 83/2014**, EUR-Lex CELEX 32014R0083 — flight-time limits (100 h/28 d, 900 h/year, 1,000 h/12 months) verified from the regulation text: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32014R0083
- **14 CFR Part 117 (FAR 117)**, eCFR — flight-time and FDP cumulative limits (100 h/672 h, 1,000 h/365 d, 60 FDP-h/168 h, 190 FDP-h/672 h) verified via the eCFR XML API (title 14, part 117, version 2025-01-01): https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-117
- **Jeppesen — Crew Rostering product page** (confirms current product offering under airline crew optimization): https://ww2.jeppesen.com/airline-crew-optimization-solutions/crew-rostering/
- **Wikipedia** (vendor ownership/background, treated as tertiary): [Jeppesen](https://en.wikipedia.org/wiki/Jeppesen) (Thoma Bravo parent), [Lufthansa Systems](https://en.wikipedia.org/wiki/Lufthansa_Systems), [Sabre Corporation](https://en.wikipedia.org/wiki/Sabre_Corporation), [IBS Software](https://en.wikipedia.org/wiki/IBS_Software), [Crew scheduling](https://en.wikipedia.org/wiki/Crew_scheduling)

### Referenced but not fully fetched (verify before relying on them)
- **ICAO FRMS framework** — Doc 9966 (*Manual for the Oversight of Fatigue Management Approaches*) and the ICAO fatigue-management program page: https://www.icao.int/safety/fatiguemanagement/ (page was bot-walled to our fetcher; Doc 9966 designation is well established)
- **FAA AC 120-103** (FRMS advisory circular).
- **Crew-cost shares and delay-cost figures** (§8.1 are directional): verify against IATA economics publications, airline 10-K/annual reports, and analyst studies before contracting KPIs.
- **Industry software roundups** (low authority; useful only for name listings — not figures): e.g., https://gitnux.org/best/flight-crew-rostering-software/

### Not retrieved this session (require working search/keys)
- Recent trade-press coverage (ATW, FlightGlobal) and carrier system-selection announcements; recent pilot-shortage statistics; startup landscape details. The in-GUI `web_search` tool needs a `DEEPSEEK_API_KEY` credential (stored via the web Models page) or a configured literal `apiKey`/`apiKeyEnv` in the `web-search-deepseek` settings; engine access via curl was mostly bot-blocked.