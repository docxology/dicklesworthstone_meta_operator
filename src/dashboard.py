"""Static, self-contained interpretation surfaces for the meta-operator.

Reads the frozen JSON artifacts (registry, upstream status, inventory, runs)
and renders two deterministic artifacts: a single-file dark-theme HTML
dashboard (inline CSS + vanilla JS, zero external fetches) and a markdown
corpus catalog. All orderings are sorted before render so output is
byte-identical for identical inputs.
"""

from __future__ import annotations

import html as _html
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src import jsonio, project_paths
from src.models import UPSTREAM_OK_STATES, UPSTREAM_STATES

logger = logging.getLogger(__name__)

# state -> chip severity class (ok green / warn amber shades / bad red shades)
_CHIP_SEVERITY: dict[str, str] = {
    "on_upstream": "ok",
    "unborn": "ok",
    "behind": "warn",
    "ahead": "warn",
    "dirty": "warn",
    "diverged": "bad",
    "detached": "bad",
    "off_default": "bad",
    "missing": "bad",
}


def _iso_now() -> str:
    """Current UTC time as an ISO-8601 Z timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _esc(text: object) -> str:
    """HTML-escape arbitrary text for safe interpolation."""
    return _html.escape(str(text), quote=True)


def _read_required_json(path: Path, *, missing_msg: str) -> dict:
    """Read a required artifact; translate any absence into RuntimeError."""
    try:
        raw = jsonio.read_json(path, required=True)
    except (KeyError, FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
        raise RuntimeError(missing_msg) from exc
    if not isinstance(raw, dict):
        raise RuntimeError(missing_msg)
    return raw


def _read_optional_json(path: Path) -> dict | None:
    """Read an optional artifact; absent OR corrupt -> None (logged, never raised).

    Corruption is a data-integrity concern for the health gate, not a reason
    for the presentation layer to crash.
    """
    try:
        raw = jsonio.read_json(path, required=False)
    except json.JSONDecodeError as exc:
        logger.warning("corrupt optional artifact skipped: %s (%s)", path, exc)
        return None
    return raw if isinstance(raw, dict) else None


def load_payload(project_root: Path, *, run_id: str | None = None) -> dict:
    """Load every artifact the dashboard needs into one payload dict.

    Registry is required (RuntimeError with a fix hint when missing);
    upstream status, inventory, and the selected run are optional (None).
    """
    root = Path(project_root)
    ddir = project_paths.data_dir(root)
    registry = _read_required_json(
        ddir / project_paths.REPO_REGISTRY,
        missing_msg="registry missing — run scripts/10_build_registry.py",
    )
    upstream = _read_optional_json(ddir / project_paths.UPSTREAM_STATUS)
    inventory = _read_optional_json(ddir / project_paths.INVENTORY)
    return {
        "generated_at": _iso_now(),
        "github_user": registry.get("github_user", ""),
        "include_forks": bool(registry.get("include_forks", True)),
        "repos": list(registry.get("repos", []) or []),
        "upstream": upstream,
        "inventory": inventory,
        "run": _load_run(project_paths.runs_dir(root), run_id),
        "runs_history": _load_run_history(project_paths.runs_dir(root)),
    }


def _load_run(runs_root: Path, run_id: str | None) -> dict | None:
    """Resolve the requested run (or lexicographically-last) to its results."""
    if not runs_root.is_dir():
        return None
    if run_id is None:
        candidates = sorted(
            (
                d
                for d in runs_root.iterdir()
                if d.is_dir() and (d / "results.json").is_file()
            ),
            key=lambda d: d.name,
        )
        if not candidates:
            return None
        target = candidates[-1]
    else:
        target = runs_root / run_id
        if not (target / "results.json").is_file():
            raise RuntimeError(
                f"run {run_id!r} not found under {runs_root} "
                "(omit the run id to use the latest run)"
            )
    return _read_optional_json(target / "results.json")


_RUN_HISTORY_KEEP = 5


def _load_run_history(runs_root: Path) -> dict[str, list[dict]]:
    """Per-repo history over the most recent runs (bounded, deterministic).

    Returns ``{repo_name: [{run_id, command, exit_code, timed_out, skipped},
    ...]}`` oldest-first, over the lexicographically-last ``keep`` run
    directories. Corrupt entries are skipped, never surfaced as crashes.
    """
    if not runs_root.is_dir():
        return {}
    candidates = sorted(
        (
            d
            for d in runs_root.iterdir()
            if d.is_dir() and (d / "results.json").is_file()
        ),
        key=lambda d: d.name,
    )
    history: dict[str, list[dict]] = {}
    for target in candidates[-_RUN_HISTORY_KEEP:]:
        raw = _read_optional_json(target / "results.json")
        if not isinstance(raw, dict):
            continue
        run_id = str(raw.get("run_id") or target.name)
        command = str(raw.get("command") or "")
        for entry in raw.get("repos", []) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "")
            if not name:
                continue
            history.setdefault(name, []).append(
                {
                    "run_id": run_id,
                    "command": command,
                    "exit_code": entry.get("exit_code"),
                    "timed_out": bool(entry.get("timed_out")),
                    "skipped": bool(entry.get("skipped")),
                }
            )
    return dict(sorted(history.items()))


def compute_summary(payload: dict) -> dict:
    """Pure aggregate of the payload — no IO, deterministic orderings.

    Languages and upstream states are sorted descending by count, then name;
    ``top_by_loc`` is the ten highest-LOC inventory entries.
    """
    repos = list(payload.get("repos", []) or [])
    upstream = payload.get("upstream") if isinstance(payload.get("upstream"), dict) else None
    inventory = (
        payload.get("inventory") if isinstance(payload.get("inventory"), dict) else None
    )

    languages: dict[str, int] = {}
    total_size_kb = 0
    for r in repos:
        lang = str(r.get("language") or "").strip()
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
        total_size_kb += int(r.get("size_kb") or 0)
    languages = dict(sorted(languages.items(), key=lambda kv: (-kv[1], kv[0])))

    upstream_repos: list[dict] = list((upstream or {}).get("repos", []) or [])
    states: dict[str, int] = {}
    upstream_ok = 0
    for u in upstream_repos:
        state = str(u.get("state") or "missing")
        states[state] = states.get(state, 0) + 1
        if state in UPSTREAM_OK_STATES:
            upstream_ok += 1
    states = dict(sorted(states.items(), key=lambda kv: (-kv[1], kv[0])))

    inv_repos: list[dict] = list((inventory or {}).get("repos", []) or [])
    total_loc = sum(int(r.get("total_loc") or 0) for r in inv_repos)


    top = sorted(
        inv_repos,
        key=lambda r: (-(int(r.get("total_loc") or 0)), str(r.get("name") or "")),
    )
    top_by_loc = [
        {"name": str(r.get("name") or ""), "total_loc": int(r.get("total_loc") or 0)}
        for r in top[:10]
    ]

    return {
        "total": len(repos),
        "forks": sum(1 for r in repos if r.get("fork")),
        "languages": languages,
        "upstream_states": states,
        "upstream_ok": upstream_ok,
        "upstream_not_ok": len(upstream_repos) - upstream_ok,
        "total_loc": total_loc,
        "total_size_kb": total_size_kb,
        "stale_days_max": _max_stale_days(inv_repos, datetime.now(timezone.utc)),
        "top_by_loc": top_by_loc,
    }


def _max_stale_days(inv_repos: list[dict], now: datetime) -> int | None:
    """Largest whole-day age across inventory ``last_commit_date`` values."""
    max_days: int | None = None
    for r in inv_repos:
        raw_date = str(r.get("last_commit_date") or "").strip()
        if not raw_date:
            continue
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = max((now - dt).days, 0)
        max_days = days if max_days is None else max(max_days, days)
    return max_days


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CSS = """
:root{--bg:#0d1117;--panel:#161b22;--border:#30363d;--fg:#c9d1d9;--muted:#8b949e;
--ok:#3fb950;--warn:#d29922;--bad:#f85149;--accent:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-size:14px;line-height:1.45;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--border)}
h1{margin:0;font-size:20px}
.meta{color:var(--muted);font-size:12px;margin-top:4px}
.cards{display:flex;flex-wrap:wrap;gap:12px;padding:16px 24px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;
padding:12px 16px;min-width:130px}
.card .num{font-size:22px;font-weight:600}
.card .lbl{color:var(--muted);font-size:11px;text-transform:uppercase;
letter-spacing:.05em;margin-top:2px}
.controls{display:flex;flex-wrap:wrap;gap:10px;padding:0 24px 12px}
.controls input,.controls select{background:var(--panel);color:var(--fg);
border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:13px}
.legend{padding:0 24px 12px;color:var(--muted);font-size:12px}
.legend .chip{margin:0 6px 4px 0}
.empty-panel{margin:0 24px 16px;padding:14px;border:1px dashed var(--warn);
border-radius:8px;color:var(--warn);background:rgba(210,153,34,.06)}
table{width:calc(100% - 48px);margin:0 24px 24px;border-collapse:collapse;
background:var(--panel);border:1px solid var(--border);border-radius:8px}
th,td{border-bottom:1px solid var(--border);padding:8px 10px;text-align:left}
th{color:var(--muted);font-size:12px;white-space:nowrap}
th.sortable{cursor:pointer;user-select:none}
th.sortable:hover{color:var(--accent)}
tr.repo{cursor:pointer}
tr.repo:hover{background:#1c2129}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.chip{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;
font-weight:600;border:1px solid;white-space:nowrap}
.chip-ok{color:var(--ok);border-color:var(--ok);background:rgba(63,185,80,.12)}
.chip-warn{color:var(--warn);border-color:var(--warn);background:rgba(210,153,34,.12)}
.chip-bad{color:var(--bad);border-color:var(--bad);background:rgba(248,81,73,.12)}
.exit-ok{color:var(--ok)}.exit-fail{color:var(--bad)}
.exit-timeout{color:var(--warn)}.exit-skip{color:var(--muted)}
.forkbadge{color:var(--accent);border:1px solid var(--accent);border-radius:4px;
padding:0 5px;font-size:11px}
.muted{color:var(--muted)}
code{background:var(--bg);border:1px solid var(--border);border-radius:4px;
padding:1px 6px;font-size:12px}
.chips code{display:inline-block;margin:2px 6px 2px 0}
details{margin:2px 0}
summary{cursor:pointer;color:var(--muted);font-size:12px}
pre{background:var(--bg);border:1px solid var(--border);border-radius:4px;
padding:8px;white-space:pre-wrap;word-break:break-word;font-size:12px;
max-width:420px;max-height:220px;overflow:auto;margin:4px 0}
#drawer{position:fixed;top:0;right:-460px;width:440px;height:100%;
background:var(--panel);border-left:1px solid var(--border);overflow-y:auto;
padding:20px;transition:right .15s;z-index:10}
#drawer.open{right:0}
#drawer h2{margin:0 0 12px}
#drawerClose{float:right;background:none;border:1px solid var(--border);
color:var(--fg);border-radius:6px;padding:4px 10px;cursor:pointer}
.kv{margin:10px 0}
.kv b{color:var(--muted);display:block;font-size:11px;text-transform:uppercase;
letter-spacing:.05em;margin-bottom:3px}
section.runs{padding:0 24px}
section.runs h2{font-size:16px}
"""

_JS = """
(function(){
  var rows=[].slice.call(document.querySelectorAll("tr.repo"));
  var filter=document.getElementById("filter");
  var langSel=document.getElementById("langSel");
  var stateSel=document.getElementById("stateSel");
  var drawer=document.getElementById("drawer");
  var DATA=window.__REPO_DATA__||{};
  var HIST=window.__RUN_HISTORY__||{};
  function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML;}
  function apply(){
    var q=(filter.value||"").toLowerCase();
    var lang=langSel.value,state=stateSel.value;
    rows.forEach(function(tr){
      var ok=(!q||tr.getAttribute("data-search").indexOf(q)>=0)
        &&(lang==="all"||tr.getAttribute("data-lang")===lang)
        &&(state==="all"||tr.getAttribute("data-state")===state);
      tr.style.display=ok?"":"none";
    });
  }
  filter.addEventListener("input",apply);
  langSel.addEventListener("change",apply);
  stateSel.addEventListener("change",apply);
  document.getElementById("drawerClose").addEventListener("click",function(){
    drawer.classList.remove("open");
  });
  rows.forEach(function(tr){
    tr.addEventListener("click",function(){
      var d=DATA[tr.getAttribute("data-name")]||{};
      var g=function(id){return document.getElementById(id);};
      g("dTitle").textContent=tr.getAttribute("data-name");
      g("dSummary").textContent=d.readme_summary||"\\u2014";
      g("dEntries").innerHTML=(d.entry_points||[]).map(function(e){
        return "<code>"+esc(String(e))+"</code>";}).join(" ")||"\\u2014";
      var cmds=d.auto_cmds||{};
      g("dCmds").innerHTML=Object.keys(cmds).sort().map(function(k){
        return "<code>"+esc(k)+": "+esc(String(cmds[k]))+"</code>";}).join(" ")||"\\u2014";
      var man=d.manifests||{};
      g("dManifests").innerHTML=Object.keys(man).sort().map(function(k){
        return "<code>"+esc(k)+"</code>";}).join(" ")||"\\u2014";
      g("dCommit").textContent=d.last_commit_message||"\\u2014";
      var hist=(HIST[tr.getAttribute("data-name")]||[]).slice(-5);
      g("dRuns").innerHTML=hist.map(function(h){
        var status=h.skipped?"skipped":(h.timed_out?"timeout":(h.exit_code===0?"ok":"exit "+h.exit_code));
        return "<code>"+esc(String(h.run_id))+": "+esc(String(h.command))+" = "+esc(status)+"</code>";
      }).join(" ")||"\\u2014";
      drawer.classList.add("open");
    });
  });
  var ths=[].slice.call(document.querySelectorAll("th.sortable"));
  ths.forEach(function(th){
    th.addEventListener("click",function(){
      var key=th.getAttribute("data-key");
      var dir=th.getAttribute("data-dir")==="asc"?"desc":"asc";
      ths.forEach(function(o){o.removeAttribute("data-dir");});
      th.setAttribute("data-dir",dir);
      var sorted=rows.slice().sort(function(a,b){
        var av=a.getAttribute(key)||"",bv=b.getAttribute(key)||"";
        var an=parseFloat(av),bn=parseFloat(bv);
        var cmp=(isNaN(an)||isNaN(bn))?av.localeCompare(bv):(an-bn);
        return dir==="asc"?cmp:-cmp;
      });
      sorted.forEach(function(r){r.parentNode.appendChild(r);});
    });
  });
})();
"""


def _chip(state: str) -> str:
    """Colored state chip; unknown/absent states render as missing (red)."""
    sev = _CHIP_SEVERITY.get(state, "bad")
    return f'<span class="chip chip-{_esc(state)} chip-{sev}">{_esc(state)}</span>'


def _exit_chip(rr: dict) -> str:
    """Exit-code chip for one RunResult dict."""
    if rr.get("skipped"):
        return '<span class="exit-skip">skipped</span>'
    if rr.get("timed_out"):
        return '<span class="chip chip-warn exit-timeout">timeout</span>'
    code = rr.get("exit_code")
    if code == 0:
        return '<span class="chip chip-ok exit-ok">0</span>'
    return f'<span class="chip chip-bad exit-fail">{_esc(code)}</span>'


def render_dashboard(payload: dict, summary: dict) -> str:
    """Render the whole dashboard as ONE self-contained HTML string.

    Deterministic: repos, run results, chips, and the embedded JS data are
    all sorted before interpolation; no clocks, no randomness, no network.
    """
    repos = sorted(payload.get("repos", []) or [], key=lambda r: str(r.get("name") or ""))
    upstream = payload.get("upstream") if isinstance(payload.get("upstream"), dict) else None
    inventory = payload.get("inventory") if isinstance(payload.get("inventory"), dict) else None
    upstream_map = {
        str(u.get("name") or ""): u for u in (upstream or {}).get("repos", []) or []
    }
    inv_map = {str(r.get("name") or ""): r for r in (inventory or {}).get("repos", []) or []}

    # --- summary cards -----------------------------------------------------
    lang_count = len(summary.get("languages", {}) or {})
    stale = summary.get("stale_days_max")
    cards = [
        ("Repos", summary.get("total", 0)),
        ("Forks", summary.get("forks", 0)),
        ("Languages", lang_count),
        ("Upstream ok", summary.get("upstream_ok", 0)),
        ("Upstream not ok", summary.get("upstream_not_ok", 0)),
        ("Total LOC", f"{summary.get('total_loc', 0):,}"),
        ("Total Size KB", f"{summary.get('total_size_kb', 0):,}"),
        ("Max stale days", "—" if stale is None else stale),
    ]
    card_html = "".join(
        f'<div class="card"><div class="num">{_esc(val)}</div>'
        f'<div class="lbl">{_esc(lbl)}</div></div>'
        for val, lbl in cards
    )

    # --- legend + controls -------------------------------------------------
    legend = "".join(_chip(s) for s in sorted(UPSTREAM_STATES))
    lang_options = sorted((summary.get("languages", {}) or {}).keys())
    lang_opts = "".join(f'<option value="{_esc(l)}">{_esc(l)}</option>' for l in lang_options)
    state_opts = "".join(
        f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in sorted(UPSTREAM_STATES)
    )
    controls = (
        '<div class="controls">'
        '<input id="filter" type="text" placeholder="Filter by name or description..." '
        'autocomplete="off">'
        f'<select id="langSel"><option value="all">Language: all</option>{lang_opts}</select>'
        f'<select id="stateSel"><option value="all">Upstream: all</option>{state_opts}</select>'
        "</div>"
        f'<div class="legend">Upstream states: {legend}</div>'
    )

    # --- repo table --------------------------------------------------------
    repo_data: dict[str, dict] = {}
    rows: list[str] = []
    for r in repos:
        name = str(r.get("name") or "")
        u = upstream_map.get(name)
        state = str(u.get("state")) if u else ""
        inv = inv_map.get(name)
        loc = str(int(inv.get("total_loc") or 0)) if inv else ""
        commit_date = str(inv.get("last_commit_date") or "") if inv else ""
        fork = bool(r.get("fork"))
        repo_data[name] = {
            "readme_summary": (inv or {}).get("readme_summary", ""),
            "entry_points": list((inv or {}).get("entry_points", []) or []),
            "auto_cmds": dict(sorted(((inv or {}).get("auto_cmds", {}) or {}).items())),
            "manifests": dict(sorted(((inv or {}).get("manifests", {}) or {}).items())),
            "last_commit_message": (inv or {}).get("last_commit_message", ""),
        }
        search = _esc((name + " " + str(r.get("description") or "")).lower())
        rows.append(
            "<tr class=\"repo\" data-name=\"%s\" data-search=\"%s\" data-lang=\"%s\" "
            "data-state=\"%s\" data-loc=\"%s\" data-size=\"%s\" data-date=\"%s\" "
            "data-fork=\"%d\">"
            '<td><a href="%s">%s</a>%s</td>'
            "<td>%s</td>"
            "<td class=\"num\">%s</td>"
            "<td class=\"num\">%s</td>"
            "<td>%s</td>"
            "<td class=\"muted\">%s</td>"
            "<td>%s</td>"
            "</tr>"
            % (
                _esc(name),
                search,
                _esc(r.get("language") or ""),
                _esc(state),
                loc,
                _esc(r.get("size_kb") or ""),
                _esc(commit_date),
                1 if fork else 0,
                _esc(r.get("html_url") or "#"),
                _esc(name),
                '<span class="forkbadge">fork</span>' if fork else "",
                _esc(r.get("language") or "") or '<span class="muted">—</span>',
                loc or '<span class="muted">—</span>',
                _esc(r.get("size_kb") or "") or '<span class="muted">—</span>',
                _chip(state) if state else '<span class="muted">—</span>',
                commit_date or '<span class="muted">—</span>',
                '<span class="forkbadge">fork</span>' if fork else "",
            )
        )
    repo_data_js = json.dumps(repo_data, sort_keys=True).replace("</", "<\\/")
    run_history_js = json.dumps(
        payload.get("runs_history") or {}, sort_keys=True
    ).replace("</", "<\\/")
    table = (
        "<table id=\"repoTable\">"
        "<thead><tr>"
        '<th class="sortable" data-key="data-name">Name &#9650;&#9660;</th>'
        '<th class="sortable" data-key="data-lang">Language &#9650;&#9660;</th>'
        '<th class="sortable" data-key="data-loc">LOC &#9650;&#9660;</th>'
        '<th class="sortable" data-key="data-size">Size KB &#9650;&#9660;</th>'
        '<th class="sortable" data-key="data-state">Upstream state &#9650;&#9660;</th>'
        '<th class="sortable" data-key="data-date">Last commit &#9650;&#9660;</th>'
        '<th class="sortable" data-key="data-fork">Fork &#9650;&#9660;</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    # --- optional-artifact panels -----------------------------------------
    panels = ""
    if upstream is None:
        panels += (
            '<div class="empty-panel">Upstream verification not built yet — '
            "run the upstream verification step to populate this column.</div>"
        )
    if inventory is None:
        panels += (
            '<div class="empty-panel">Inventory not built yet — run the inventory '
            "step to populate LOC, languages, and repo details.</div>"
        )

    # --- runs section ------------------------------------------------------
    run = payload.get("run") if isinstance(payload.get("run"), dict) else None
    runs_html = ""
    if run is not None:
        meta = (
            f'<p class="meta">run <b>{_esc(run.get("run_id") or "")}</b> · '
            f"command <code>{_esc(run.get('command') or '')}</code> · "
            f"selector <code>{_esc(run.get('selector') or '')}</code> · "
            f"generated_at {_esc(run.get('generated_at') or '')}</p>"
        )
        run_rows: list[str] = []
        for rr in sorted(run.get("repos", []) or [], key=lambda x: str(x.get("name") or "")):
            tail = str(rr.get("stderr_tail") or "")
            run_rows.append(
                "<tr><td>%s</td><td><code>%s</code></td><td>%s</td>"
                "<td class=\"num\">%s</td><td>%s</td></tr>"
                % (
                    _esc(rr.get("name") or ""),
                    _esc(rr.get("command") or ""),
                    _exit_chip(rr),
                    _esc(rr.get("seconds") or ""),
                    (
                        "<details><summary>stderr</summary><pre>%s</pre></details>"
                        % _esc(tail)
                        if tail
                        else '<span class="muted">—</span>'
                    ),
                )
            )
        runs_html = (
            '<section class="runs"><h2>Runs</h2>' + meta
            + "<table><thead><tr><th>Repo</th><th>Command</th><th>Exit</th>"
            "<th>Seconds</th><th>stderr tail</th></tr></thead><tbody>"
            + "".join(run_rows)
            + "</tbody></table></section>"
        )

    meta_line = (
        f"github user <b>{_esc(payload.get('github_user') or '')}</b> · "
        f"include_forks <b>{_esc('yes' if payload.get('include_forks') else 'no')}</b> · "
        f"generated_at {_esc(payload.get('generated_at') or '')}"
    )
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Meta-Operator Corpus Dashboard</title>"
        f"<style>{_CSS}</style></head><body>"
        "<header><h1>Meta-Operator Corpus Dashboard</h1>"
        f'<div class="meta">{meta_line}</div></header>'
        '<div class="cards">' + card_html + "</div>"
        + controls
        + panels
        + table
        + runs_html
        + '<aside id="drawer"><button id="drawerClose">Close</button>'
        "<h2 id=\"dTitle\"></h2>"
        '<div class="kv"><b>Readme summary</b><div id="dSummary"></div></div>'
        '<div class="kv"><b>Entry points</b><div id="dEntries" class="chips"></div></div>'
        '<div class="kv"><b>Auto commands</b><div id="dCmds" class="chips"></div></div>'
        '<div class="kv"><b>Manifests</b><div id="dManifests" class="chips"></div></div>'
        '<div class="kv"><b>Last commit</b><div id="dCommit"></div></div>'
        '<div class="kv"><b>Run history</b><div id="dRuns" class="chips"></div></div>'
        "</aside>"
        "<script>window.__REPO_DATA__=" + repo_data_js
        + ";window.__RUN_HISTORY__=" + run_history_js + f";{_JS}</script>"
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# Markdown catalog
# ---------------------------------------------------------------------------


def render_catalog(payload: dict, summary: dict) -> str:
    """Render ``corpus_catalog.md``: deterministic markdown, one section per language."""
    repos = sorted(payload.get("repos", []) or [], key=lambda r: str(r.get("name") or ""))
    upstream = payload.get("upstream") if isinstance(payload.get("upstream"), dict) else None
    inventory = payload.get("inventory") if isinstance(payload.get("inventory"), dict) else None
    upstream_map = {
        str(u.get("name") or ""): u for u in (upstream or {}).get("repos", []) or []
    }
    inv_map = {str(r.get("name") or ""): r for r in (inventory or {}).get("repos", []) or []}

    total = summary.get("total", 0)
    forks = summary.get("forks", 0)
    ok = summary.get("upstream_ok", 0)
    checked = sum((summary.get("upstream_states", {}) or {}).values())
    total_loc = summary.get("total_loc", 0)
    summary_line = (
        f"{total} repos ({forks} forks), upstream ok {ok}/{checked}, "
        f"total LOC {total_loc:,}."
    )

    sections: dict[str, list[str]] = {}
    for r in repos:
        name = str(r.get("name") or "")
        lang = str(r.get("language") or "").strip() or "Unknown"
        state = str((upstream_map.get(name) or {}).get("state") or "n/a")
        loc = (inv_map.get(name) or {}).get("total_loc")
        date = str((inv_map.get(name) or {}).get("last_commit_date") or "n/a")
        desc = str(r.get("description") or "").replace("|", "\\|") or "n/a"
        row = (
            f"| [{name}]({r.get('html_url') or '#'}) "
            f"| {state} | {loc if loc is not None else 'n/a'} | {date} "
            f"| {'yes' if r.get('fork') else 'no'} | {desc} |"
        )
        sections.setdefault(lang, []).append(row)

    lines = [
        "# Corpus Catalog",
        "",
        f"Generated: {payload.get('generated_at') or 'n/a'}",
        "",
        summary_line,
        "",
    ]
    for lang in sorted(sections):
        lines.append(f"## {lang}")
        lines.append("")
        lines.append("| Repo | Upstream | LOC | Last commit | Fork | Description |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        lines.extend(sorted(sections[lang]))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def write_artifacts(payload: dict, summary: dict, project_root: Path) -> tuple[Path, Path]:
    """Write the dashboard HTML and corpus catalog; return both artifact paths."""
    dash_path = project_paths.web_dir(project_root) / project_paths.DASHBOARD
    cat_path = project_paths.data_dir(project_root) / project_paths.CORPUS_CATALOG
    jsonio.write_text(dash_path, render_dashboard(payload, summary))
    jsonio.write_text(cat_path, render_catalog(payload, summary))
    logger.info("wrote dashboard %s and catalog %s", dash_path, cat_path)
    return dash_path, cat_path