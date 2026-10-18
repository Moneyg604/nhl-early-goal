"""Publish the props pages under <site>/props/: index.html is today's slate, days/<date>.html the archive,
plus validation.json and factors.json for anyone checking the numbers."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from earlygoal.brand import head_tags

HEAD = """<link rel="manifest" href="{root}manifest.webmanifest"><meta name="theme-color" content="#0F1529"><link rel="apple-touch-icon" href="{root}apple-touch-icon.png"><meta name="apple-mobile-web-app-title" content="Gill Sports"><meta name="apple-mobile-web-app-capable" content="yes">"""
from earlygoal.site import slate_today

from .config import DATA_DIR, OUT_DIR
from .report import render


def build_props_site(site_dir: Path, out_dir: Path = OUT_DIR, keep_days: int = 30) -> Path | None:
    props_dir = site_dir / "props"
    days_dir = props_dir / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(out_dir.glob("props-*.json")):
        m = re.match(r"props-(\d{4}-\d{2}-\d{2})\.json$", f.name)
        if m:
            shutil.copy(f, days_dir / f"{m.group(1)}.json")
    jsons = sorted(days_dir.glob("*.json"), reverse=True)
    for stale in jsons[keep_days:]:
        stale.unlink(missing_ok=True)
        (days_dir / stale.name.replace(".json", ".html")).unlink(missing_ok=True)
    jsons = jsons[:keep_days]
    if not jsons:
        return None
    days = [p.name.replace(".json", "") for p in jsons]
    today = slate_today()
    past_or_today = [d for d in days if d <= today]
    index_day = today if today in days else (past_or_today[0] if past_or_today else days[-1])
    published = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def nav(selected: str, base: str) -> str:
        opts = "".join(f'<option value="{base}days/{d}.html" {"selected" if d == selected else ""}>{d}{" · today" if d == today else ""}</option>' for d in days)
        return (f'<div class="hmeta"><select class="daysel" onchange="location.href=this.value" aria-label="day">{opts}</select>'
                f'<span class="pub" style="margin-left:8px">published {published}</span></div>')

    for p in jsons:
        d = p.name.replace(".json", "")
        payload = json.loads(p.read_text())
        html = render(payload, root="../../", nhl_href="../../", nfl_href="../../nfl/")
        html = html.replace('<div class="hmeta"><span id="dayslot"></span></div>', nav(d, "../"), 1)
        html = html.replace("</head>", HEAD.format(root="../../") + head_tags("../../", "Gill Sports · NHL props", "NHL props: shots on goal, points, assists, anytime goal, blocked shots, team totals and power-play goals") + "</head>", 1)
        (days_dir / f"{d}.html").write_text(html, encoding="utf-8")
    payload = json.loads((days_dir / f"{index_day}.json").read_text())
    html = render(payload, root="../", nhl_href="../", nfl_href="../nfl/")
    html = html.replace('<div class="hmeta"><span id="dayslot"></span></div>', nav(index_day, "./"), 1)
    html = html.replace("</head>", HEAD.format(root="../") + head_tags("../", "Gill Sports · NHL props", "NHL props: shots on goal, points, assists, anytime goal, blocked shots, team totals and power-play goals") + "</head>", 1)
    (props_dir / "index.html").write_text(html, encoding="utf-8")
    (props_dir / "days.json").write_text(json.dumps({"days": days, "latest": index_day, "today": today, "published": published}, indent=1))
    for name in ("backtest_latest.json", "factors.json"):
        src = DATA_DIR / name
        if src.exists():
            shutil.copy(src, props_dir / ("validation.json" if name.startswith("backtest") else name))
    return props_dir


__all__ = ["build_props_site"]
