"""Company research viewer: one self-contained HTML file built from the run's envelopes.

Everything shown comes from the envelopes' published claims, their evidence items and the summary
built from them; the page adds no facts. A reader can find a company (search, filters, sort), read
its summary with numbered sources, compare companies side by side, and verify each fact: every value
links to the page it was quoted from, with the quoted span, retrieval time and content SHA-256.
Works offline, on desktop and on phones; the data is embedded as JSON and parsed once.
"""
from __future__ import annotations

import html
import json
from typing import Any

from .synthesis import GROUP_NAMES, LEGAL_FORMS, NACE_DIVISIONS, PLACEHOLDER_TITLES, PLATFORM_NAMES, READABLE_ENTITY, ROLE_NAMES, _comparable, _place, _placeholder

MAX_ROLES = 24
MAX_LOCATIONS = 16
MAX_SPAN = 160
FIN_FIELDS = ("revenue", "operating_result", "annual_result", "assets", "debt")
LIST_FIELDS = {"registered_roles", "registered_subunits", "summary_profile"}
ACCOUNTING_PLAIN = {"filing_observed": "annual accounts filed", "required_by_legal_form": "required to file (legal form)",
                    "threshold_or_activity_dependent": "depends on size or activity", "not_required": "not required to file"}


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None and str(value) not in ("", "None") else None
    except (TypeError, ValueError):
        return None


def _short(value: Any, limit: int = 300) -> Any:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def viewer_record(envelope: dict[str, Any]) -> dict[str, Any]:
    """Compact, display-ready record for one envelope (short keys keep large runs small)."""
    org = envelope.get("organisation_number") or ""
    claims = envelope.get("claims") or []
    evidence = {e.get("id"): e for e in envelope.get("evidence") or []}
    sources: list[dict[str, Any]] = []
    source_index: dict[str, int] = {}

    def src(eid: str) -> int | None:
        item = evidence.get(eid)
        if not item or not item.get("source_url"):
            return None
        url = item["source_url"]
        key = f"{url}\n{item.get('content_sha256')}"
        if key not in source_index:
            source_index[key] = len(sources)
            sources.append({"u": url, "c": item.get("source_class"), "r": item.get("retrieved_at"), "h": item.get("content_sha256")})
        return source_index[key]

    def ev_refs(claim: dict[str, Any]) -> list[list[Any]]:
        refs = []
        for eid in claim.get("evidence_ids") or []:
            index = src(eid)
            if index is not None:
                span = " ".join(str((evidence.get(eid) or {}).get("claim_span") or "").split())
                refs.append([index, span[:MAX_SPAN] + ("…" if len(span) > MAX_SPAN else ""), (evidence.get(eid) or {}).get("effective_at")])
        return refs

    by_field: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        by_field.setdefault(str(claim.get("field")), []).append(claim)

    def avail(field: str) -> list[dict[str, Any]]:
        return [c for c in by_field.get(field) or [] if c.get("availability") == "available"]

    def val(field: str) -> Any:
        items = avail(field)
        return items[0].get("value") if items else None

    def state(field: str) -> str | None:
        items = by_field.get(field) or []
        return items[0].get("availability") if items else None

    def first_src(field: str) -> int | None:
        items = avail(field) or by_field.get(field) or []
        for claim in items:
            for eid in claim.get("evidence_ids") or []:
                index = src(eid)
                if index is not None:
                    return index
        return None

    # Claims table (everything published, with its state) - the verification layer.
    table = []
    for claim in claims:
        field = claim.get("field")
        if field == "summary_profile":
            continue
        value = claim.get("value")
        if field == "registered_roles" and isinstance(value, list):
            shown = f"{len([r for r in value if not r.get('inactive')])} active role records (listed under Leadership)"
        elif field == "registered_subunits" and isinstance(value, list):
            shown = f"{len(value)} registered sub-units (listed under Locations)"
        elif field == "financial_history" and isinstance(value, dict):
            shown = "; ".join(f"{k.replace('_', ' ')} {value[k]:,.0f}" for k in FIN_FIELDS if isinstance(value.get(k), (int, float)))
        elif field == "accounting_obligation" and isinstance(value, dict):
            shown = " · ".join(str(v) for v in (ACCOUNTING_PLAIN.get(value.get("classification"), value.get("classification")),
                                                 value.get("latest_submitted_accounts") and f"latest year {value.get('latest_submitted_accounts')}") if v)
        elif field == "dated_news":
            shown = _short(claim.get("title") or value, 120)
        elif field == "former_names" and isinstance(value, list):
            shown = "; ".join(f"{n.get('name')} (until {str(n.get('until') or '')[:10]})" for n in value if isinstance(n, dict))
        elif field == "group_accounts" and isinstance(value, list):
            shown = "group (konsern) accounts for " + ", ".join(str(v)[:4] for v in value)
        elif field == "reporting_period" and isinstance(value, dict):
            shown = f"{value.get('fraDato')} – {value.get('tilDato')}"
        elif isinstance(value, bool):
            shown = "yes" if value else "no"
        else:
            shown = _short(value, 200)
        period = claim.get("reporting_period")
        row = [field, shown, claim.get("availability"), ev_refs(claim),
               (f"{period.get('fraDato')} – {period.get('tilDato')}" if isinstance(period, dict) else str(period)) if period else None]
        table.append(row)

    # Annual accounts: latest year plus earlier years from the same response.
    fin = []
    period = val("reporting_period")
    if any(val(f) is not None for f in FIN_FIELDS) and isinstance(period, dict):
        fin.append({"from": period.get("fraDato"), "to": period.get("tilDato"), **{f: _num(val(f)) for f in FIN_FIELDS},
                    "s": first_src("revenue"), "c": _comparable(period)})
    for claim in sorted(avail("financial_history"), key=lambda c: str(((c.get("value") or {}).get("period") or {}).get("tilDato") or ""), reverse=True):
        item = claim.get("value") or {}
        p = item.get("period") or {}
        refs = ev_refs(claim)
        fin.append({"from": p.get("fraDato"), "to": p.get("tilDato"), **{f: _num(item.get(f)) for f in FIN_FIELDS},
                    "s": refs[0][0] if refs else None, "c": _comparable(p)})

    roles_all = [r for r in (val("registered_roles") or []) if isinstance(r, dict) and not r.get("inactive")]
    def role_label(r: dict[str, Any]) -> str:
        norwegian = r.get("role") or r.get("group") or ""
        english = ROLE_NAMES.get(str(r.get("role_code") or ""))
        return f"{english[:1].upper() + english[1:]} ({norwegian.lower()})" if english and norwegian else (norwegian or "Role")

    roles = [{"n": (" ".join(r["name"]) if isinstance(r.get("name"), list) else r.get("name")) or r.get("organisation_number"),
              "r": role_label(r), "c": r.get("role_code"), "d": r.get("last_changed")} for r in roles_all[:MAX_ROLES]]
    units = [u for u in (val("registered_subunits") or []) if isinstance(u, dict)]
    locs = [{"n": u.get("name"), "k": _place((u.get("address") or {}).get("kommune")), "e": u.get("employees"), "o": u.get("organisation_number")}
            for u in units[:MAX_LOCATIONS]]

    news = sorted(({"t": c.get("title") or c.get("value"), "d": str(c.get("published_at") or "")[:10], "u": c.get("url") or c.get("source_url"),
                    "e": ev_refs(c), **({"j": 1} if _placeholder(c) else {})} for c in avail("dated_news")), key=lambda n: str(n["d"]), reverse=True)
    run_day = str((envelope.get("run") or {}).get("completed_at") or "")[:10]
    if len(news) >= 2 and all(n["d"] == run_day for n in news):  # pages that print today's date
        for n in news:
            n["j"] = 1
    hiring = [{"k": c.get("kind"), "t": c.get("title"), "u": c.get("value") if str(c.get("value") or "").startswith("http") else c.get("url"),
               "d": str(c.get("posted_date") or "")[:10] or None, "pl": c.get("platform"), "o": c.get("openings_listed"), "e": ev_refs(c)}
              for c in avail("hiring_signal")]
    socials = [{"p": PLATFORM_NAMES.get(str(c.get("platform") or "").lower(), c.get("platform")), "u": c.get("value"), "e": ev_refs(c)} for c in avail("social_profile")]

    summary_claim = next((c for c in claims if c.get("field") == "summary_profile"), None) or {}
    url_index = {}
    for index, item in enumerate(sources):
        url_index.setdefault(item["u"], index)
    for source in summary_claim.get("sources") or []:
        for eid in source.get("evidence_ids") or []:
            if src(eid) is not None and source.get("url") not in url_index:
                url_index[source.get("url")] = src(eid)
    summary_sources = summary_claim.get("sources") or []
    summary = {
        "s": [{"k": s.get("key"), "l": s.get("label"), "t": s.get("text")} for s in summary_claim.get("sections") or []],
        "src": [[s.get("label"), url_index.get(s.get("url"), s.get("url"))] for s in summary_sources],
        "txt": None if summary_claim.get("sections") else summary_claim.get("value"),
    }

    changes = [{"f": str(c.get("field") or "").replace("claims.", ""), "t": c.get("change_type") or ("changed" if c.get("old_value") is not None and c.get("new_value") is not None else "added" if c.get("new_value") is not None else "removed"),
                "o": _short(c.get("old_value"), 160), "nv": _short(c.get("new_value"), 160), "d": c.get("effective_at"), "u": c.get("source_url")}
               for c in envelope.get("changes") or []]
    refresh = envelope.get("refresh") or {}
    events: list[list[Any]] = []
    for y in fin:
        if y.get("to"):
            label = y["to"][:4] if str(y.get("from") or "")[5:] == "01-01" and y["to"][5:] == "12-31" else f"{y.get('from')} – {y['to']}"
            events.append([y["to"], "accounts", f"Accounts period {label} ends" + (f": revenue NOK {y['revenue']:,.0f}" if y.get("revenue") is not None else ""), None])
    groups: dict[str, list[Any]] = {}
    for r in roles_all:
        code, stamp = str(r.get("group_code") or r.get("role_code") or ""), str(r.get("last_changed") or "")[:10]
        if code and stamp and stamp >= (groups.get(code) or ["", ""])[0]:
            groups[code] = [stamp, r.get("group") or r.get("role") or code]
    for code, (stamp, norwegian) in groups.items():
        english = GROUP_NAMES.get(code)
        holders = [(" ".join(r["name"]) if isinstance(r.get("name"), list) else r.get("name")) for r in roles_all
                   if str(r.get("group_code") or r.get("role_code") or "") == code and r.get("name")]
        events.append([stamp, "roles", f"{(english or norwegian).capitalize()} ({str(norwegian).lower()}) updated in the register" + (f"; now {', '.join(holders[:3])}" if holders else ""), None])
    for n in val("former_names") or []:
        if isinstance(n, dict) and n.get("until"):
            events.append([str(n["until"])[:10], "name", f"Name change: previously {n.get('name')}", None])
    for n in news[:8]:
        if n.get("d") and not n.get("j"):
            events.append([n["d"], "news", n.get("t"), n.get("u")])
    for c in envelope.get("changes") or []:
        events.append([str(c.get("effective_at") or c.get("retrieved_at") or "")[:10], "refresh",
                       f"{str(c.get('field') or '').replace('claims.', '').replace('_', ' ')} {c.get('change_type') or 'changed'} since the previous run", c.get("source_url")])
    if val("founded_date"):
        events.append([str(val("founded_date"))[:10], "founded", "Founded", None])
    events = sorted((e for e in events if e[0]), key=lambda e: e[0], reverse=True)[:16]
    form = val("legal_form")
    employees = _num(val("registry_employees"))
    latest = fin[0] if fin else {}
    previous = fin[1] if len(fin) > 1 else {}
    growth = None
    if _num(latest.get("revenue")) and _num(previous.get("revenue")) and previous["revenue"] > 0 and latest["revenue"] > 0:
        growth = round((latest["revenue"] - previous["revenue"]) / previous["revenue"] * 100, 1)
    return {
        "o": org,
        "n": val("legal_name") or (envelope.get("profile") or {}).get("name") or org,
        "f": form, "fd": LEGAL_FORMS.get(form or ""),
        "m": _place(val("municipality")) if val("municipality") else None,
        "ic": val("industry_code"), "il": val("industry_label"),
        "nd": (f"NACE {str(val('industry_code'))[:2]}: {NACE_DIVISIONS[str(val('industry_code'))[:2]]}" if str(val("industry_code") or "")[:2] in NACE_DIVISIONS else None),
        "rd": READABLE_ENTITY.format(org=org) if org else None,
        "ga": [str(v)[:4] for v in (val("group_accounts") or [])], "ev": events,
        "act": val("registered_activity"), "aS": first_src("registered_activity"), "rS": first_src("legal_name"),
        "acc": {"c": ACCOUNTING_PLAIN.get((val("accounting_obligation") or {}).get("classification"), (val("accounting_obligation") or {}).get("classification")) if isinstance(val("accounting_obligation"), dict) else None,
                "r": (val("accounting_obligation") or {}).get("reason") if isinstance(val("accounting_obligation"), dict) else None,
                "y": (val("accounting_obligation") or {}).get("latest_submitted_accounts") if isinstance(val("accounting_obligation"), dict) else None,
                "s": first_src("accounting_obligation")},
        "fn": list({str(n.get("name")).casefold(): {"n": n.get("name"), "u": str(n.get("until") or "")[:10]} for n in reversed(val("former_names") or []) if isinstance(n, dict)}.values())[::-1],
        "fnS": first_src("former_names"), "eS": first_src("registry_employees"),
        "e": employees, "fo": val("founded_date"),
        "bk": val("status_bankrupt") is True, "lq": val("status_liquidating") is True,
        "fin": fin, "fs": state("revenue"), "g": growth,
        "ro": roles, "roN": len(roles_all), "roS": first_src("registered_roles"),
        "lo": locs, "loN": len(units), "loS": first_src("registered_subunits"),
        "w": val("official_website"), "ws": state("official_website"), "wS": first_src("official_website"),
        "d": val("company_description"), "dS": first_src("company_description"),
        "so": socials, "nw": news, "hi": hiring,
        "sm": summary, "ch": changes,
        "rf": {"p": refresh.get("previous_run_id"), "w": str(refresh.get("previous_completed_at") or "")[:10] or None},
        "cl": table, "S": sources,
    }


def build_viewer_html(envelopes: list[dict[str, Any]], run: dict[str, Any] | None = None) -> str:
    run = run or {}
    records = [viewer_record(env) for env in envelopes]
    data = json.dumps({"run": run, "companies": records}, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/").replace("<!--", "<\\!--")
    title = f"Signalpost · {len(records)} Norwegian companies"
    return TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", data)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f7f9;--panel:#fff;--ink:#14171c;--muted:#5b6472;--line:#dde1e7;--accent:#1f5fbf;--accent-soft:#e8f0fc;--good:#1d7a46;--good-soft:#e6f4ec;--warn:#9a5b00;--warn-soft:#fdf2e1;--bad:#a8261b;--bad-soft:#fbe9e7;--radius:10px;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent)}
button,select,input{font:inherit}
button{cursor:pointer;-webkit-tap-highlight-color:transparent}
:focus-visible{outline:3px solid #7aa7ec;outline-offset:2px}
.top{background:#0f2747;color:#fff;padding:14px 20px}
.top h1{margin:0;font-size:19px;letter-spacing:.2px}
.top p{margin:2px 0 0;color:#c9d6ea;font-size:13px}
.top .row{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.top button{background:transparent;border:1px solid #6f8bb3;color:#fff;border-radius:8px;padding:6px 12px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;padding:14px 20px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:10px 12px;text-align:left}
.stat strong{display:block;font-size:20px}
.stat span{color:var(--muted);font-size:12.5px}
.stat[aria-pressed=true]{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);background:var(--accent-soft)}
.layout{display:grid;grid-template-columns:minmax(300px,380px) 1fr;gap:14px;padding:14px 20px 28px;align-items:start}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius)}
.finder{position:sticky;top:10px;display:flex;flex-direction:column;max-height:calc(100vh - 20px)}
.finder .controls{padding:12px;border-bottom:1px solid var(--line);display:grid;gap:8px}
.finder input[type=search]{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:#fff}
.filters{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.filters select{width:100%;padding:7px 8px;border:1px solid var(--line);border-radius:8px;background:#fff;min-width:0}
.bar{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.btn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 10px;color:var(--ink)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn:disabled{opacity:.5;cursor:default}
.list{overflow:auto;flex:1}
.item{display:flex;gap:10px;padding:10px 12px;border-bottom:1px solid var(--line);align-items:flex-start}
.item.active{background:var(--accent-soft)}
.item input{margin-top:4px;width:17px;height:17px;flex:none}
.item button.open{all:unset;cursor:pointer;flex:1;min-width:0;display:block}
.item strong{display:block;overflow-wrap:anywhere}
.item small{color:var(--muted);display:block}
.badges{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.badge{font-size:11.5px;border-radius:999px;padding:1px 8px;background:#eef0f3;color:#39424e;white-space:nowrap}
.badge.good{background:var(--good-soft);color:var(--good)}
.badge.warn{background:var(--warn-soft);color:var(--warn)}
.badge.bad{background:var(--bad-soft);color:var(--bad)}
.more{padding:10px 12px}
.profile{padding:18px 20px;min-width:0}
.profile h2{margin:0;font-size:23px;overflow-wrap:anywhere}
.sub{color:var(--muted)}
.head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start}
.actions{display:flex;gap:6px;flex-wrap:wrap}
.jump{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 4px;position:sticky;top:0;background:var(--panel);padding:6px 0;z-index:2}
.jump a{font-size:13px;text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 10px;color:var(--ink);background:#fff}
section{border-top:1px solid var(--line);padding:14px 0 6px;scroll-margin-top:52px}
section h3{margin:0 0 8px;font-size:16px}
.summary p{margin:0 0 8px}
.summary .lbl{font-weight:600}
.summary sup a,.ref{font-size:11.5px;text-decoration:none;background:var(--accent-soft);border-radius:4px;padding:0 4px;margin-left:2px}
.sources{font-size:13px;color:var(--muted);margin:6px 0 0;padding-left:20px}
.sources li{overflow-wrap:anywhere}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px}
.fact{border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:0}
.fact span{display:block;color:var(--muted);font-size:12.5px}
.fact strong{overflow-wrap:anywhere}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f3f5f8;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.up{color:var(--good)}.down{color:var(--bad)}
.muted{color:var(--muted)}
.empty{color:var(--muted);font-style:italic}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.ev{font-size:12.5px;color:var(--muted);overflow-wrap:anywhere}
.ev code{font-family:var(--mono);font-size:12px;background:#f3f5f8;border-radius:4px;padding:0 4px;overflow-wrap:anywhere}
details summary{cursor:pointer;color:var(--accent)}
.ask{display:flex;gap:6px;margin-top:6px}
.ask input{flex:1;min-width:0;padding:8px 10px;border:1px solid var(--line);border-radius:8px}
.answer{margin-top:8px;background:#f8fafc;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.overlay{position:fixed;inset:0;background:rgba(15,25,40,.45);display:none;align-items:flex-start;justify-content:center;padding:24px;z-index:20;overflow:auto}
.overlay.open{display:flex}
.dialog{background:#fff;border-radius:12px;max-width:1200px;width:100%;padding:18px 20px;box-shadow:0 10px 40px rgba(0,0,0,.25)}
.dialog h2{margin:0 0 4px;font-size:20px}
.cmp th:first-child,.cmp td:first-child{position:sticky;left:0;background:#fff;z-index:1;min-width:140px}
.cmp th{min-width:180px}
.back{display:none}
.brief{background:#f5f8fd;border:1px solid #d9e4f5;border-radius:10px;padding:12px 14px;margin:12px 0 4px}
.brief p{margin:0 0 6px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:8px}
.metric{background:#fff;border:1px solid var(--line);border-radius:8px;padding:6px 9px;min-width:0}
.metric span{display:block;color:var(--muted);font-size:12px}
.metric strong{font-size:15px;overflow-wrap:anywhere}
.trend{display:flex;align-items:flex-end;gap:4px;height:34px;margin-top:4px}
.trend i{display:block;width:14px;background:#7aa7ec;border-radius:2px 2px 0 0}
.trend i.neg{background:#e3a29b}
.timeline{list-style:none;margin:0 0 8px;padding:0;border-left:2px solid var(--line)}
.timeline li{position:relative;padding:3px 0 8px 14px}
.timeline li:before{content:"";position:absolute;left:-6px;top:9px;width:10px;height:10px;border-radius:50%;background:#7aa7ec}
.timeline li.recent:before{background:var(--warn)}
.timeline time{font-variant-numeric:tabular-nums;color:var(--muted);margin-right:6px}
.hash{display:none}
.showhash .hash{display:inline}
.n-short{display:none}
.cmp-cards{display:none}
.best{font-weight:700}
.fab{display:none}
.fact strong{overflow-wrap:break-word;hyphens:auto}
.skip{position:absolute;left:-999px}.skip:focus{left:10px;top:10px;background:#fff;padding:6px;z-index:30}
@media (max-width:900px){
 .layout{grid-template-columns:1fr;padding:10px 10px 24px}
 .stats{padding:8px 10px 0;display:flex;overflow-x:auto;gap:8px;scrollbar-width:thin}
 .stat{flex:0 0 auto;min-width:118px;padding:7px 10px}
 .stat strong{font-size:17px}
 .top h1{font-size:17px}
 .top p{font-size:12px}
 .top button{padding:4px 10px;font-size:13px}
 .finder{position:static;max-height:none}
 .list{max-height:none}
 body.detail .finder,body.detail .stats{display:none}
 body:not(.detail) .profile{display:none}
 .back{display:inline-block;margin-bottom:10px}
 .profile{padding:14px}
 .overlay{padding:0}
 .n-full{display:none}
 .n-short{display:inline}
 .summary sup a,.ref{display:inline-block;min-width:24px;min-height:22px;text-align:center;padding:2px 5px}
 .tablewrap table{font-size:13px}
 th,td{padding:6px}
 .cmp-table{display:none}
 #s-ev table,#s-ev tbody,#s-ev tr,#s-ev td{display:block;width:100%}
 #s-ev tr:first-child{display:none}
 #s-ev tr{border-bottom:2px solid var(--line);padding:6px 0}
 #s-ev td{border:0;padding:3px 6px}
 #s-ev td[data-l]:before{content:attr(data-l);display:block;font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
 .item input{width:24px;height:24px}
 .btn{min-height:40px}
 .fab{display:block;position:fixed;right:14px;bottom:14px;z-index:15;border-radius:999px;padding:10px 16px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
 .fab[hidden]{display:none}
 .cmp-cards{display:block}
 .cmp-card{border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:8px 0}
 .cmp-card h4{margin:0 0 4px;font-size:14px}
 .cmp-card div{padding:4px 0;border-top:1px dashed var(--line)}
 .cmp-card div span{display:block;overflow-wrap:anywhere}
 .cmp-card div span:first-child{color:var(--muted);font-size:12px}
 .dialog{border-radius:0;min-height:100%;padding:14px}
 .top{padding:12px 14px}
}
</style>
</head>
<body>
<a class="skip" href="#q">Skip to search</a>
<header class="top"><div class="row"><div><h1>Signalpost — Norwegian company profiles</h1><p id="runline"></p></div><button type="button" id="about-open">How to read and verify</button></div></header>
<div class="stats" id="stats" role="group" aria-label="Quick filters"></div>
<button type="button" class="btn primary fab" id="fab-compare" hidden>Compare (0)</button>
<main class="layout">
 <aside class="panel finder" aria-label="Find companies">
  <div class="controls">
   <label class="sr" for="q" style="font-weight:600">Find a company</label>
   <input id="q" type="search" placeholder="Name, org. no., place, industry, person" autocomplete="off">
   <div class="filters">
    <select id="f-form" aria-label="Legal form"><option value="">All legal forms</option></select>
    <select id="f-has" aria-label="Has information"><option value="">Any information</option><option value="fin">Has annual accounts</option><option value="web">Has verified website</option><option value="social">Has social profiles</option><option value="news">Has dated news</option><option value="hire">Has hiring signal</option><option value="recent">Changed in the last 90 days</option><option value="change">Changed since last run</option><option value="noweb">No verified website</option></select>
    <select id="f-ind" aria-label="Industry"><option value="">All industries</option></select>
    <select id="f-muni" aria-label="Municipality"><option value="">All municipalities</option></select>
    <select id="f-status" aria-label="Register status"><option value="">Any register status</option><option value="active">Not bankrupt or winding up</option><option value="adverse">Bankrupt or winding up</option></select>
    <select id="sort" aria-label="Sort"><option value="name">Sort: name</option><option value="rev">Sort: revenue (high first)</option><option value="growth">Sort: revenue growth</option><option value="emp">Sort: employees</option><option value="news">Sort: latest news</option></select>
   </div>
   <div class="bar" id="saved"></div>
   <div class="bar"><span id="count" aria-live="polite"></span><span><button class="btn" id="export" type="button" title="Download the filtered companies as JSON">Export</button> <button class="btn primary" id="compare-open" type="button" disabled>Compare (0)</button></span></div>
  </div>
  <div class="list" id="list"></div>
 </aside>
 <article class="panel profile" id="profile" aria-live="polite"></article>
</main>
<div class="overlay" id="compare" role="dialog" aria-modal="true" aria-labelledby="cmp-title"><div class="dialog"><div class="head"><div><h2 id="cmp-title">Compare companies</h2><p class="sub">Up to four companies side by side. Values marked ↗ link to their source; open a company for the full evidence.</p></div><div class="actions"><button class="btn" id="cmp-csv" type="button">Download CSV</button><button class="btn" id="cmp-link" type="button">Copy link</button><button class="btn" id="cmp-clear" type="button">Clear</button><button class="btn primary" id="cmp-close" type="button">Close</button></div></div><div class="tablewrap" id="cmp-body"></div></div></div>
<div class="overlay" id="about" role="dialog" aria-modal="true" aria-labelledby="about-title"><div class="dialog" style="max-width:760px"><div class="head"><h2 id="about-title">How to read and verify these profiles</h2><button class="btn primary" id="about-close" type="button">Close</button></div>
<p><strong>Find.</strong> Search by company name, organisation number, municipality, industry, registered activity or a role holder's name. The tiles at the top and the filters narrow the list; sort by revenue, growth, employees or latest news.</p>
<p><strong>Compare.</strong> Tick the box next to up to four companies (or use “Add to compare” on a profile), then press Compare. The comparison can be downloaded as CSV or shared as a link.</p>
<p><strong>Verify.</strong> Summary sentences carry numbered sources (statements about what is missing name the source that was checked where there is one). Every value in a profile links to the page it was read from; under “Evidence” each published claim shows the exact quoted text (span), when the page was fetched and the SHA-256 of the fetched content, so it can be checked against the live page.</p>
<p><strong>Sources.</strong> Brønnøysund Register Centre (Enhetsregisteret entity, roles and sub-unit records; Regnskapsregisteret annual accounts), NAV's public vacancy register, and each company's own website. A website is shown only when it is proven to belong to this exact legal entity; profiles and news come only from such a verified site. LinkedIn, review sites and the press are not read.</p>
<p><strong>Missing is not zero.</strong> “Not available” means a source was checked and had no value; “failed” or “blocked” means the source could not be read in this run. Neither is ever shown as zero.</p>
<p class="muted" id="about-run"></p></div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
var RAW=JSON.parse(document.getElementById('data').textContent),RUN=RAW.run||{},DATA=RAW.companies||[];
var $=function(s){return document.querySelector(s)};
var esc=function(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})};
var norm=function(v){return String(v||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/ø/g,'o').replace(/æ/g,'ae').replace(/å/g,'a')};
var store={get:function(k,d){try{var v=localStorage.getItem(k);return v?JSON.parse(v):d}catch(e){return d}},set:function(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
var NF=new Intl.NumberFormat('en-GB',{maximumFractionDigits:0});
var nok=function(v){return v==null?'—':NF.format(v)};var nk=function(v){return v==null?'—':'<span class="n-full">'+NF.format(v)+'</span><span class="n-short">'+short(v)+'</span>'};
var short=function(v){if(v==null)return '—';var a=Math.abs(v);return a>=1e9?(v/1e9).toFixed(2)+' bn':a>=1e6?(v/1e6).toFixed(1)+' m':a>=1e4?NF.format(v/1e3)+' k':NF.format(v)};
var FIELD_LABELS={organisation_number:'Organisation number',legal_name:'Legal name',legal_form:'Legal form',municipality:'Municipality',industry_code:'Industry code',industry_label:'Industry',registry_employees:'Employees (register)',founded_date:'Founded',status_bankrupt:'Bankrupt',status_liquidating:'Being wound up',accounting_obligation:'Accounting obligation',revenue:'Revenue',operating_result:'Operating result',annual_result:'Annual result',assets:'Total assets',debt:'Debt',reporting_period:'Reporting period',registered_roles:'Registered roles',registered_subunits:'Registered sub-units',official_website:'Official website',company_description:'Website description',social_profile:'Social profile',dated_news:'Dated news',hiring_signal:'Hiring signal',registered_activity:'Registered activity',former_names:'Former names',financial_history:'Earlier annual accounts'};
var STATE_LABELS={available:'available',not_available:'not available',not_applicable:'not applicable',ambiguous:'not confirmed',blocked:'blocked',failed:'failed'};
DATA.forEach(function(x){
 x._news=x.nw.filter(function(n){return !n.j}).length?x.nw.filter(function(n){return !n.j})[0].d:'';x._rev=x.fin.length?x.fin[0].revenue:null;
 x._nw=x.nw.filter(function(n){return !n.j});x._hay=norm([x.n,x.o,x.m,x.ic,x.il,x.nd,x.act,x.w,(x.ro||[]).map(function(r){return r.n}).join(' '),(x.fn||[]).map(function(f){return f.n}).join(' ')].join(' '));
});
var byOrg={};DATA.forEach(function(x){byOrg[x.o]=x});
var cmp=store.get('signalpost-compare',[]).filter(function(o){return byOrg[o]}).slice(0,4);
var tile=null,selected=null,shown=200;
var RUN_DAY=(RUN.completed_at||new Date().toISOString()).slice(0,10),SINCE=new Date(new Date(RUN_DAY+'T00:00:00Z').getTime()-90*864e5).toISOString().slice(0,10);
DATA.forEach(function(x){x._recent=(x.ev||[]).filter(function(e){return e[1]!=='founded'&&e[1]!=='accounts'&&e[0]>=SINCE&&e[0]<=RUN_DAY})});
var has={recent:function(x){return x._recent.length>0},fin:function(x){return x.fin.length>0},web:function(x){return !!x.w},social:function(x){return x.so.length>0},news:function(x){return x._nw.length>0},hire:function(x){return x.hi.length>0},change:function(x){return x.ch.length>0},noweb:function(x){return !x.w}};
function runline(){var done=(RUN.completed_at||'').slice(0,16).replace('T',' ');$('#runline').textContent=DATA.length+' companies · run '+(RUN.run_id||'—')+(done?' · completed '+done+' UTC':'')+' · facts link to their sources';$('#about-run').textContent='This file: run '+(RUN.run_id||'—')+', started '+(RUN.started_at||'—')+', completed '+(RUN.completed_at||'—')+'. Built from the run\'s envelopes; it adds no information of its own.'}
function stats(){var defs=[['all','companies',function(){return true}],['fin','with annual accounts',has.fin],['web','verified websites',has.web],['social','with social profiles',has.social],['news','with dated news',has.news],['hire','with hiring signals',has.hire]];defs.push(['recent','changed in the last 90 days',has.recent]);if(DATA.some(has.change))defs.push(['change','changed since last run',has.change]);$('#stats').innerHTML=defs.map(function(d){var n=d[0]==='all'?DATA.length:DATA.filter(d[2]).length;return '<button type="button" class="stat" data-tile="'+d[0]+'" aria-pressed="'+((tile||'all')===d[0])+'"><strong>'+NF.format(n)+'</strong><span>'+esc(d[1])+'</span></button>'}).join('');Array.prototype.forEach.call(document.querySelectorAll('[data-tile]'),function(b){b.onclick=function(){tile=b.dataset.tile==='all'?null:b.dataset.tile;$('#f-has').value=tile||'';shown=200;stats();list()}})}
function filtered(){var q=norm($('#q').value).trim(),terms=q?q.split(/\s+/):[],form=$('#f-form').value,ind=$('#f-ind').value,muni=$('#f-muni').value,h=$('#f-has').value,st=$('#f-status').value,sort=$('#sort').value;var rows=DATA.filter(function(x){return terms.every(function(t){return x._hay.indexOf(t)>=0})&&(!form||x.f===form)&&(!ind||String(x.ic||'').slice(0,2)===ind)&&(!muni||x.m===muni)&&(!h||has[h](x))&&(!st||(st==='adverse')===(x.bk||x.lq))});var key={name:function(a,b){return a.n.localeCompare(b.n,'nb')},rev:function(a,b){return (b._rev==null?-Infinity:b._rev)-(a._rev==null?-Infinity:a._rev)},growth:function(a,b){return (b.g==null?-Infinity:b.g)-(a.g==null?-Infinity:a.g)},emp:function(a,b){return (b.e==null?-1:b.e)-(a.e==null?-1:a.e)},news:function(a,b){return b._news.localeCompare(a._news)}}[sort];return rows.sort(key)}
function badges(x){var b=[];if(x.bk)b.push('<span class="badge bad">bankrupt</span>');if(x.lq)b.push('<span class="badge bad">winding up</span>');if(x.fin.length&&x.fin[0].revenue!=null)b.push('<span class="badge">rev. NOK '+esc(short(x.fin[0].revenue))+(x.g!=null&&x.fin[0].c&&x.fin[1]&&x.fin[1].c&&Math.abs(x.g)<=200?' · '+(x.g>=0?'+':'−')+Math.abs(x.g).toFixed(0)+'%':'')+'</span>');if(x.e!=null)b.push('<span class="badge">'+NF.format(x.e)+' employees</span>');if(x.w)b.push('<span class="badge good">website</span>');if(x.so.length)b.push('<span class="badge good">'+x.so.length+' social</span>');if(x._nw.length)b.push('<span class="badge good">'+x._nw.length+' news</span>');if(x.ga&&x.ga.length)b.push('<span class="badge warn">parent accounts</span>');if(x.hi.length)b.push('<span class="badge good">hiring</span>');if(x.ch.length)b.push('<span class="badge warn">'+x.ch.length+' changes</span>');if(x._recent.length)b.push('<span class="badge warn">recent change '+esc(x._recent[0][0])+'</span>');return '<span class="badges">'+b.join('')+'</span>'}
function list(){var rows=filtered();$('#count').textContent=NF.format(rows.length)+' of '+NF.format(DATA.length)+' companies';$('#list').innerHTML=rows.slice(0,shown).map(function(x){var on=cmp.indexOf(x.o)>=0;return '<div class="item'+(selected&&selected.o===x.o?' active':'')+'"><input type="checkbox" data-cmp="'+x.o+'" '+(on?'checked':'')+' aria-label="Compare '+esc(x.n)+'"><button type="button" class="open" data-org="'+x.o+'"><strong>'+esc(x.n)+'</strong><small>'+esc(x.o)+' · '+esc(x.f||'—')+' · '+esc(x.m||'municipality not reported')+'</small><small>'+esc(x.il||'')+'</small>'+badges(x)+'</button></div>'}).join('')+(rows.length>shown?'<div class="more"><button class="btn" type="button" id="more">Show '+Math.min(200,rows.length-shown)+' more of '+NF.format(rows.length-shown)+'</button></div>':'')+(rows.length?'':'<div class="more empty">No company matches. Clear the search or filters.</div>');Array.prototype.forEach.call(document.querySelectorAll('[data-org]'),function(b){b.onclick=function(){open(b.dataset.org,true)}});Array.prototype.forEach.call(document.querySelectorAll('[data-cmp]'),function(c){c.onchange=function(){toggleCmp(c.dataset.cmp,c.checked)}});var m=$('#more');if(m)m.onclick=function(){shown+=200;list()};if(!selected&&rows.length&&window.innerWidth>900)open(rows[0].o,false);cmpButton()}
var saved=store.get('signalpost-saved-searches',[]);
function current(){return {q:$('#q').value,f:$('#f-form').value,i:$('#f-ind').value,m:$('#f-muni').value,h:$('#f-has').value,s:$('#f-status').value,o:$('#sort').value}}
function savedBar(){$('#saved').innerHTML='<span>'+(saved.length?saved.map(function(v,i){return '<button type="button" class="btn" data-saved="'+i+'" title="Apply this saved search">'+esc(v.label)+'</button>'}).join(' '):'No saved searches')+'</span><button type="button" class="btn" id="save-search">Save search</button>';Array.prototype.forEach.call(document.querySelectorAll('[data-saved]'),function(b){b.onclick=function(){var v=saved[+b.dataset.saved].v;$('#q').value=v.q;$('#f-form').value=v.f;$('#f-ind').value=v.i||'';$('#f-muni').value=v.m||'';$('#f-has').value=v.h;$('#f-status').value=v.s;$('#sort').value=v.o;tile=v.h||null;shown=200;stats();list()}});$('#save-search').onclick=function(){var v=current(),label=[v.q,v.f,v.h&&$('#f-has').selectedOptions[0].text,v.s&&$('#f-status').selectedOptions[0].text].filter(Boolean).join(' · ')||'All companies';saved=[{label:label.slice(0,40),v:v}].concat(saved.filter(function(s){return s.label!==label})).slice(0,6);store.set('signalpost-saved-searches',saved);savedBar()}}
function toggleCmp(org,on){cmp=cmp.filter(function(o){return o!==org});if(on){if(cmp.length>=4){alert('Compare holds up to four companies. Remove one first.');list();return}cmp.push(org)}store.set('signalpost-compare',cmp);cmpButton();if(selected&&selected.o===org)profile();Array.prototype.forEach.call(document.querySelectorAll('[data-cmp="'+org+'"]'),function(c){c.checked=on})}
function cmpButton(){var b=$('#compare-open');b.textContent='Compare ('+cmp.length+')';b.disabled=cmp.length<1;var f=$('#fab-compare');if(f){f.textContent='Compare ('+cmp.length+')';f.hidden=cmp.length<1}}
function srcMini(x,i){var s=x.S[i];if(i==null||!s)return '';return ' <a class="ref" href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer" title="Source: '+esc(s.u)+' · fetched '+esc(s.r||'')+'">↗</a>'}
function srcLink(x,i,label){var s=x.S[i];if(i==null||!s)return '';return ' <a class="ref" href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer" title="'+esc(s.u)+' · fetched '+esc(s.r||'')+'">'+esc(label||'source')+' ↗</a>'}
function evList(x,refs){if(!refs||!refs.length)return '';return refs.map(function(r){var s=x.S[r[0]]||{};return '<div class="ev">“<code>'+esc(r[1])+'</code>” — <a href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer">'+esc(s.u)+'</a> · fetched '+esc((s.r||'').slice(0,19).replace('T',' '))+(r[2]?' · effective '+esc(r[2]):'')+'<span class="hash"> · SHA-256 <code>'+esc(s.h||'')+'</code></span></div>'}).join('')}
function open(org,user){selected=byOrg[org]||null;if(user){document.body.classList.add('detail');try{history.replaceState(null,'','#org='+org)}catch(e){}}profile();list();if(user&&window.innerWidth<=900)window.scrollTo(0,0)}
function sumHtml(x){var sm=x.sm||{},src=sm.src||[];src=src.map(function(s){return {l:s[0],u:typeof s[1]==='number'?(x.S[s[1]]||{}).u:s[1]}});var link=function(t){return esc(t).replace(/\[(\d+(?:, \d+)*)\]/g,function(_,ns){return '<sup>'+ns.split(', ').map(function(n){var s=src[+n-1];return s?'<a href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer" title="'+esc(s.l)+'">'+n+'</a>':n}).join(' ')+'</sup>'})};if(sm.s&&sm.s.length)return sm.s.filter(function(s){return s.k!=='brief'}).map(function(s){return '<p><span class="lbl">'+esc(s.l)+':</span> '+link(s.t)+'</p>'}).join('')+(src.length?'<details><summary>Sources ('+src.length+')</summary><ol class="sources">'+src.map(function(s){return '<li>'+esc(s.l)+' — <a href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer">'+esc(s.u)+'</a></li>'}).join('')+'</ol></details>':'');return sm.txt?'<p>'+esc(sm.txt)+'</p>':'<p class="empty">No summary was produced for this company.</p>'}
function finHtml(x){if(!x.fin.length)return '<p class="empty">'+(x.fs==='not_applicable'?'This legal form does not file annual accounts.':x.fs==='failed'||x.fs==='blocked'?'The accounts register could not be read in this run.':'No annual accounts were returned by Regnskapsregisteret. Missing figures are not zero.')+'</p>';var rows=[['revenue','Revenue'],['operating_result','Operating result'],['annual_result','Annual result'],['assets','Total assets'],['debt','Debt']];var yrs=x.fin;var head='<tr><th>NOK</th>'+yrs.map(function(y){return '<th class="num">'+esc(y.to&&y.from&&y.from.slice(5)==='01-01'&&y.to.slice(5)==='12-31'?y.to.slice(0,4):(y.from||'')+' – '+(y.to||''))+'</th>'}).join('')+(yrs.length>1?'<th class="num">Change</th>':'')+'</tr>';var comp=yrs.length>1&&yrs[0].c&&yrs[1].c;var body=rows.map(function(r){var a=yrs[0][r[0]],b=yrs.length>1?yrs[1][r[0]]:null,ch='';var cls=function(up){return r[0]==='debt'?'muted':(up?'up':'down')};if(yrs.length>1&&!comp){ch='<span class="muted" title="periods of different length">n/a</span>'}else if(yrs.length>1&&a!=null&&b!=null&&b>0&&a>0){var p=(a-b)/b*100;ch=a>=2*b?'<span class="'+cls(true)+'">×'+(a/b).toFixed(1)+'</span>':'<span class="'+cls(p>=0)+'">'+(p>=0?'+':'−')+Math.abs(p).toFixed(1)+'%</span>'}else if(yrs.length>1&&a!=null&&b!=null){ch='<span class="muted">'+(a>=b?'+':'−')+nok(Math.abs(a-b))+'</span>'}return '<tr><th>'+r[1]+'</th>'+yrs.map(function(y){return '<td class="num">'+nk(y[r[0]])+'</td>'}).join('')+(yrs.length>1?'<td class="num">'+ch+'</td>':'')+'</tr>'}).join('');var srcs=yrs.map(function(y){return y.s}).filter(function(v,i,a){return v!=null&&a.indexOf(v)===i});return '<div class="tablewrap"><table>'+head+body+'</table></div><p class="ev">'+(x.ga&&x.ga.length?'The company\'s own (parent-company) accounts; the register also holds group (konsern) accounts for '+esc(x.ga.join(', '))+'. ':'Accounts as filed with Regnskapsregisteret. ')+'Change compares the latest period with the one before when both cover twelve months.'+srcs.map(function(i){return srcLink(x,i,'accounts')}).join('')+'</p>'}
function briefHtml(x){var sm=x.sm||{},b=(sm.s||[]).filter(function(s){return s.k==='brief'})[0];var src=(sm.src||[]).map(function(s){return {l:s[0],u:typeof s[1]==='number'?(x.S[s[1]]||{}).u:s[1]}});var link=function(t){return esc(t).replace(/\[(\d+(?:, \d+)*)\]/g,function(_,ns){return '<sup>'+ns.split(', ').map(function(n){var s=src[+n-1];return s?'<a href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer" title="'+esc(s.l)+'">'+n+'</a>':n}).join(' ')+'</sup>'})};var y=x.fin[0]||{},m=[];var cmpOk=x.fin.length>1&&x.fin[0].c&&x.fin[1].c&&x.g!=null&&Math.abs(x.g)<=200;m.push([(x.ga&&x.ga.length?'Own revenue':'Revenue')+(y.to?' '+(y.to||'').slice(0,4):''),y.revenue==null?'—':'NOK '+short(y.revenue)+(cmpOk?' ('+(x.g>=0?'+':'−')+Math.abs(x.g).toFixed(0)+'%)':''),y.s]);m.push([y.c===false?'Result for the period':'Annual result',y.annual_result==null?'—':'NOK '+short(y.annual_result),y.s]);m.push(['Employees',x.e==null?'not reported':NF.format(x.e),x.eS]);m.push(['Website',x.w?'verified':(STATE_LABELS[x.ws]||'none'),x.wS]);var nn=x._nw;m.push(['Dated news',nn.length?nn.length+(nn.length>=20?'+':'')+' (latest '+nn[0].d+')':'none found',null,nn.length?nn[0].u:null]);var cp=x.hi.filter(function(h){return h.k==='careers_page'})[0],po=x.hi.filter(function(h){return h.k!=='careers_page'});m.push(['Hiring',po.length?po.length+' posting(s)':cp?(cp.o===false?'careers page, no openings stated':'careers page'):'none found',null,po.length?po[0].u:cp?cp.u:null]);var revs=x.fin.slice().reverse().filter(function(f){return f.revenue!=null}),mx=Math.max.apply(null,revs.map(function(f){return Math.abs(f.revenue)}).concat([1]));var trend=revs.length>1?'<div class="metric"><span>Revenue trend '+esc((revs[0].to||'').slice(0,4))+'–'+esc((revs[revs.length-1].to||'').slice(0,4))+'</span><div class="trend" aria-hidden="true">'+revs.map(function(f){return '<i class="'+(f.revenue<0?'neg':'')+'" style="height:'+Math.max(3,Math.round(Math.abs(f.revenue)/mx*34))+'px" title="'+esc((f.to||'').slice(0,4))+': NOK '+esc(nok(f.revenue))+'"></i>'}).join('')+'</div></div>':'';return '<div class="brief">'+(b?'<p><strong>In brief.</strong> '+link(b.t)+'</p>':'')+'<div class="metrics">'+m.map(function(v){var link=v[2]!=null?srcMini(x,v[2]):v[3]?' <a class="ref" href="'+esc(v[3])+'" target="_blank" rel="noopener noreferrer">↗</a>':'';return '<div class="metric"><span>'+esc(v[0])+link+'</span><strong>'+esc(v[1])+'</strong></div>'}).join('')+trend+'</div></div>'}
function profile(){var x=selected,el=$('#profile');if(!x){el.innerHTML='<p class="empty">Choose a company from the list.</p>';return}var inCmp=cmp.indexOf(x.o)>=0;var chips=[];if(x.bk)chips.push('<span class="badge bad">bankrupt</span>');if(x.lq)chips.push('<span class="badge bad">being wound up</span>');chips.push('<span class="badge '+(x.w?'good':'')+'">website: '+esc(x.w?'verified':STATE_LABELS[x.ws]||'not checked')+'</span>');chips.push('<span class="badge '+(x.fin.length?'good':'')+'">accounts: '+(x.fin.length?x.fin.length+' year'+(x.fin.length>1?'s':''):esc(STATE_LABELS[x.fs]||'—'))+'</span>');if(x.ch.length)chips.push('<span class="badge warn">'+x.ch.length+' change(s) since last run</span>');
var facts=[['Organisation number',x.o,null],['Legal form',(x.f||'—')+(x.fd?' · '+x.fd:''),null],['Municipality',x.m||'Not reported',null],['Industry',(x.ic||'')+' '+(x.il||'Not reported')+(x.nd?' — '+x.nd:''),null],['Founded',x.fo||'Not reported',null],['Employees (register)',x.e==null?'Not reported':NF.format(x.e),null]];
var regSrc=x.rS;if(x.acc&&x.acc.c)facts.push(['Annual accounts filed',(x.acc.y?'latest year '+x.acc.y+' · ':'')+x.acc.c.replace(/_/g,' '),null]);
var people=x.ro.length?'<div class="tablewrap"><table><tr><th>Name</th><th>Role</th><th>Updated</th></tr>'+x.ro.map(function(r){return '<tr><td>'+esc(r.n||'—')+'</td><td>'+esc(r.r||'—')+'</td><td>'+esc(r.d||'—')+'</td></tr>'}).join('')+'</table></div>'+(x.roN>x.ro.length?'<p class="ev">Showing '+x.ro.length+' of '+x.roN+' active role records.</p>':'')+'<p class="ev">From the Enhetsregisteret roles record.'+srcLink(x,x.roS,'roles')+'</p>':'<p class="empty">No active role holders are registered.</p>';
var locs=x.lo.length?'<div class="tablewrap"><table><tr><th>Sub-unit</th><th>Municipality</th><th class="num">Employees</th></tr>'+x.lo.map(function(l){return '<tr><td>'+esc(l.n||'—')+' <span class="muted">'+esc(l.o||'')+'</span></td><td>'+esc(l.k||'—')+'</td><td class="num">'+(l.e==null?'—':NF.format(l.e))+'</td></tr>'}).join('')+'</table></div>'+(x.loN>x.lo.length?'<p class="ev">Showing '+x.lo.length+' of '+x.loN+' sub-units.</p>':'')+'<p class="ev">From Enhetsregisteret sub-unit records.'+srcLink(x,x.loS,'sub-units')+'</p>':'<p class="empty">No registered sub-units. That alone does not prove there is no other physical presence.</p>';
var web=x.w?'<p><strong>Website:</strong> <a href="'+esc(x.w)+'" target="_blank" rel="noopener noreferrer">'+esc(x.w)+'</a> <span class="badge good">verified as this legal entity</span>'+srcLink(x,x.wS,'proof')+'</p>'+(x.d?'<p><strong>Self-description:</strong> “'+esc(x.d)+'”'+srcLink(x,x.dS)+'</p>':''):'<p class="empty">'+(x.ws==='ambiguous'?'A candidate website was found but could not be confirmed as this exact legal entity, so nothing from it is shown.':x.ws==='blocked'||x.ws==='failed'?'The website could not be read in this run ('+esc(x.ws)+').':'No official website is registered or could be verified.')+'</p>';
var soc=x.so.length?'<div class="tablewrap"><table><tr><th>Platform</th><th>Profile</th></tr>'+x.so.map(function(s){return '<tr><td>'+esc(s.p)+'</td><td><a href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer">'+esc(s.u)+'</a>'+(s.e[0]?srcLink(x,s.e[0][0],'linked from'):'')+'</td></tr>'}).join('')+'</table></div>':(x.w?'<p class="empty">The verified website links to no social profiles.</p>':'');
var hire=x.hi.length?'<div class="tablewrap"><table><tr><th>Signal</th><th>Details</th><th>Date</th></tr>'+x.hi.map(function(h){return '<tr><td>'+(h.k==='careers_page'?'Careers page':'Job posting')+'</td><td><a href="'+esc(h.u)+'" target="_blank" rel="noopener noreferrer">'+esc(h.t||h.u)+'</a>'+(h.k==='careers_page'&&h.o===false?' <span class="badge">no openings stated</span>':'')+(h.pl==='arbeidsplassen.nav.no'?' <span class="badge">NAV</span>':'')+'</td><td>'+esc(h.d||'—')+'</td></tr>'}).join('')+'</table></div>':'<p class="empty">No careers page or job posting was found on the checked pages or in NAV\'s vacancy register. That does not show the company is not hiring.</p>';
var news=x.nw.length?'<div class="tablewrap"><table><tr><th>Date</th><th>Item</th></tr>'+x.nw.map(function(n){return '<tr><td style="white-space:nowrap">'+esc(n.d)+'</td><td><a href="'+esc(n.u)+'" target="_blank" rel="noopener noreferrer">'+esc(n.t)+'</a></td></tr>'}).join('')+'</table></div><p class="ev">Dated items published on the company\'s verified website, newest first.</p>':'<p class="empty">'+(x.w?'No dated news was found on the checked pages of its website.':'No verified website, so no company news could be read.')+'</p>';
var tl=(x.ev||[]).length?'<ul class="timeline">'+x.ev.map(function(e){var recent=e[0]>=SINCE&&e[0]<=RUN_DAY&&e[1]!=='accounts'&&e[1]!=='founded';return '<li class="'+(recent?'recent':'')+'"><time>'+esc(e[0])+'</time>'+(e[3]?'<a href="'+esc(e[3])+'" target="_blank" rel="noopener noreferrer">'+esc(e[2])+'</a>':esc(e[2]))+(recent?' <span class="badge warn">last 90 days</span>':'')+'</li>'}).join('')+'</ul>':'';var changes=tl+(x.rf&&x.rf.p?'<p>Compared with the previous run'+(x.rf.w?' ('+esc(x.rf.w)+')':'')+': '+(x.ch.length?x.ch.length+' material change(s).':'no material change.')+'</p>':'<p class="muted">First snapshot of this company: there is no earlier run to compare with. Year-on-year movements are under Financials and in the summary.</p>')+(x.ch.length?'<div class="tablewrap"><table><tr><th>Field</th><th>Change</th><th>Before</th><th>After</th><th>Source</th></tr>'+x.ch.map(function(c){return '<tr><td>'+esc(FIELD_LABELS[c.f]||c.f)+'</td><td>'+esc(c.t)+'</td><td>'+esc(c.o==null?'—':c.o)+'</td><td>'+esc(c.nv==null?'—':c.nv)+'</td><td>'+(c.u?'<a href="'+esc(c.u)+'" target="_blank" rel="noopener noreferrer">source ↗</a>':'—')+'</td></tr>'}).join('')+'</table></div>':'')+(x.fn.length?'<p><strong>Former names:</strong> '+x.fn.map(function(f){return esc(f.n)+(f.u?' (until '+esc(f.u)+')':'')}).join('; ')+srcLink(x,x.fnS,'register')+'</p>':'');
var claims='<details><summary>Show all '+x.cl.length+' published claims with their evidence</summary><div class="tablewrap" style="margin-top:8px"><table><tr><th>Claim</th><th>Value</th><th>State</th><th>Evidence (quoted span · source · fetched · SHA-256)</th></tr>'+x.cl.map(function(r){var c={f:r[0],v:r[1],a:r[2],e:r[3],p:r[4]};return '<tr><td data-l="Claim">'+esc(FIELD_LABELS[c.f]||c.f)+(c.p?'<br><small class="muted">'+esc(c.p)+'</small>':'')+'</td><td data-l="Value">'+esc(c.v==null?'—':typeof c.v==='number'?nok(c.v):c.v)+'</td><td data-l="State"><span class="badge '+(c.a==='available'?'good':c.a==='failed'||c.a==='blocked'?'bad':'')+'">'+esc(STATE_LABELS[c.a]||c.a)+'</span></td><td data-l="Evidence">'+(c.a!=='available'&&c.e&&c.e.length?'<small class="muted">The record or page that was checked:</small>':'')+(evList(x,c.e)||'<span class="muted">—</span>')+'</td></tr>'}).join('')+'</table></div></details>';
el.innerHTML='<button type="button" class="btn back" id="back">← All companies</button><div class="head"><div><h2>'+esc(x.n)+'</h2><div class="sub">'+esc(x.o)+' · '+esc(x.f||'')+(x.fd?' ('+esc(x.fd)+')':'')+' · '+esc(x.m||'municipality not reported')+'</div><div class="chips">'+chips.join('')+'</div></div><div class="actions"><button type="button" class="btn'+(inCmp?' primary':'')+'" id="add-cmp">'+(inCmp?'In compare ✓':'Add to compare')+'</button><button type="button" class="btn" id="copy-link">Copy link</button><button type="button" class="btn" id="dl-json">Download JSON</button>'+(x.rd?'<a class="btn" href="'+esc(x.rd)+'" target="_blank" rel="noopener noreferrer">Register page ↗</a>':'')+'</div></div>'+briefHtml(x)+
'<nav class="jump" aria-label="Sections"><a href="#s-summary">Summary</a><a href="#s-fin">Financials</a><a href="#s-people">Leadership</a><a href="#s-loc">Locations</a><a href="#s-web">Web &amp; social</a><a href="#s-hire">Hiring</a><a href="#s-news">News</a><a href="#s-changes">Changes</a><a href="#s-ev">Evidence</a></nav>'+
'<section id="s-summary" class="summary"><h3>Summary</h3>'+sumHtml(x)+'</section>'+
'<section><h3>Key facts</h3><div class="facts">'+facts.map(function(f){return '<div class="fact"><span>'+esc(f[0])+'</span><strong>'+esc(f[1])+'</strong></div>'}).join('')+'</div>'+(x.act?'<p><strong>Registered activity:</strong> “'+esc(x.act)+'”'+srcLink(x,x.aS,'register')+'</p>':'')+(x.acc&&x.acc.r?'<p class="ev">Accounting obligation: '+esc(x.acc.r)+srcLink(x,x.acc.s,'rule')+'</p>':'')+'<p class="ev">From the Enhetsregisteret entity record.'+srcLink(x,regSrc,'register')+'</p></section>'+
'<section id="s-fin"><h3>Financials</h3>'+finHtml(x)+'</section>'+
'<section id="s-people"><h3>Leadership</h3>'+people+'</section>'+
'<section id="s-loc"><h3>Locations</h3>'+locs+'</section>'+
'<section id="s-web"><h3>Web and social profiles</h3>'+web+soc+'</section>'+
'<section id="s-hire"><h3>Hiring</h3>'+hire+'</section>'+
'<section id="s-news"><h3>Dated public activity</h3>'+news+'</section>'+
'<section id="s-changes"><h3>What changed</h3>'+changes+'</section>'+
'<section id="s-ask"><h3>Ask about this company</h3><div class="chips" id="ask-quick">'+['Is it hiring?','Who leads it?','How did revenue change?','Where does it operate?','Latest news?','Website and social profiles?'].map(function(q){return '<button type="button" class="btn" data-q="'+esc(q)+'">'+esc(q)+'</button>'}).join('')+'</div><form class="ask" id="ask-form"><input id="ask-q" placeholder="Or type a question" aria-label="Question about this company"><button class="btn primary" type="submit">Ask</button></form><div id="ask-out"></div></section>'+
'<section id="s-ev"><h3>Evidence</h3><p class="ev">Every published claim with its state and the exact text it was quoted from. Open a source to check the quoted span on the live page; register sources are machine-readable JSON, and the same facts are on the <a href="'+esc(x.rd||'#')+'" target="_blank" rel="noopener noreferrer">readable register page ↗</a>. <label><input type="checkbox" id="show-hash"> show content hashes (SHA-256)</label></p>'+claims+'</section>';
$('#show-hash').onchange=function(e){$('#s-ev').classList.toggle('showhash',e.target.checked)};$('#add-cmp').onclick=function(){toggleCmp(x.o,cmp.indexOf(x.o)<0);profile();list()};$('#copy-link').onclick=function(){copy(location.href.split('#')[0]+'#org='+x.o)};$('#dl-json').onclick=function(){download(x.o+'.json',JSON.stringify(strip(x),null,2),'application/json')};$('#back').onclick=function(){document.body.classList.remove('detail');try{history.replaceState(null,'',location.pathname+location.search)}catch(e){}list()};$('#ask-form').onsubmit=function(e){e.preventDefault();ask(x,$('#ask-q').value)};Array.prototype.forEach.call(document.querySelectorAll('#ask-quick [data-q]'),function(b){b.onclick=function(){$('#ask-q').value=b.dataset.q;ask(x,b.dataset.q)}})}
function strip(x){var o={};Object.keys(x).forEach(function(k){if(k[0]!=='_')o[k]=x[k]});return o}
function ask(x,q){var t=norm(q),out=[];var cite=function(i){return srcLink(x,i)};if(/hir|job|career|vacan|stilling|recruit|ansett/.test(t))out.push(['Hiring',x.hi.length?x.hi.slice(0,4).map(function(h){return (h.k==='careers_page'?'Careers page ':'Posting ')+'<a href="'+esc(h.u)+'" target="_blank" rel="noopener noreferrer">'+esc(h.t||h.u)+'</a>'+(h.d?' ('+esc(h.d)+')':'')}).join('<br>'):'No careers page or job posting was found on the checked pages or in NAV\'s vacancy register; that does not show it is not hiring.']);if(/lead|ceo|chair|board|director|owner|who|leder|styre/.test(t))out.push(['Leadership',x.ro.length?x.ro.slice(0,6).map(function(r){return esc(r.r)+': <strong>'+esc(r.n)+'</strong>'}).join('<br>')+cite(x.roS):'No active role holders are registered.']);if(/revenue|profit|result|financ|account|money|growth|debt|asset|turnover|omsetning|regnskap|change|grow/.test(t))out.push(['Financials',x.fin.length?x.fin.map(function(y){return esc((y.to||'').slice(0,4))+': revenue NOK '+nok(y.revenue)+', annual result NOK '+nok(y.annual_result)}).join('<br>')+cite(x.fin[0].s):'No annual accounts were returned; missing figures are not zero.']);if(/where|location|office|address|branch|sted|kontor|municipal/.test(t))out.push(['Locations',(x.m?'Registered in '+esc(x.m)+'. ':'')+(x.lo.length?x.loN+' registered sub-unit(s): '+x.lo.slice(0,6).map(function(l){return esc(l.n)+' ('+esc(l.k||'—')+')'}).join(', ')+cite(x.loS):'No registered sub-units.')]);if(/news|activity|recent|latest|press|nyhet|update/.test(t))out.push(['Dated activity',x.nw.length?x.nw.slice(0,4).map(function(n){return esc(n.d)+' — <a href="'+esc(n.u)+'" target="_blank" rel="noopener noreferrer">'+esc(n.t)+'</a>'}).join('<br>'):'No dated news was found on its verified website.']);if(/social|linkedin|facebook|instagram|youtube|website|site|web/.test(t))out.push(['Web and social',(x.w?'Verified website <a href="'+esc(x.w)+'" target="_blank" rel="noopener noreferrer">'+esc(x.w)+'</a>'+cite(x.wS):'No verified website.')+(x.so.length?'<br>'+x.so.map(function(s){return esc(s.p)+': <a href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer">'+esc(s.u)+'</a>'}).join('<br>'):'')]);if(/sentiment|reputation|review|opinion|omtale/.test(t))out.push(['Reputation','Not assessed: Signalpost does not read review sites, the press or LinkedIn.']);if(!out.length){var s=(x.sm.s||[])[0];out.push(['Overview',s?esc(s.t.replace(/\s\[\d+(?:, \d+)*\]/g,'')):esc(x.n)+' ('+esc(x.o)+')']);out.push(['Tip','Ask about hiring, leadership, financials, locations, news, website or social profiles.'])}$('#ask-out').innerHTML='<div class="answer">'+out.map(function(o){return '<p><strong>'+esc(o[0])+'.</strong> '+o[1]+'</p>'}).join('')+'<p class="ev">Answers are read from this profile\'s published claims; nothing is generated.</p></div>'}
function cmpRows(){var latest=function(x,k){return x.fin.length?x.fin[0][k]:null};return [['Organisation number',function(x){return esc(x.o)}],['Legal form',function(x){return esc((x.f||'—')+(x.fd?' · '+x.fd:''))}],['Municipality',function(x){return esc(x.m||'—')}],['Industry',function(x){return esc((x.ic||'')+' '+(x.il||'—'))}],['Founded',function(x){return esc(x.fo||'—')}],['Employees',function(x){return x.e==null?'—':NF.format(x.e)+srcMini(x,x.eS)}],['Latest accounts',function(x){if(!x.fin.length)return '—';var y=x.fin[0],cal=(y.from||'').slice(5)==='01-01'&&(y.to||'').slice(5)==='12-31';return esc(cal?(y.to||'').slice(0,4):(y.from||'')+' – '+(y.to||''))+(y.c===false?' <small class="muted">(not 12 months)</small>':'')+srcMini(x,y.s)}],['Revenue (NOK)',function(x){return nok(latest(x,'revenue'))+(x.fin.length?srcMini(x,x.fin[0].s):'')+(x.ga&&x.ga.length?' <small class="muted">parent only</small>':'')}],['Revenue, year before (NOK)',function(x){var y=x.fin[1];return y&&y.revenue!=null?nok(y.revenue)+' <small class="muted">'+esc((y.to||'').slice(0,4))+'</small>':'—'}],['Revenue, two years before (NOK)',function(x){var y=x.fin[2];return y&&y.revenue!=null?nok(y.revenue)+' <small class="muted">'+esc((y.to||'').slice(0,4))+'</small>':'—'}],['Revenue change',function(x){var ok=x.fin.length>1&&x.fin[0].c&&x.fin[1].c;return x.g==null||!ok?'—':'<span class="'+(x.g>=0?'up':'down')+'">'+(x.g>=0?'+':'−')+Math.abs(x.g).toFixed(1)+'%</span>'}],['Operating result (NOK)',function(x){return nok(latest(x,'operating_result'))}],['Annual result (NOK)',function(x){return nok(latest(x,'annual_result'))}],['Total assets (NOK)',function(x){return nok(latest(x,'assets'))}],['Debt (NOK)',function(x){return nok(latest(x,'debt'))}],['Equity (assets − debt, NOK)',function(x){var a=latest(x,'assets'),d=latest(x,'debt');return a==null||d==null?'—':'<span class="'+(a-d<0?'down':'')+'">'+nok(a-d)+'</span>'}],['Group (konsern) accounts',function(x){return x.ga&&x.ga.length?'also filed ('+esc(x.ga.join(', '))+')':'—'}],['Chief executive',function(x){var r=x.ro.filter(function(r){return r.c==='DAGL'});return r.length?esc(r.map(function(r){return r.n}).join(', '))+srcLink(x,x.roS):'—'}],['Chair of the board',function(x){var r=x.ro.filter(function(r){return r.c==='LEDE'});return r.length?esc(r.map(function(r){return r.n}).join(', ')):'—'}],['Sub-units',function(x){return NF.format(x.loN)}],['Website',function(x){return x.w?'<a href="'+esc(x.w)+'" target="_blank" rel="noopener noreferrer">'+esc(x.w.replace(/^https?:\/\//,''))+'</a>':esc(STATE_LABELS[x.ws]||'—')}],['Social profiles',function(x){return x.so.length?x.so.map(function(s){return '<a href="'+esc(s.u)+'" target="_blank" rel="noopener noreferrer">'+esc(s.p)+'</a>'}).join(', '):'—'}],['Dated news',function(x){return x._nw.length?x._nw.length+' (latest '+esc(x._nw[0].d)+')':'—'}],['Hiring',function(x){return x.hi.length?x.hi.map(function(h){return '<a href="'+esc(h.u)+'" target="_blank" rel="noopener noreferrer">'+(h.k==='careers_page'?'careers page':'posting')+'</a>'}).join(', '):'none found'}],['Register status',function(x){return x.bk?'bankrupt':x.lq?'being wound up':'active'}],['Changes in the last 90 days',function(x){return x._recent.length?x._recent.slice(0,3).map(function(e){return esc(e[0])+' '+esc(String(e[2]).slice(0,60))}).join('<br>'):'none recorded'}]]}
function renderCmp(){var xs=cmp.map(function(o){return byOrg[o]}).filter(Boolean);if(!xs.length){$('#cmp-body').innerHTML='<p class="empty" style="padding:12px">Nothing to compare yet. Tick companies in the list.</p>';return}var BEST={'Revenue (NOK)':function(x){return x.fin.length?x.fin[0].revenue:null},'Annual result (NOK)':function(x){return x.fin.length?x.fin[0].annual_result:null},'Employees':function(x){return x.e},'Revenue change':function(x){return x.g}};var best=function(r,x){var f=BEST[r[0]];if(!f||xs.length<2)return false;var vals=xs.map(f).filter(function(v){return v!=null});return vals.length>1&&f(x)===Math.max.apply(null,vals)};var rows=cmpRows();$('#cmp-body').innerHTML='<div class="cmp-table"><table class="cmp"><tr><th>Company</th>'+xs.map(function(x){return '<th><a href="#org='+x.o+'" data-goto="'+x.o+'">'+esc(x.n)+'</a><br><button type="button" class="btn" data-rm="'+x.o+'" style="margin-top:4px;font-size:12px">Remove</button></th>'}).join('')+'</tr>'+rows.map(function(r){return '<tr><th>'+r[0]+'</th>'+xs.map(function(x){return '<td class="'+(/NOK|change/.test(r[0])?'num ':'')+(best(r,x)?'best':'')+'">'+r[1](x)+(best(r,x)?' ▲':'')+'</td>'}).join('')+'</tr>'}).join('')+'</table></div><div class="cmp-cards">'+xs.map(function(x){return '<p style="margin:4px 0"><a href="#org='+x.o+'" data-goto="'+x.o+'"><strong>'+esc(x.n)+'</strong></a> <button type="button" class="btn" data-rm="'+x.o+'" style="font-size:12px;padding:2px 8px">Remove</button></p>'}).join('')+rows.map(function(r){return '<div class="cmp-card"><h4>'+r[0]+'</h4>'+xs.map(function(x){return '<div><span>'+esc(x.n)+'</span><span class="'+(best(r,x)?'best':'')+'">'+r[1](x)+(best(r,x)?' ▲':'')+'</span></div>'}).join('')+'</div>'}).join('')+'</div>';Array.prototype.forEach.call(document.querySelectorAll('[data-rm]'),function(b){b.onclick=function(){toggleCmp(b.dataset.rm,false);renderCmp();list()}});Array.prototype.forEach.call(document.querySelectorAll('[data-goto]'),function(a){a.onclick=function(e){e.preventDefault();closeOverlay('#compare');open(a.dataset.goto,true)}})}
function openOverlay(id){$(id).classList.add('open');var b=$(id).querySelector('button.primary');if(b)b.focus()}
function closeOverlay(id){$(id).classList.remove('open')}
function copy(text){var done=function(){alert('Link copied:\n'+text)};try{navigator.clipboard.writeText(text).then(done,function(){prompt('Copy this link:',text)})}catch(e){prompt('Copy this link:',text)}}
function download(name,body,type){var blob=new Blob([body],{type:type}),u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u)},1000)}
function csvCell(v){v=String(v==null?'':v).replace(/<[^>]+>/g,'').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/ ↗/g,'');return /[",\n;]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v}
$('#compare-open').onclick=function(){renderCmp();openOverlay('#compare')};$('#cmp-close').onclick=function(){closeOverlay('#compare')};$('#cmp-clear').onclick=function(){cmp=[];store.set('signalpost-compare',cmp);renderCmp();list();if(selected)profile()};
$('#cmp-link').onclick=function(){copy(location.href.split('#')[0]+'#compare='+cmp.join(','))};
$('#cmp-csv').onclick=function(){var xs=cmp.map(function(o){return byOrg[o]}).filter(Boolean),rows=[['Field'].concat(xs.map(function(x){return x.n}))].concat(cmpRows().map(function(r){return [r[0]].concat(xs.map(function(x){return r[1](x)}))}));download('signalpost-compare.csv',rows.map(function(r){return r.map(csvCell).join(',')}).join('\n'),'text/csv')};
$('#export').onclick=function(){var rows=filtered();download('signalpost-companies.json',JSON.stringify({exported_at:new Date().toISOString(),run:RUN,filters:{query:$('#q').value,legal_form:$('#f-form').value,has:$('#f-has').value,status:$('#f-status').value,sort:$('#sort').value},companies:rows.map(strip)},null,1),'application/json')};
$('#about-open').onclick=function(){openOverlay('#about')};$('#about-close').onclick=function(){closeOverlay('#about')};
document.addEventListener('keydown',function(e){if(e.key==='Escape'){closeOverlay('#compare');closeOverlay('#about')}if(e.key==='/'&&document.activeElement.tagName!=='INPUT'){e.preventDefault();$('#q').focus()}});
['#compare','#about'].forEach(function(id){$(id).addEventListener('click',function(e){if(e.target===$(id))closeOverlay(id)})});
var inds={},munis={};DATA.forEach(function(x){var d=String(x.ic||'').slice(0,2);if(d&&d!=='00')inds[d]=x.nd||('NACE '+d);if(x.m)munis[x.m]=(munis[x.m]||0)+1});$('#f-ind').innerHTML+=Object.keys(inds).sort().map(function(d){return '<option value="'+esc(d)+'">'+esc(inds[d])+'</option>'}).join('');$('#f-muni').innerHTML+=Object.keys(munis).sort(function(a,b){return a.localeCompare(b,'nb')}).map(function(m){return '<option value="'+esc(m)+'">'+esc(m)+' ('+munis[m]+')</option>'}).join('');if(!DATA.some(function(x){return x.ch.length})){var oc=document.querySelector('#f-has option[value="change"]');if(oc)oc.remove()}var forms={};DATA.forEach(function(x){if(x.f)forms[x.f]=(forms[x.f]||0)+1});$('#f-form').innerHTML+=Object.keys(forms).sort().map(function(f){return '<option value="'+esc(f)+'">'+esc(f)+' ('+forms[f]+')</option>'}).join('');
var timer=null;$('#q').addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(function(){shown=200;list()},120)});['#f-form','#f-ind','#f-muni','#f-status','#sort'].forEach(function(id){$(id).onchange=function(){shown=200;list()}});$('#fab-compare').onclick=function(){renderCmp();openOverlay('#compare')};$('#f-has').onchange=function(){tile=$('#f-has').value||null;shown=200;stats();list()};
function route(){var h=location.hash.slice(1),m;if((m=/^org=(\d{9})$/.exec(h))&&byOrg[m[1]]){open(m[1],true);return true}if((m=/^compare=([\d,]+)$/.exec(h))){cmp=m[1].split(',').filter(function(o){return byOrg[o]}).slice(0,4);store.set('signalpost-compare',cmp);list();renderCmp();openOverlay('#compare');return true}return false}
runline();stats();savedBar();if(!route())list();window.addEventListener('hashchange',route);
})();
</script>
</body>
</html>
"""
