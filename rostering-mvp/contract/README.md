# Feed-Adapters Data Contract — `crew-recovery-contract/1.0`

What a carrier's systems must push into the recovery engine, and in which
shape. The demo **dogfoods** this contract: `run_demo.py` exports the synthetic
world as `out/contract_sample.json` via `proto/contract.py` and validates it —
if the demo world can't conform, the contract (or the generator) is wrong.

> Status: **v1.0 draft** — the exact field set for your pilot carrier should be
> negotiated in the Phase-0 shadow run (architecture doc §12).

## 1. Why a contract

The recovery engine is a decision-support overlay on the airline's existing
scheduling stack. It never owns the master data — it consumes a consistent
snapshot of it. A versioned contract makes the integration testable (the
adapter layer's only job is "make reality look like the contract") and keeps
the engine free of carrier-specific ETL quirks.

## 2. Feed classes

| Feed | Content | Latency class |
|---|---|---|
| Planned state | flights, pairings, rosters/assignments | daily batch (D-1) + ad-hoc |
| Operational state | actual/estimated times, delays, cancellations, aircraft swaps | streaming, < 1 min |
| Crew state | check-in, sick, position, legality accumulators | streaming, < 1 min |
| Static master | fleet, bases, crew groups, qualifications, CBA rule pack | weekly / on change |
| External events | weather, ATC, airport ops | streaming, advisory |

## 3. Payload schema (see `proto/contract.py` for the exporting side)

Top level: `{ "schema", "flights": [...], "crews": [...], "pairings": [...],
"reserves": [...] }`.

### `flights[]`
| Field | Type | Unit | Description |
|---|---|---|---|
| `id` | string | — | stable flight id |
| `day` | int | — | day offset from horizon start |
| `dep_min` | int | min | scheduled departure (day×1440 + minutes-of-day) |
| `arr_min` | int | min | scheduled arrival |
| `origin` / `dest` | string | station code | — |
| `delay_min` | int | min | current accrued delay |
| `cancelled` | bool | — | flight not operating |

### `crews[]`
| Field | Type | Description |
|---|---|---|
| `id`, `base`, `group` (P/FA), `seniority` | string/int | identity |
| `acclimated` | bool | US/EASA acclimatisation state (unknown → EASA Tables 3/4) |
| `hist_flight_672h`, `hist_flight_365d`, `hist_flight_12mo` | int min | pre-existing flight time in each cumulative window |
| `hist_duty_168h`, `hist_duty_336h`, `hist_duty_672h` | int min | pre-existing duty in each cumulative window (incl. the EASA 110 h / 14 d tier) |

### `pairings[]`
| Field | Type | Description |
|---|---|---|
| `id` | string | pairing id |
| `flight_ids` | string[] | ordered legs |
| `crew_ids` | string[] | crews assigned (pilot + cabin) — must be non-empty |

### `reserves[]`
`{ "day", "crew_id" }` — reserve availability per day.

## 4. Adapter responsibilities

- **Sources:** files/SFTP, REST (or the vendor's API), message queue, CDC on
  the legacy DB; screen-scraping is explicitly a last resort (brittle).
- **Normalization:** all feeds normalized to this schema; timestamps in
  minutes-of-horizon with an explicit day-0 convention.
- **Staleness:** every feed carries a generation timestamp; the engine must
  know **how stale each feed is** (per-feed staleness telemetry) and degrade
  to read-only when staleness exceeds policy.
- **Idempotency:** snapshots are full-state deltas (replace per id), never
  append-only logs — replay must converge.

## 5. Open questions for the pilot carrier

1. Which feeds can be exposed, and at what latency (files vs API vs queue)?
2. Who owns the mapping from carrier-native IDs to contract IDs (pairings,
   crew numbers, flight numbers — day-of-operation vs equipment numbers)?
3. Legality accumulators: does the carrier expose them, or must the engine
   reconstruct them from duty history (the demo reconstructs from the roster)?
4. Which rule pack (FAR 117 vs EASA FTL + which CBA) is the pilot's baseline?
5. Staleness policy per feed (e.g., ops state > 5 min = suspend proposals)?