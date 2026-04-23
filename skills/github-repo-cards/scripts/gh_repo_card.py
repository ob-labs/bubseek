#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Generate a beautiful GitHub-style SVG/PNG card for a repository.

Usage:
    uv run gh_repo_card.py <org>/<repo> [--top-n 5] [--analysis "text"] [--output card.svg]
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import cast

# ── Data fetching via gh CLI / GitHub API ────────────────────────────────────

_GITHUB_API = "https://api.github.com"


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
    return cast(dict | list, json.loads(payload.decode("utf-8")))


def _api_bytes(url: str, *, accept: str = "application/octet-stream") -> tuple[bytes, str]:
    return _http_get(url, accept=accept)


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _gh_json(*args: str) -> dict | list:
    return json.loads(_gh(*args))


def _gh_stats_json(endpoint: str, retries: int = 4) -> dict | list:
    """Fetch a GitHub stats endpoint with retry for 202 (computing) responses.

    GitHub stats APIs return ``{}`` while computing data on the first call.
    We retry with exponential back-off until an array is returned.
    """
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
        print(f"   ⏳ stats computing, retry in {delay}s …", file=sys.stderr)
        time.sleep(delay)

    return raw


def fetch_repo_info(nwo: str) -> dict:
    """Fetch basic repo metadata."""
    if not _gh_available():
        raw = _api_json(f"{_GITHUB_API}/repos/{nwo}")
        if not isinstance(raw, dict):
            raise TypeError(f"Unexpected response for repository {nwo!r}")
        return {
            "name": raw.get("name"),
            "owner": {"login": raw.get("owner", {}).get("login", "")},
            "description": raw.get("description"),
            "stargazerCount": raw.get("stargazers_count", 0),
            "forkCount": raw.get("forks_count", 0),
            "primaryLanguage": {"name": raw.get("language") or ""},
            "licenseInfo": {"name": (raw.get("license") or {}).get("name", "")},
            "updatedAt": raw.get("updated_at"),
            "url": raw.get("html_url"),
            "homepageUrl": raw.get("homepage"),
        }

    return cast(
        dict,
        _gh_json(
            "repo",
            "view",
            nwo,
            "--json",
            "name,owner,description,stargazerCount,forkCount,primaryLanguage,licenseInfo,updatedAt,url,homepageUrl",
        ),
    )


def fetch_commit_activity(nwo: str) -> list[int]:
    """Fetch last 52 weeks of commit counts via the stats/commit_activity API."""
    raw = _gh_stats_json(f"repos/{nwo}/stats/commit_activity")
    if not isinstance(raw, list):
        return []
    return [week.get("total", 0) for week in raw[-52:]]


def fetch_stargazer_counts(nwo: str) -> list[int]:
    """Approximate recent star activity from the last page of stargazers.

    Fetches only the last 100 stargazers (single API call) to build a
    rough weekly bucketed curve.
    """
    try:
        if _gh_available():
            raw = _gh(
                "api",
                f"repos/{nwo}/stargazers?per_page=100",
                "-H",
                "Accept: application/vnd.github.star+json",
                "--cache",
                "1h",
            )
            if not raw:
                return []
            items = json.loads(raw)
        else:
            items = _api_json(
                f"{_GITHUB_API}/repos/{nwo}/stargazers?per_page=100",
                accept="application/vnd.github.star+json",
            )

        if not isinstance(items, list):
            return []

        from collections import Counter

        weeks: Counter[str] = Counter()
        for item in items:
            d = item.get("starred_at", "")
            try:
                dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
                weeks[dt.strftime("%G-W%V")] += 1
            except ValueError:
                continue
        if not weeks:
            return []
        sorted_keys = sorted(weeks)[-26:]
        return [weeks[k] for k in sorted_keys]
    except Exception:
        return []


def _download_avatar_b64(url: str, size: int = 64) -> str:
    """Download an avatar and return a data-URI (base64-encoded PNG).

    Falls back to an empty string so the SVG stays valid if download fails.
    """
    fetch_url = f"{url}&s={size}" if "?" in url else f"{url}?s={size}"
    try:
        data, content_type = _api_bytes(fetch_url)
        return f"data:{content_type};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return ""


def fetch_top_contributors(nwo: str, n: int = 5) -> list[dict]:
    """Return top-N contributors by commit count (with embedded avatar data)."""
    if _gh_available():
        raw = _gh_json("api", f"repos/{nwo}/contributors?per_page={n}", "--cache", "1h")
    else:
        raw = _api_json(f"{_GITHUB_API}/repos/{nwo}/contributors?per_page={n}")
    if not isinstance(raw, list):
        return []
    results = []
    for c in raw[:n]:
        avatar_data = _download_avatar_b64(c["avatar_url"])
        results.append({
            "login": c["login"],
            "avatar_data": avatar_data,
            "contributions": c["contributions"],
        })
    return results


def build_default_analysis(info: dict) -> str:
    """Generate a concise analysis paragraph from repository metadata."""
    updated_at = info.get("updatedAt")
    updated_text = ""
    if isinstance(updated_at, str):
        try:
            updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            updated_text = updated_dt.strftime("%Y-%m-%d")
        except ValueError:
            updated_text = updated_at

    license_name = (info.get("licenseInfo") or {}).get("name", "") or "No license metadata"
    lang = (info.get("primaryLanguage") or {}).get("name", "") or "Unknown language"
    homepage = info.get("homepageUrl") or "No homepage"

    fragments = [
        f"Primary language: {lang}.",
        f"License: {license_name}.",
        f"Homepage: {homepage}.",
    ]
    if updated_text:
        fragments.append(f"Last updated: {updated_text}.")
    return " ".join(fragments)


# ── SVG rendering ────────────────────────────────────────────────────────────

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
}


def _sparkline_path(values: list[int], x: float, y: float, w: float, h: float) -> str:
    """Build an SVG <path> d-attribute for a sparkline area chart."""
    if not values:
        return ""
    n = len(values)
    mx = max(values) or 1
    points: list[str] = []
    for i, v in enumerate(values):
        px = x + (i / max(n - 1, 1)) * w
        py = y + h - (v / mx) * h
        points.append(f"{px:.1f},{py:.1f}")
    line = " L".join(points)
    return f"M{line} L{x + w:.1f},{y + h:.1f} L{x:.1f},{y + h:.1f} Z"


def _esc(text: str | None) -> str:
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def _wrap(text: str, width: int = 70) -> list[str]:
    return textwrap.wrap(text, width=width) if text else []


def render_repo_svg(  # noqa: C901
    info: dict,
    commits: list[int],
    stars: list[int],
    contributors: list[dict],
    analysis: str = "",
    top_n: int = 5,
) -> str:
    name = info.get("name", "")
    owner = info.get("owner", {}).get("login", "")
    desc = info.get("description") or ""
    star_count = info.get("stargazerCount", 0)
    fork_count = info.get("forkCount", 0)
    lang = (info.get("primaryLanguage") or {}).get("name", "")
    lang_color = _LANG_COLORS.get(lang, "#888")
    license_name = (info.get("licenseInfo") or {}).get("name", "")
    url = info.get("url", "")

    # ── Layout constants ──
    card_w = 820
    pad = 32
    content_w = card_w - pad * 2

    # dynamic height calculation
    desc_lines = _wrap(desc, 80)
    analysis_lines = _wrap(analysis, 80) if analysis else []
    contrib_rows = (min(len(contributors), top_n) + 3) // 4  # 4 per row

    has_sparklines = bool(commits or stars)

    header_h = 80
    desc_h = max(len(desc_lines) * 20 + 12, 0)
    stats_h = 40
    sparkline_h = 140 if has_sparklines else 0
    contrib_header_h = 36 if contributors else 0
    contrib_h = contrib_rows * 52 + 16 if contributors else 0
    analysis_header_h = 36 if analysis else 0
    analysis_h = len(analysis_lines) * 20 + 20 if analysis else 0
    footer_h = 24

    card_h = (
        pad
        + header_h
        + desc_h
        + stats_h
        + sparkline_h
        + contrib_header_h
        + contrib_h
        + analysis_header_h
        + analysis_h
        + footer_h
        + pad
    )

    parts: list[str] = []

    # ── Card shell ──
    parts.append(f"""\
<svg xmlns="http://www.w3.org/2000/svg" width="{card_w}" height="{card_h}" viewBox="0 0 {card_w} {card_h}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="commitGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.05"/>
    </linearGradient>
    <linearGradient id="starGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f0883e" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="#f0883e" stop-opacity="0.05"/>
    </linearGradient>
    <filter id="shadow" x="-4%" y="-4%" width="108%" height="108%">
      <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.4"/>
    </filter>
    <clipPath id="avatarClip"><circle cx="16" cy="16" r="16"/></clipPath>
  </defs>
  <rect width="{card_w}" height="{card_h}" rx="16" fill="url(#bg)" filter="url(#shadow)"/>
  <rect width="{card_w}" height="{card_h}" rx="16" fill="none" stroke="#30363d" stroke-width="1"/>
""")

    cy = pad  # current y cursor

    # ── Header: icon + name ──
    # Repo icon (octicon book)
    parts.append(f"""\
  <g transform="translate({pad},{cy})">
    <svg width="20" height="20" viewBox="0 0 16 16" fill="#8b949e">
      <path fill-rule="evenodd" d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9z"/>
    </svg>
    <text x="28" y="15" font-family="'Segoe UI',system-ui,sans-serif" font-size="14" fill="#8b949e">{_esc(owner)} /</text>
    <text x="{32 + len(owner) * 8}" y="15" font-family="'Segoe UI',system-ui,sans-serif" font-size="16" font-weight="600" fill="#58a6ff">{_esc(name)}</text>
  </g>
""")

    # badges row
    badge_y = cy + 30
    parts.append(f"""\
  <g transform="translate({pad},{badge_y})" font-family="'Segoe UI',system-ui,sans-serif" font-size="12">
    <rect rx="10" width="auto" height="20" fill="none"/>
""")
    bx = 0
    if lang:
        parts.append(f"""\
    <circle cx="{bx + 6}" cy="10" r="6" fill="{lang_color}"/>
    <text x="{bx + 16}" y="14" fill="#c9d1d9">{_esc(lang)}</text>
""")
        bx += 16 + len(lang) * 7 + 16
    if license_name:
        # license icon
        parts.append(f"""\
    <svg x="{bx}" y="0" width="16" height="20" viewBox="0 0 16 16" fill="#8b949e">
      <path fill-rule="evenodd" d="M8.75.75a.75.75 0 00-1.5 0V2h-.984c-.305 0-.604.08-.869.23l-1.288.737A.25.25 0 013.984 3H1.75a.75.75 0 000 1.5h.428L.066 9.192a.75.75 0 00.154.838l.53-.53-.53.53v.001l.002.002.004.005.01.01.031.034.111.112.395.372c.33.299.786.668 1.386 1.016C2.879 11.952 3.87 12.5 5 12.5c1.13 0 2.121-.548 2.84-.918a12.154 12.154 0 001.892-1.5l.013-.014.004-.005.001-.001-.53-.53.53.53a.75.75 0 00.154-.838L7.822 4.5h.428a.75.75 0 000-1.5H6.984l-.002-.001L5.13 1.68a.25.25 0 01.124-.18L6.543 .763A1.75 1.75 0 017.766 0H8.75zM5 11c-.377 0-.745-.141-1.017-.29a9.56 9.56 0 01-1.32-.905l1.662-3.968a.25.25 0 01.462 0l1.662 3.968c-.389.336-.79.608-1.32.905A3.09 3.09 0 015 11z"/>
    </svg>
    <text x="{bx + 20}" y="14" fill="#8b949e">{_esc(license_name)}</text>
""")
        bx += 20 + len(license_name) * 7 + 16
    parts.append("  </g>\n")

    # description
    cy = badge_y + 32
    if desc_lines:
        for i, line in enumerate(desc_lines):
            parts.append(
                f'  <text x="{pad}" y="{cy + 14 + i * 20}" '
                f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="14" fill="#8b949e">'
                f"{_esc(line)}</text>\n"
            )
        cy += len(desc_lines) * 20 + 12

    # ── Stats row ──
    parts.append(f"""\
  <g transform="translate({pad},{cy})" font-family="'Segoe UI',system-ui,sans-serif" font-size="13" fill="#c9d1d9">
    <svg width="16" height="16" viewBox="0 0 16 16" fill="#e3b341" y="0">
      <path d="M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z"/>
    </svg>
    <text x="22" y="13">{star_count:,}</text>
    <svg x="90" width="16" height="16" viewBox="0 0 16 16" fill="#8b949e" y="0">
      <path d="M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v.878A2.25 2.25 0 005.75 8.5h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 2.25 0 002.25-2.25v-.878a2.25 2.25 0 10-1.5 0v.878a.75.75 0 01-.75.75h-4.5A.75.75 0 015 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm3-8.75a.75.75 0 100-1.5.75.75 0 000 1.5z"/>
    </svg>
    <text x="112" y="13">{fork_count:,}</text>
  </g>
""")
    cy += stats_h

    # ── Sparkline charts ──
    if has_sparklines:
        spark_pad_top = 8
        spark_label_h = 18
        spark_area_h = sparkline_h - spark_label_h - spark_pad_top - 16

        both = bool(commits and stars)
        chart_w = (content_w - 20) / 2 if both else content_w

        # Commit activity
        if commits:
            parts.append(
                f'  <text x="{pad}" y="{cy + spark_label_h}" '
                f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="11" '
                f'font-weight="600" fill="#58a6ff" text-transform="uppercase" letter-spacing="1">'
                f"COMMIT ACTIVITY (52 w)</text>\n"
            )
            path_d = _sparkline_path(commits, pad, cy + spark_label_h + spark_pad_top, chart_w, spark_area_h)
            if path_d:
                parts.append(f'  <path d="{path_d}" fill="url(#commitGrad)" stroke="#58a6ff" stroke-width="1.5"/>\n')

        # Star activity
        if stars:
            sx = (pad + chart_w + 20) if both else pad
            parts.append(
                f'  <text x="{sx}" y="{cy + spark_label_h}" '
                f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="11" '
                f'font-weight="600" fill="#f0883e" text-transform="uppercase" letter-spacing="1">'
                f"STAR ACTIVITY</text>\n"
            )
            path_d = _sparkline_path(stars, sx, cy + spark_label_h + spark_pad_top, chart_w, spark_area_h)
            if path_d:
                parts.append(f'  <path d="{path_d}" fill="url(#starGrad)" stroke="#f0883e" stroke-width="1.5"/>\n')

        cy += sparkline_h

    # ── Top contributors ──
    if contributors:
        parts.append(
            f'  <text x="{pad}" y="{cy + 14}" '
            f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="12" '
            f'font-weight="600" fill="#c9d1d9" letter-spacing="0.5">'
            f"TOP CONTRIBUTORS</text>\n"
        )
        cy += contrib_header_h
        per_row = 4
        col_w = content_w / per_row
        for idx, c in enumerate(contributors[:top_n]):
            row, col = divmod(idx, per_row)
            cx_ = pad + col * col_w
            cy_ = cy + row * 52
            login = _esc(c["login"])
            contribs = c["contributions"]
            avatar_data = c.get("avatar_data", "")
            # Avatar: use embedded base64 data-URI, fall back to initial circle
            if avatar_data:
                avatar_el = (
                    f'    <clipPath id="ac{idx}"><circle cx="16" cy="16" r="16"/></clipPath>\n'
                    f'    <image href="{avatar_data}" x="0" y="0" width="32" height="32" clip-path="url(#ac{idx})"/>'
                )
            else:
                initial = _esc(login[0].upper()) if login else "?"
                avatar_el = (
                    f'    <circle cx="16" cy="16" r="16" fill="#30363d"/>\n'
                    f'    <text x="16" y="21" text-anchor="middle" font-family="\'Segoe UI\',system-ui,sans-serif" '
                    f'font-size="14" font-weight="600" fill="#c9d1d9">{initial}</text>'
                )
            parts.append(
                f'  <g transform="translate({cx_},{cy_})">\n'
                f"{avatar_el}\n"
                f'    <text x="40" y="14" font-family="\'Segoe UI\',system-ui,sans-serif" font-size="13" font-weight="600" fill="#c9d1d9">{login}</text>\n'
                f'    <text x="40" y="30" font-family="\'Segoe UI\',system-ui,sans-serif" font-size="11" fill="#8b949e">{contribs:,} commits</text>\n'
                f"  </g>\n"
            )
        cy += contrib_h

    # ── Analysis block ──
    if analysis_lines:
        parts.append(
            f'  <text x="{pad}" y="{cy + 14}" '
            f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="12" '
            f'font-weight="600" fill="#c9d1d9" letter-spacing="0.5">'
            f"ANALYSIS</text>\n"
        )
        cy += analysis_header_h
        # background box
        box_h = len(analysis_lines) * 20 + 16
        parts.append(
            f'  <rect x="{pad}" y="{cy}" width="{content_w}" height="{box_h}" rx="8" '
            f'fill="#1c2128" stroke="#30363d" stroke-width="1"/>\n'
        )
        for i, line in enumerate(analysis_lines):
            parts.append(
                f'  <text x="{pad + 12}" y="{cy + 18 + i * 20}" '
                f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="13" fill="#8b949e">'
                f"{_esc(line)}</text>\n"
            )
        cy += analysis_h

    # ── Footer ──
    cy += 8
    parts.append(
        f'  <text x="{pad}" y="{cy + 12}" '
        f'font-family="\'Segoe UI\',system-ui,sans-serif" font-size="10" fill="#484f58">'
        f"{_esc(url)}</text>\n"
    )

    parts.append("</svg>")
    return "".join(parts)


# ── SVG → PNG conversion ────────────────────────────────────────────────────


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
    parser = argparse.ArgumentParser(description="Generate a GitHub repo card (SVG + PNG)")
    parser.add_argument("repo", help="Repository in <org>/<repo> format")
    parser.add_argument("--top-n", type=int, default=5, help="Number of top contributors (default: 5)")
    parser.add_argument("--analysis", default="", help="Analysis text to include on the card")
    parser.add_argument("--output", default=None, help="Output SVG path (default: <repo>.svg)")
    args = parser.parse_args()

    nwo = args.repo
    if "/" not in nwo:
        parser.error("Repository must be in <org>/<repo> format")

    out = Path(args.output) if args.output else Path(nwo.split("/")[1] + ".svg")

    print(f"📦 Fetching info for {nwo} …")
    info = fetch_repo_info(nwo)

    print("📈 Fetching commit activity …")
    commits = fetch_commit_activity(nwo)

    print("⭐ Fetching star activity …")
    stars = fetch_stargazer_counts(nwo)

    print(f"👥 Fetching top {args.top_n} contributors …")
    contributors = fetch_top_contributors(nwo, args.top_n)

    print("🎨 Rendering SVG …")
    analysis = args.analysis or build_default_analysis(info)
    svg = render_repo_svg(info, commits, stars, contributors, analysis=analysis, top_n=args.top_n)
    out.write_text(svg, encoding="utf-8")
    print(f"   → {out}")

    print("🖼  Converting to PNG …")
    png = svg_to_png(out)
    print(f"   → {png}")
    print("✅ Done!")


if __name__ == "__main__":
    main()
