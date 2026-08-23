"""Phase-2 recovery: exact picker + pairing surgery.

Replaces the Phase-1 per-gap greedy with:
  - **solve_picker**: an exact CP-style selection over the WHOLE candidate
    pool — a small branch-and-bound over one action per gap with a
    "each crew used at most once" constraint, maximizing covered gaps and then
    minimizing action cost. For production this is the drop-in point for a
    real MIP/CP engine (OR-Tools, Gurobi); the prototype keeps it stdlib-only.
  - **find_surgery**: "relieve at leg N" — splits an over-long pairing so the
    legality-broken crew keeps a legal prefix and a fresh crew (reserve/swap)
    takes the suffix, turning the previously *refused* case into a proposal.
  - every candidate is validated end-to-end with the RuleEngine before being
    proposed; outcome measurement applies the chosen set to a copy of the
    world and reports the delta.
"""
import copy
from typing import Dict, List, Optional

from .legality import build_duties, evaluate, pairing_duty
from .model import Crew, Pairing, World
from .risk import uncovered_flights
from .rules import CrewCheck, RuleEngine

GAP_VALUE = 100.0        # covering a gap dominates any single action score
ADVISORY_ACCUMULATOR_RULES = (
    "ft-672h", "ft-28d", "duty-168h", "duty-672h", "ft-365d", "ft-year",
)


# ----------------------------------------------------------------- helpers
def _crew(w: World, cid: str) -> Optional[Crew]:
    return next((c for c in w.crews if c.id == cid), None)


def _no_overlap(duties) -> bool:
    ds = sorted(duties, key=lambda d: (d.start, d.pairing_id))
    for a, b in zip(ds, ds[1:]):
        if b.start < a.end:
            return False
    return True


def _crew_can_take(w: World, engine: RuleEngine, cid: str, pid: str):
    """Would crew cid remain fully legal after taking pairing pid on top of
    their existing schedule? Returns (ok, margin_after)."""
    p = w.pairing(pid)
    duties = list(build_duties(w).get(cid, [])) + [pairing_duty(w, p, cid)]
    if not _no_overlap(duties):
        return False, None
    crew = _crew(w, cid)
    if crew is None:
        return False, None
    cc = engine.check(crew, duties)
    if cc.ok:
        return True, None
    return False, cc.min_margin


def describe_pairing(w: World, pid: str) -> str:
    p = w.pairing(pid)
    f0 = w.flight(p.flight_ids[0])
    return f"{f0.id} {f0.origin}->{f0.dest} ({len(p.flight_ids)} legs)"


# ------------------------------------------------------------- gap analysis
def build_gap_candidates(w: World, engine: RuleEngine, checks: Dict[str, CrewCheck]):
    """One gap record per uncovered pairing (cancelled flights excluded)."""
    un = uncovered_flights(w, checks)
    gaps: Dict[str, list] = {}
    for f, reason in un:
        if f.cancelled:
            continue
        for p in w.pairings:
            if f.id in p.flight_ids:
                gaps.setdefault(p.id, []).append(f)

    from collections import defaultdict
    crews_of_pairing: Dict[str, List[str]] = defaultdict(list)
    for cid, pid in w.assignments:
        crews_of_pairing[pid].append(cid)

    out = []
    for pid in sorted(gaps):
        flights = gaps[pid]
        f0 = flights[0]
        broken = [cid for cid in crews_of_pairing.get(pid, [])
                  if checks.get(cid) and checks[cid].worst == "violation"]
        orig = broken[0] if broken else (crews_of_pairing.get(pid, [None])[0])
        group = (_crew(w, orig).group if orig and _crew(w, orig) else "P")
        candidates = []
        # reserve callouts (same base, same group, on reserve that day)
        for cid in w.reserves.get(f0.day, []):
            c = _crew(w, cid)
            if c is None or c.group != group or c.base != f0.origin:
                continue
            ok, margin = _crew_can_take(w, engine, cid, pid)
            if ok:
                candidates.append({"kind": "reserve", "crew_id": cid,
                                   "score": 10.0, "legality_ok": True,
                                   "margin_after": margin,
                                   "note": "reserve callout"})
        # crew swaps (same base/group, not broken, not on reserve)
        for c in w.crews:
            if c.group != group or c.base != f0.origin:
                continue
            if c.id == orig or c.id in w.reserves.get(f0.day, []):
                continue
            ok, margin = _crew_can_take(w, engine, c.id, pid)
            if ok:
                candidates.append({"kind": "swap", "crew_id": c.id,
                                   "score": 20.0 + c.seniority * 0.1,
                                   "legality_ok": True, "margin_after": margin,
                                   "note": "crew swap"})
        candidates.sort(key=lambda x: (x["score"], x["crew_id"]))
        out.append({"pid": pid, "flight_desc": describe_pairing(w, pid),
                    "base": f0.origin, "day": f0.day, "group": group,
                    "broken": broken, "orig": orig, "candidates": candidates})
    return out


# ------------------------------------------------------------- exact picker
def solve_picker(gaps: List[dict]):
    """Exact selection: one action per gap (or none), each crew used at most
    once. Maximizes covered gaps (GAP_VALUE per gap) and then minimizes action
    score. Deterministic DFS with a best-case bound; tiny instances here."""
    n = len(gaps)
    best_each = [max([GAP_VALUE - c["score"] for c in g["candidates"]] or [0.0])
                 for g in gaps]
    best_sel: List[Optional[dict]] = [None] * n
    best_val = -1.0
    used: set = set()
    sel: List[Optional[dict]] = [None] * n
    cur_val = 0.0
    explored = 0

    def dfs(i: int):
        nonlocal best_val, cur_val, explored
        explored += 1
        if i == n:
            if cur_val > best_val:
                best_val = cur_val
                best_sel[:] = [dict(c) if c else None for c in sel]
            return
        bound = cur_val + sum(best_each[i:])
        if bound <= best_val:
            return
        gap = gaps[i]
        # try each candidate (best first), then "leave uncovered"
        for c in gap["candidates"]:
            if c["crew_id"] in used:
                continue
            sel[i] = c
            used.add(c["crew_id"])
            cur_val += GAP_VALUE - c["score"]
            dfs(i + 1)
            cur_val -= GAP_VALUE - c["score"]
            used.discard(c["crew_id"])
            sel[i] = None
        sel[i] = None
        dfs(i + 1)

    dfs(0)
    covered = sum(1 for c in best_sel if c is not None)
    return best_sel, {"covered": covered, "value": round(best_val, 1),
                      "explored_nodes": explored}


# ------------------------------------------------------------ pairing surgery
def _suffix_crew_candidates(w: World, suffix_pid: str, group: str, base: str,
                            day: int, used: set, exclude: set):
    """Ordered (crew_id, kind, score) list of crews who could legally take the
    suffix pairing. Legality is re-validated by the caller on the split world."""
    out = []
    for cid in w.reserves.get(day, []):
        c = _crew(w, cid)
        if c and c.group == group and c.base == base and cid not in used and cid not in exclude:
            out.append((cid, "reserve", 10.0))
    for c in w.crews:
        if c.group != group or c.base != base:
            continue
        if c.id in used or c.id in exclude or c.id in w.reserves.get(day, []):
            continue
        out.append((c.id, "swap", 20.0 + c.seniority * 0.1))
    return sorted(out, key=lambda x: (x[2], x[0]))


def find_surgery(w: World, engine: RuleEngine, gap: dict, checks: Dict[str, CrewCheck],
                 used: set):
    """Split an over-long pairing at leg boundary k so the broken crew keeps a
    legal prefix and a fresh crew takes the suffix. Returns a proposal dict or
    None if no fully-legal split exists."""
    p = w.pairing(gap["pid"])
    n = len(p.flight_ids)
    if n < 2:
        return None
    pid = gap["pid"]
    broken = gap["broken"][0] if gap["broken"] else None
    orig = gap["orig"]
    before_violations = sum(1 for c in checks.values() if c.worst == "violation")
    exclude = set(gap["broken"]) | ({orig} if orig else set())

    for k in range(1, n):
        w2 = copy.deepcopy(w)
        w2.pairings = [pp for pp in w2.pairings if pp.id != pid]
        pre, suf = f"{pid}#pre{k}", f"{pid}#suf{k}"
        w2.pairings.append(Pairing(pre, p.flight_ids[:k]))
        w2.pairings.append(Pairing(suf, p.flight_ids[k:]))
        w2.assignments = [a for a in w2.assignments
                          if not (a[1] == pid and broken is not None and a[0] == broken)]
        # healthy crews on the old pairing keep flying the prefix
        w2.assignments = [(cid, pre if pid_ == pid else pid_) for cid, pid_ in w2.assignments]
        if broken is not None:
            w2.assignments.append((broken, pre))

        for cid, kind, score in _suffix_crew_candidates(w2, suf, gap["group"],
                                                        gap["base"], gap["day"],
                                                        used, exclude):
            ok, margin = _crew_can_take(w2, engine, cid, suf)
            if not ok:
                continue
            w3 = copy.deepcopy(w2)
            w3.assignments.append((cid, suf))
            after = evaluate(w3, engine)
            busted = sum(1 for c in after.values() if c.worst == "violation")
            if busted > before_violations:
                continue
            return {
                "kind": "surgery", "pairing_id": pid, "split_index": k,
                "prefix_id": pre, "suffix_id": suf, "crew_id": cid,
                "suffix_kind": kind, "score": 15.0, "legality_ok": True,
                "broken_crew": broken, "original_crew": orig,
                "flight_desc": gap["flight_desc"],
                "margin_after": margin,
                "note": (f"split at leg {k}: {broken or orig} keeps legs 1..{k} "
                         f"({pre}); {cid} covers legs {k + 1}..{n} ({suf})"),
            }
    return None


# ---------------------------------------------------------------- proposals
def generate(w: World, engine: RuleEngine, checks: Dict[str, CrewCheck]):
    """Proposals for the current (disrupted) state: exact picker over the
    candidate pool, surgery fallback for unfixable gaps, then advisories."""
    gaps = build_gap_candidates(w, engine, checks)
    sel, picker_stats = solve_picker(gaps)

    proposals: List[dict] = []
    used: set = set()
    for i, gap in enumerate(gaps):
        cand = sel[i]
        if cand is not None:
            d = dict(cand)
            d.update({"pairing_id": gap["pid"], "flight_desc": gap["flight_desc"],
                      "original_crew": gap["orig"],
                      "broken_crew": gap["broken"][0] if gap["broken"] else None})
            used.add(d["crew_id"])
            proposals.append(d)
        else:
            surgery = find_surgery(w, engine, gap, checks, used)
            if surgery:
                used.add(surgery["crew_id"])
                proposals.append(surgery)
            else:
                proposals.append({
                    "kind": "advisory", "pairing_id": gap["pid"],
                    "flight_desc": gap["flight_desc"], "crew_id": None,
                    "original_crew": gap["orig"], "score": 0.0,
                    "legality_ok": True,
                    "note": ("no legal action found (pairing itself exceeds "
                             "FDP limits and no legal split/single-crew option "
                             "exists) — manual re-time needed")})

    # --- secondary relief: close remaining violations by offloading duties ---
    reliefs = secondary_relief(w, engine, checks, proposals, used)
    proposals.extend(reliefs)

    # advisory rows: accumulator exposure & at-risk monitors
    handled = {p["crew_id"] for p in proposals if p.get("crew_id")}
    handled |= {p["relieved_crew"] for p in proposals if p.get("relieved_crew")}
    for cid, cc in checks.items():
        if cid in handled or cc.ok:
            continue
        if cc.worst == "violation" and any(
                v.rule_id.endswith(ADVISORY_ACCUMULATOR_RULES) for v in cc.violations):
            proposals.append({"kind": "advisory", "pairing_id": "-",
                              "flight_desc": "-", "crew_id": cid,
                              "original_crew": None, "score": 0.0,
                              "legality_ok": True,
                              "note": "accumulator exposure — schedule review / rest day"})
        elif cc.worst == "at_risk":
            proposals.append({"kind": "monitor", "pairing_id": "-",
                              "flight_desc": "-", "crew_id": cid,
                              "original_crew": None, "score": 0.0,
                              "legality_ok": True,
                              "note": "at-risk duty — delay may breach; monitor before sign-off"})

    outcome = measure(w, engine, proposals)
    outcome["picker"] = picker_stats
    return proposals, outcome


def secondary_relief(w: World, engine: RuleEngine, checks: Dict[str, CrewCheck],
                     proposals: List[dict], used: set):
    """Close residual violations after the main selection + surgery.

    A pairing can carry more than one broken crew (e.g., an augmented
    two-pilot pairing, or a swap that over-loaded a healthy crew): the picker
    covers the pairing once, but the *other* broken crew stays on it and stays
    in violation. `relieve` offloads that crew's duty to a legality-clean
    taker. Validated end-to-end: the relieved crew must heal, the taker must
    stay fully legal, and no previously-ok crew may become broken.
    """
    w2 = copy.deepcopy(w)
    for p in proposals:
        if p["kind"] in ("reserve", "swap", "surgery") and p.get("crew_id") and p.get("legality_ok"):
            _apply(w2, p)
    checks2 = evaluate(w2, engine)
    before_broken = {cid for cid, c in checks2.items() if c.worst == "violation"}
    reliefs: List[dict] = []
    used = set(used)

    for cid in sorted(before_broken):
        crew = _crew(w2, cid)
        if crew is None or cid in used:
            continue
        my_pids = sorted(pid for c2, pid in w2.assignments if c2 == cid)
        for pid in my_pids:
            # 1) preferred: release without replacement — the pairing is often
            #    already covered by the main selection (reserve/swap), so the
            #    broken crew can simply be taken off it.
            w3r = copy.deepcopy(w2)
            w3r.assignments = [a for a in w3r.assignments
                               if not (a[0] == cid and a[1] == pid)]
            chk3r = evaluate(w3r, engine)
            others = sorted(c2 for c2, p2 in w3r.assignments if p2 == pid)
            if chk3r[cid].worst != "violation" and \
                    not ({cc for cc, c3 in chk3r.items() if c3.worst == "violation"}
                         - before_broken):
                reliefs.append({
                    "kind": "relieve", "pairing_id": pid,
                    "flight_desc": describe_pairing(w2, pid),
                    "crew_id": None, "relieved_crew": cid,
                    "original_crew": cid, "broken_crew": cid,
                    "score": 12.0, "legality_ok": True, "margin_after": None,
                    "note": (f"relieve {cid}: released from {pid} "
                             f"(pairing keeps {', '.join(others) or 'no other crew — needs manual cover'})"),
                })
                used.add(cid)
                break
            # 2) fallback: re-crew with a legality-clean taker
            p_obj = w2.pairing(pid)
            f0 = w2.flight(p_obj.flight_ids[0])
            cands: List[tuple] = []
            for rc in w2.reserves.get(f0.day, []):
                c = _crew(w2, rc)
                if c and c.group == crew.group and c.base == crew.base and rc not in used:
                    ok, margin = _crew_can_take(w2, engine, rc, pid)
                    if ok:
                        cands.append((rc, "reserve", 10.0, margin))
            for c in w2.crews:
                if c.group != crew.group or c.base != crew.base:
                    continue
                if c.id in used or c.id == crew.id or c.id in w2.reserves.get(f0.day, []):
                    continue
                ok, margin = _crew_can_take(w2, engine, c.id, pid)
                if ok:
                    cands.append((c.id, "swap", 20.0 + c.seniority * 0.1, margin))
            cands.sort(key=lambda x: (x[2], x[0]))
            matched = False
            for taker, kind, score, margin in cands:
                w3 = copy.deepcopy(w2)
                w3.assignments = [a for a in w3.assignments
                                  if not (a[0] == cid and a[1] == pid)]
                w3.assignments.append((taker, pid))
                chk3 = evaluate(w3, engine)
                if chk3[cid].worst == "violation":
                    continue                      # relief did not heal the crew
                if {cc for cc, c3 in chk3.items() if c3.worst == "violation"} - before_broken:
                    continue                      # creates a new violation
                reliefs.append({
                    "kind": "relieve", "pairing_id": pid,
                    "flight_desc": describe_pairing(w2, pid),
                    "crew_id": taker, "relieved_crew": cid,
                    "original_crew": cid, "broken_crew": cid,
                    "score": 15.0 + score / 10.0, "legality_ok": True,
                    "margin_after": margin,
                    "note": f"relieve {cid}: re-crew {pid} with {taker} ({kind})",
                })
                used.add(taker)
                used.add(cid)
                matched = True
                break
            if matched:
                break
    return reliefs


# ------------------------------------------------------------ measurement
def _apply(w2: World, p: dict) -> None:
    if p["kind"] in ("reserve", "swap", "relieve"):
        broken = p.get("broken_crew", p.get("relieved_crew"))
        w2.assignments = [a for a in w2.assignments
                          if not (a[1] == p["pairing_id"]
                                  and (broken is None or a[0] == broken))]
        if p.get("crew_id"):
            w2.assignments.append((p["crew_id"], p["pairing_id"]))
    elif p["kind"] == "surgery":
        pid = p["pairing_id"]
        pair = next(pp for pp in w2.pairings if pp.id == pid)
        w2.pairings = [pp for pp in w2.pairings if pp.id != pid]
        pre, suf = p["prefix_id"], p["suffix_id"]
        w2.pairings.append(Pairing(pre, pair.flight_ids[:p["split_index"]]))
        w2.pairings.append(Pairing(suf, pair.flight_ids[p["split_index"]:]))
        broken = p.get("broken_crew")
        w2.assignments = [a for a in w2.assignments
                          if not (a[1] == pid and broken is not None and a[0] == broken)]
        w2.assignments = [(cid, pre if pid_ == pid else pid_) for cid, pid_ in w2.assignments]
        if broken is not None:
            w2.assignments.append((broken, pre))
        w2.assignments.append((p["crew_id"], suf))


def measure(w: World, engine: RuleEngine, proposals: List[dict]) -> dict:
    """Apply the executable proposals to a copy of the world and measure the
    effect on uncovered flights and violations."""
    w2 = copy.deepcopy(w)
    before = _counts(w, engine)
    applied = 0
    for p in proposals:
        if p["kind"] not in ("reserve", "swap", "surgery", "relieve"):
            continue
        if not p.get("legality_ok"):
            continue
        if p["kind"] == "relieve":
            if not (p.get("crew_id") or p.get("relieved_crew")):
                continue
        elif not p.get("crew_id"):
            continue
        _apply(w2, p)
        applied += 1
    after = _counts(w2, engine)
    return {"proposals_applied": applied, **before,
            **{f"after_{k}": v for k, v in after.items()}}


def _counts(w: World, engine: RuleEngine) -> dict:
    checks = evaluate(w, engine)
    un = uncovered_flights(w, checks)
    non_cancelled = [f for f, r in un if not f.cancelled]
    violations = sum(1 for c in checks.values() if c.worst == "violation")
    return {"violations": violations,
            "uncovered_non_cancelled": len(non_cancelled)}