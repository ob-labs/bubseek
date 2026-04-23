#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Generate a beautiful GitHub-trending-style SVG/PNG card.

Usage:
    uv run gh_trending_card.py [--language python] [--since daily] [--limit 10] [--output trending.svg]
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path

# ── Data fetching ────────────────────────────────────────────────────────────

_GITHUB_API = "https://api.github.com"
_TRENDING_URL = "https://github.com/trending"


def _github_headers(*, accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "bubseek-github-repo-cards",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_get(url: str, *, accept: str) -> tuple[bytes, str]:
    curl = shutil.which("curl")
    headers = _github_headers(accept=accept)
    if curl:
        command = [curl, "-fsSL", "--compressed", "--retry", "2", "--connect-timeout", "20"]
        for name, value in headers.items():
            command.extend(["-H", f"{name}: {value}"])
        command.append(url)
        response = subprocess.run(command, capture_output=True, check=True)
        return response.stdout, "application/octet-stream"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(), response.headers.get("Content-Type", "application/octet-stream")


def _api_json(url: str, *, accept: str = "application/vnd.github+json") -> dict | list:
    payload, _ = _http_get(url, accept=accept)
    return json.loads(payload.decode("utf-8"))


def _api_text(url: str, *, accept: str = "text/html") -> str:
    payload, _ = _http_get(url, accept=accept)
    return payload.decode("utf-8")


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _gh_json(*args: str) -> dict | list:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip())


def _gh_stats_json(endpoint: str, retries: int = 4) -> dict | list:
    """Fetch a GitHub stats endpoint with retry for 202 (computing) responses."""
    raw: dict | list = {}
    for attempt in range(retries):
        if _gh_available():
            raw = _gh_json("api", endpoint, "--cache", "0s")
        else:
            try:
                raw = _api_json(f"{_GITHUB_API}/{endpoint}")
            except urllib.error.HTTPError as exc:
                if exc.code != HTTPStatus.ACCEPTED:
                    raise
                raw = {}
        if isinstance(raw, list):
            return raw
        delay = 2**attempt
        print(f"   ⏳ {endpoint.split('/')[-1]} computing, retry in {delay}s …", file=sys.stderr)
        time.sleep(delay)
    return raw


def fetch_trending(language: str = "", since: str = "daily", limit: int = 10) -> list[dict]:
    """Fetch trending repositories from the public trending page.

    If parsing fails or GitHub changes the page shape, fall back to the search API.
    """
    repos = _fetch_trending_page(language=language, since=since, limit=limit)
    if repos:
        return repos
    return _fetch_trending_via_search_api(language=language, since=since, limit=limit)


def _fetch_trending_page(language: str = "", since: str = "daily", limit: int = 10) -> list[dict]:
    params = {"since": since}
    if language:
        params["l"] = language

    html_text = _api_text(f"{_TRENDING_URL}?{urllib.parse.urlencode(params)}")
    repo_matches = re.findall(
        r'<h2 class="h3 lh-condensed">\s*<a href="/([^"]+)">.*?</a>\s*</h2>(.*?)</article>',
        html_text,
        flags=re.DOTALL,
    )

    results = []
    for full_name, article_body in repo_matches[:limit]:
        normalized_name = "/".join(part.strip() for part in full_name.split("/"))
        description_match = re.search(
            r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>',
            article_body,
            flags=re.DOTALL,
        )
        language_match = re.search(
            r'<span itemprop="programmingLanguage">\s*(.*?)\s*</span>',
            article_body,
            flags=re.DOTALL,
        )
        stars_and_forks = re.findall(r'href="/[^"]+/(stargazers|forks)">\s*([\d,]+)\s*</a>', article_body)
        counts = {kind: int(count.replace(",", "")) for kind, count in stars_and_forks}

        results.append({
            "full_name": normalized_name,
            "description": html.unescape(_strip_tags(description_match.group(1)))[:120] if description_match else "",
            "language": html.unescape(language_match.group(1).strip()) if language_match else "",
            "stars": counts.get("stargazers", 0),
            "forks": counts.get("forks", 0),
            "commits_week": _fetch_weekly_commits(normalized_name),
        })
    return results


def _fetch_trending_via_search_api(language: str = "", since: str = "daily", limit: int = 10) -> list[dict]:
    window = {"daily": 1, "weekly": 7, "monthly": 30}.get(since, 1)
    cutoff = (datetime.now(UTC) - timedelta(days=window)).strftime("%Y-%m-%d")

    q_parts = [f"pushed:>={cutoff}", "stars:>=10"]
    if language:
        q_parts.append(f"language:{language}")
    query = urllib.parse.quote_plus(" ".join(q_parts))

    url = f"{_GITHUB_API}/search/repositories?q={query}&sort=stars&order=desc&per_page={limit}"
    raw = (
        _gh_json(
            "api", f"search/repositories?q={'+'.join(q_parts)}&sort=stars&order=desc&per_page={limit}", "--cache", "1h"
        )
        if _gh_available()
        else _api_json(url)
    )
    items = raw.get("items", []) if isinstance(raw, dict) else []
    results = []
    for repo in items[:limit]:
        results.append({
            "full_name": repo["full_name"],
            "description": (repo.get("description") or "")[:120],
            "language": repo.get("language") or "",
            "stars": repo["stargazers_count"],
            "forks": repo["forks_count"],
            "commits_week": _fetch_weekly_commits(repo["full_name"]),
        })
    return results


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", " ".join(text.split()))


def _fetch_weekly_commits(nwo: str) -> list[int]:
    """Fetch last 8 weeks of commit counts with retry for stats computation."""
    try:
        raw = _gh_stats_json(f"repos/{nwo}/stats/commit_activity")
        if not isinstance(raw, list):
            return []
        return [w.get("total", 0) for w in raw[-8:]]
    except Exception:
        return []


# ── SVG constants ────────────────────────────────────────────────────────────

_LANG_COLORS: dict[str, str] = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "Java": "#b07219",
    "C": "#555555",
    "C++": "#f34b7d",
    "C#": "#178600",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "Scala": "#c22d40",
    "Shell": "#89e051",
    "Lua": "#000080",
    "Dart": "#00B4AB",
    "Elixir": "#6e4a7e",
    "Haskell": "#5e5086",
    "Zig": "#ec915c",
    "Nix": "#7e7eff",
    "Vue": "#41b883",
    "Svelte": "#ff3e00",
    "Jupyter Notebook": "#DA5B0B",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
}


def _esc(text: str | None) -> str:
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def _mini_bar_chart(values: list[int], x: float, y: float, w: float, h: float) -> str:
    """Render a tiny bar chart as SVG rects."""
    if not values:
        return ""
    n = len(values)
    mx = max(values) or 1
    bar_w = max(w / n - 2, 2)
    gap = (w - bar_w * n) / max(n - 1, 1) if n > 1 else 0
    bars: list[str] = []
    for i, v in enumerate(values):
        bh = max((v / mx) * h, 1)
        bx = x + i * (bar_w + gap)
        by = y + h - bh
        opacity = 0.4 + 0.6 * (v / mx)
        bars.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
            f'rx="1.5" fill="#58a6ff" opacity="{opacity:.2f}"/>'
        )
    return "\n    ".join(bars)


def _format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


# ── SVG rendering ────────────────────────────────────────────────────────────


def render_trending_svg(repos: list[dict], title: str = "Trending Repositories") -> str:
    card_w = 820
    pad = 28
    row_h = 96
    header_h = 56
    card_h = pad + header_h + len(repos) * row_h + pad

    parts: list[str] = []

    parts.append(f"""\
<svg xmlns="http://www.w3.org/2000/svg" width="{card_w}" height="{card_h}" viewBox="0 0 {card_w} {card_h}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <filter id="shadow" x="-4%" y="-4%" width="108%" height="108%">
      <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.4"/>
    </filter>
  </defs>
  <rect width="{card_w}" height="{card_h}" rx="16" fill="url(#bg)" filter="url(#shadow)"/>
  <rect width="{card_w}" height="{card_h}" rx="16" fill="none" stroke="#30363d" stroke-width="1"/>
""")

    cy = pad

    # ── Title ──
    parts.append(f"""\
  <g transform="translate({pad},{cy})">
    <svg width="22" height="22" viewBox="0 0 16 16" fill="#f0883e" y="-2">
      <path d="M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z"/>
    </svg>
    <text x="30" y="16" font-family="'Segoe UI',system-ui,sans-serif" font-size="18" font-weight="700" fill="#c9d1d9">{_esc(title)}</text>
  </g>
""")
    cy += header_h

    # ── Rows ──
    for idx, repo in enumerate(repos):
        ry = cy + idx * row_h
        full_name = repo["full_name"]
        desc = repo["description"]
        lang = repo["language"]
        lang_color = _LANG_COLORS.get(lang, "#888")
        stars = repo["stars"]
        forks = repo["forks"]
        commits_week = repo.get("commits_week", [])

        # Separator line (not for first row)
        if idx > 0:
            parts.append(
                f'  <line x1="{pad}" y1="{ry}" x2="{card_w - pad}" y2="{ry}" stroke="#21262d" stroke-width="1"/>\n'
            )

        # Rank badge
        parts.append(
            f'  <g transform="translate({pad},{ry + 12})">\n'
            f'    <rect width="28" height="28" rx="8" fill="#1f2937"/>\n'
            f'    <text x="14" y="19" text-anchor="middle" font-family="\'Segoe UI\',system-ui,sans-serif" '
            f'font-size="13" font-weight="700" fill="#58a6ff">{idx + 1}</text>\n'
            f"  </g>\n"
        )

        # Repo name
        name_x = pad + 40
        parts.append(
            f'  <text x="{name_x}" y="{ry + 26}" '
            f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="15" font-weight="600" fill="#58a6ff">'
            f"{_esc(full_name)}</text>\n"
        )

        # Description (truncated single line)
        desc_text = (desc[:90] + "…") if len(desc) > 90 else desc
        parts.append(
            f'  <text x="{name_x}" y="{ry + 46}" '
            f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="12" fill="#8b949e">'
            f"{_esc(desc_text)}</text>\n"
        )

        # Bottom meta row: language · stars · forks
        meta_y = ry + 68
        mx = name_x
        if lang:
            parts.append(
                f'  <circle cx="{mx + 5}" cy="{meta_y}" r="5" fill="{lang_color}"/>\n'
                f'  <text x="{mx + 14}" y="{meta_y + 4}" '
                f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="11" fill="#8b949e">'
                f"{_esc(lang)}</text>\n"
            )
            mx += 14 + len(lang) * 6.5 + 16

        # Star icon + count
        parts.append(
            f'  <svg x="{mx}" y="{meta_y - 7}" width="14" height="14" viewBox="0 0 16 16" fill="#e3b341">'
            f'<path d="M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z"/>'
            f"</svg>\n"
            f'  <text x="{mx + 18}" y="{meta_y + 4}" '
            f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="11" fill="#c9d1d9">'
            f"{_format_count(stars)}</text>\n"
        )
        mx += 18 + len(_format_count(stars)) * 7 + 16

        # Fork icon + count
        parts.append(
            f'  <svg x="{mx}" y="{meta_y - 7}" width="14" height="14" viewBox="0 0 16 16" fill="#8b949e">'
            f'<path d="M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v.878A2.25 2.25 0 005.75 8.5h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 2.25 0 002.25-2.25v-.878a2.25 2.25 0 10-1.5 0v.878a.75.75 0 01-.75.75h-4.5A.75.75 0 015 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm3-8.75a.75.75 0 100-1.5.75.75 0 000 1.5z"/>'
            f"</svg>\n"
            f'  <text x="{mx + 18}" y="{meta_y + 4}" '
            f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="11" fill="#c9d1d9">'
            f"{_format_count(forks)}</text>\n"
        )

        # Mini commit bar chart on the right (or placeholder)
        chart_w = 100
        chart_h = 32
        chart_x = card_w - pad - chart_w
        chart_y = ry + 18
        if commits_week:
            bars = _mini_bar_chart(commits_week, chart_x, chart_y, chart_w, chart_h)
            parts.append(f"  {bars}\n")
            parts.append(
                f'  <text x="{chart_x + chart_w / 2}" y="{chart_y + chart_h + 14}" '
                f'text-anchor="middle" font-family="\'Segoe UI\',system-ui,sans-serif" '
                f'font-size="9" fill="#484f58">commits/week</text>\n'
            )
        else:
            # Subtle dashed baseline so the area doesn't look broken
            parts.append(
                f'  <line x1="{chart_x}" y1="{chart_y + chart_h}" '
                f'x2="{chart_x + chart_w}" y2="{chart_y + chart_h}" '
                f'stroke="#21262d" stroke-width="1" stroke-dasharray="4,3"/>\n'
                f'  <text x="{chart_x + chart_w / 2}" y="{chart_y + chart_h + 14}" '
                f'text-anchor="middle" font-family="\'Segoe UI\',system-ui,sans-serif" '
                f'font-size="9" fill="#30363d">no activity data</text>\n'
            )

    parts.append("</svg>")
    return "".join(parts)


# ── SVG → PNG ────────────────────────────────────────────────────────────────


def svg_to_png(svg_path: Path) -> Path:
    png_path = svg_path.with_suffix(".png")
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run(
            [rsvg, "-o", str(png_path), "--dpi-x", "192", "--dpi-y", "192", str(svg_path)],
            check=True,
        )
        return png_path
    convert = shutil.which("convert")
    if convert:
        subprocess.run(
            [convert, "-density", "192", str(svg_path), str(png_path)],
            check=True,
        )
        return png_path
    print("⚠  No SVG→PNG converter found (need rsvg-convert or ImageMagick convert)", file=sys.stderr)
    return svg_path


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a GitHub trending card (SVG + PNG)")
    parser.add_argument("--language", default="", help="Filter by language (e.g. python, rust)")
    parser.add_argument(
        "--since", default="daily", choices=["daily", "weekly", "monthly"], help="Trending window (default: daily)"
    )
    parser.add_argument("--limit", type=int, default=10, help="Number of repos (default: 10)")
    parser.add_argument("--output", default=None, help="Output SVG path (default: trending.svg)")
    args = parser.parse_args()

    out = Path(args.output) if args.output else Path("trending.svg")

    lang_label = args.language or "all languages"
    title = f"Trending Repositories — {lang_label} ({args.since})"

    print(f"🔍 Fetching trending repos ({lang_label}, {args.since}) …")
    repos = fetch_trending(language=args.language, since=args.since, limit=args.limit)

    if not repos:
        print("❌ No trending repos found.", file=sys.stderr)
        sys.exit(1)

    print(f"🎨 Rendering {len(repos)} repos …")
    svg = render_trending_svg(repos, title=title)
    out.write_text(svg, encoding="utf-8")
    print(f"   → {out}")

    print("🖼  Converting to PNG …")
    png = svg_to_png(out)
    print(f"   → {png}")
    print("✅ Done!")


if __name__ == "__main__":
    main()
