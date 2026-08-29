"""Reporting: JSON + self-contained HTML dashboards for the risk radar."""
import html
import json
import os
from typing import Dict, List, Optional

from .model import World
from .rules import CrewCheck
from .risk import rank_crews, reserve_gaps, uncovered_flights, summary

RULE_DESCRIPTIONS = {
    "FAR117.ft-672h": "Flight time > 100 h in any 672 consecutive hours",
    "FAR117.ft-365d": "Flight time > 1,000 h in any 365 consecutive days",
    "FAR117.duty-168h": "Duty > 60 h in any 168 consecutive hours",
    "FAR117.duty-672h": "Duty > 190 h in any 672 consecutive hours",
    "FAR117.fdp-per-duty": "Per-duty FDP exceeds Table B limit",
    "co.ft-per-fdp": "Company flight-time guardrail (not a FAR 117 limit)",
    "FAR117.rest-min": "Rest between duties below minimum",
    "EASA-FTL.ft-28d": "Flight time > 100 h / 28 consecutive days",
    "EASA-FTL.ft-year": "Flight time > 900 h / calendar year",
    "EASA-FTL.ft-12mo": "Flight time > 1,000 h / 12 months (not exercised in 7d demo)",
    "EASA-FTL.duty-168h": "Duty > 60 h / 168 h (approximation)",
    "EASA-FTL.duty-672h": "Duty > 190 h / 672 h (approximation)",
    "EASA-FTL.fdp-per-duty": "Per-duty FDP exceeds limit",
    "EASA-FTL.ft-per-fdp": "Per-duty flight time exceeds cap",
    "EASA-FTL.rest-min": "Rest between duties below minimum",
}


def snapshot(w: World, checks: Dict[str, CrewCheck], regime: str) -> Dict[str, object]:
    """Plain-data snapshot of the risk radar for one scenario."""
    un = uncovered_flights(w, checks)
    rows = []
    for cid, c, score in rank_crews(checks):
        crew = next((c for c in w.crews if c.id == cid), None)
        rows.append({
            "id": cid,
            "group": crew.group if crew else "?",
            "base": crew.base if crew else "?",
            "worst": c.worst,
            "score": score,
            "min_margin_min": c.min_margin,
            "duty_count": c.duty_count,
            "total_flight_min": c.total_flight_min,
            "total_duty_min": c.total_duty_min,
            "violations": [
                {"rule": v.rule_id, "severity": v.severity, "message": v.message,
                 "margin_min": v.margin_min}
                for v in c.violations
            ],
        })
    return {
        "regime": regime,
        "summary": summary(w, checks, un),
        "crews": rows,
        "uncovered": [
            {"id": f.id, "day": f.day, "from": f.origin, "to": f.dest,
             "reason": reason, "dep": f.dep}
            for f, reason in un
        ],
        "gaps": reserve_gaps(w, checks, un),
    }


def emit_json(path: str, scenarios: Dict[str, Dict[str, object]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(scenarios, fh, indent=2, default=str)


def emit_html(path: str, name: str, snap: Dict[str, object],
              proposals: Optional[List[dict]] = None,
              whatif: Optional[Dict[str, object]] = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    s = snap["summary"]
    cards = [
        ("Crews", s["crews"]), ("Flights", s["flights"]), ("Duties", s["duties"]),
        ("Violations", s["violations"], "bad"), ("At risk", s["at_risk"], "warn"),
        ("Uncovered flights", s["uncovered"], "bad"),
    ]
    card_html = "".join(
        f'<div class="card {"c-" + (c[2] if len(c) > 2 else "ok")}"><div class="num">{c[1]}</div>'
        f'<div class="lab">{c[0]}</div></div>'
        for c in cards)

    rows = []
    for c in snap["crews"]:
        badge = "b-ok" if c["worst"] == "ok" else ("b-warn" if c["worst"] == "at_risk" else "b-bad")
        detail = "<br>".join(html.escape(v["message"]) for v in c["violations"]) or "—"
        rows.append(
            f'<tr><td>{html.escape(c["id"])}</td><td>{c["group"]}</td><td>{c["base"]}</td>'
            f'<td><span class="badge {badge}">{c["worst"]}</span></td>'
            f'<td>{c["score"]}</td><td>{c["min_margin_min"]:+.0f}</td>'
            f'<td>{c["duty_count"]}</td><td class="dim">{detail}</td></tr>')
    crew_table = "\n".join(rows) or "<tr><td colspan=8>All clear</td></tr>"

    vrows = []
    for c in snap["crews"]:
        for v in c["violations"]:
            cls = "b-bad" if v["severity"] == "violation" else "b-warn"
            vrows.append(
                f'<tr><td>{html.escape(c["id"])}</td>'
                f'<td><span class="badge {cls}">{v["severity"]}</span></td>'
                f'<td>{html.escape(v["rule"])}</td>'
                f'<td class="dim">{html.escape(V_DESC.get(v["rule"], v["rule"]))}</td>'
                f'<td>{v["margin_min"]:+.0f}</td></tr>')
    vtable = "\n".join(vrows) or "<tr><td colspan=5>No rule findings</td></tr>"

    urows = "".join(
        f'<tr><td>{u["id"]}</td><td>D{u["day"]}</td><td>{u["from"]}→{u["to"]}</td>'
        f'<td>{html.escape(u["reason"])}</td></tr>'
        for u in snap["uncovered"]) or "<tr><td colspan=4>None</td></tr>"

    gro = "".join(
        f'<tr><td>{html.escape(k)}</td><td class="dim">{html.escape("; ".join(v))}</td></tr>'
        for k, v in snap["gaps"].items()) or "<tr><td colspan=2>No reserve gaps</td></tr>"

    rb = "".join(f"<li>{html.escape(k)}: {v}</li>" for k, v in s["rule_breakdown"].items())

    prop_html = ""
    if proposals:
        prows = "\n".join(
            f'<tr><td><span class="badge {"b-ok" if p.get("legality_ok") else "b-warn"}">'
            f'{html.escape(p["kind"])}</span></td>'
            f'<td>{html.escape(p["pairing_id"])}</td>'
            f'<td>{html.escape(p["flight_desc"])}</td>'
            f'<td>{html.escape(p.get("crew_id") or "—")}</td>'
            f'<td>{p.get("score")}</td>'
            f'<td class="dim">{html.escape(p["note"])}</td></tr>'
            for p in proposals)
        prop_html = ('<h2>Recovery proposals</h2>'
                     '<table><tr><th>Action</th><th>Pairing</th><th>Flight</th>'
                     f'<th>Crew</th><th>Score</th><th>Note</th></tr>{prows}</table>')

    wf_html = ""
    if whatif:
        dn = whatif["do_nothing"]
        pl = whatif["plan"]
        dels = whatif["deltas"]
        rows = "".join(
            f'<tr><td>{label}</td><td>{dn[key]}</td><td>{pl[key]}</td>'
            f'<td class="dim">{dels[key]:+d}</td></tr>'
            for key, label in (("violations", "Violations"),
                               ("at_risk", "At-risk crews"),
                               ("uncovered", "Uncovered flights")))
        fat = pl.get("fatigue") or {}
        fatrows = "".join(
            f'<tr><td>{html.escape(r["crew_id"])}</td><td>{r["index"]}</td>'
            f'<td>{r["level"]}</td></tr>'
            for r in fat.get("top", []))
        wf_html = ('<h2>What-if: do nothing vs. action plan</h2>'
                   '<table><tr><th>Metric</th><th>Do nothing</th><th>Plan</th>'
                   f'<th>Delta</th></tr>{rows}</table>'
                   '<div class="meta">Plan applied '
                   f'{pl.get("applied")} actions · reserve callouts {pl.get("reserve_callouts")} · '
                   f'fatigue mean {fat.get("mean")} · high-fatigue crews {fat.get("high")}</div>')
        if fatrows:
            wf_html += ('<h3>Highest fatigue crews after plan</h3>'
                        '<table><tr><th>Crew</th><th>Index</th><th>Level</th>'
                        f'</tr>{fatrows}</table>')

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Recovery Engine — Risk Radar · {html.escape(name)}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font: 14px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif; background:#0d1117; color:#e6edf3; margin:24px; }}
h1 {{ font-size:20px; }} h2 {{ font-size:15px; margin-top:28px; border-bottom:1px solid #21262d; padding-bottom:6px; }}
.meta {{ color:#8b949e; font-size:12px; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:16px 0; }}
.card {{ background:#161b22; border:1px solid #21262d; border-radius:10px; padding:12px 18px; min-width:110px; text-align:center; }}
.card .num {{ font-size:26px; font-weight:700; }} .card .lab {{ color:#8b949e; font-size:11px; }}
.c-bad .num {{ color:#f85149; }} .c-warn .num {{ color:#d29922; }}
table {{ border-collapse:collapse; width:100%; margin:10px 0; font-size:13px; }}
th, td {{ border:1px solid #21262d; padding:6px 9px; text-align:left; vertical-align:top; }}
th {{ background:#161b22; color:#8b949e; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
.badge {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:11px; font-weight:600; }}
.b-ok {{ background:#12261b; color:#3fb950; }} .b-warn {{ background:#2c2310; color:#d29922; }} .b-bad {{ background:#3a1314; color:#f85149; }}
.dim {{ color:#8b949e; }} ul {{ margin:6px 0; padding-left:18px; }} code {{ background:#161b22; padding:1px 5px; border-radius:4px; }}
.note {{ background:#121d2f; border:1px solid #1f3a5f; border-radius:8px; padding:10px 14px; font-size:12px; color:#8fb7e8; margin-top:22px; }}
</style></head><body>
<h1>Disruption Recovery Engine — Risk Radar</h1>
<div class="meta">Scenario: <code>{html.escape(name)}</code> · Regime: <code>{html.escape(snap["regime"])}</code><br>
Rule activity: {rb}</div>
<div class="cards">{card_html}</div>
<h2>Crews by risk</h2>
<table><tr><th>Crew</th><th>Grp</th><th>Base</th><th>Status</th><th>Score</th><th>Min margin</th><th>Duties</th><th>Findings</th></tr>{crew_table}</table>
<h2>All rule findings</h2>
<table><tr><th>Crew</th><th>Severity</th><th>Rule</th><th>Description</th><th>Margin (min)</th></tr>{vtable}</table>
<h2>Uncovered flights</h2>
<table><tr><th>Flight</th><th>Day</th><th>Sector</th><th>Reason</th></tr>{urows}</table>
<h2>Reserve coverage gaps</h2>
<table><tr><th>Position</th><th>Details</th></tr>{gro}</table>
{prop_html}
{wf_html}
<div class="note"><b>Prototype notice.</b> Cumulative limits are the verified FAR 117 / EASA FTL values from primary
sources (EUR-Lex CELEX 32014R0083; 14 CFR part 117 via eCFR). Per-duty FDP tables are the <b>exact</b> FAR 117
Table B/C values from eCFR (2025-01-01). Minimum rest, report/debrief buffers, the EASA per-duty scheme, and the
company flight-time guardrail remain simplifications. Synthetic data only; a real pilot carrier is required for
Phase 1 validation.</div>
</body></html>"""
    with open(path, "w") as fh:
        fh.write(doc)


V_DESC = RULE_DESCRIPTIONS