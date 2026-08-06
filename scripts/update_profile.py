from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

START = "<!-- CREST-LIVE:START -->"
END = "<!-- CREST-LIVE:END -->"

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "CREST-Interactive")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
API = "https://api.github.com"


def api_get(path: str):
    request = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "crest-profile-updater",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fmt_date(value: str | None) -> str:
    if not value:
        return "Unknown"
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%d %b %Y")


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def main() -> int:
    if not README.is_file():
        print("README.md is missing", file=sys.stderr)
        return 1

    profile = api_get(f"/users/{urllib.parse.quote(OWNER)}")
    account_type = profile.get("type", "User")

    if account_type == "Organization":
        repos_path = f"/orgs/{urllib.parse.quote(OWNER)}/repos?per_page=100&type=public&sort=pushed"
    else:
        repos_path = f"/users/{urllib.parse.quote(OWNER)}/repos?per_page=100&type=public&sort=pushed"

    repos = api_get(repos_path)
    repos = [
        repo for repo in repos
        if not repo.get("fork")
        and not repo.get("archived")
        and repo.get("name") != OWNER
    ]

    repos.sort(key=lambda repo: repo.get("pushed_at") or "", reverse=True)
    recent = repos[:5]

    language_counts = Counter()
    for repo in recent[:8]:
        language = repo.get("language")
        if language:
            language_counts[language] += 1

    language_signal = ", ".join(name for name, _ in language_counts.most_common(5)) or "Not enough public data"
    latest = recent[0] if recent else None
    latest_name = (
        f"[{escape_md(latest['name'])}]({latest['html_url']})"
        if latest else "No active public repository"
    )

    now = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y · %H:%M UTC")

    lines = [
        START,
        "| Signal | Current reading |",
        "|---|---|",
        f"| **Profile refresh** | {now} |",
        f"| **Public repositories** | {len(repos)} non-fork, non-archived repositories |",
        f"| **Recently active repository** | {latest_name} |",
        f"| **Visible language signals** | {escape_md(language_signal)} |",
        "",
        "### Recently active public work",
        "",
    ]

    if recent:
        for repo in recent:
            description = escape_md(repo.get("description") or "No public description")
            pushed = fmt_date(repo.get("pushed_at"))
            language = repo.get("language") or "Mixed / unspecified"
            lines.append(
                f"- **[{escape_md(repo['name'])}]({repo['html_url']})** "
                f"— {description}  \n"
                f"  <sub>{escape_md(language)} · last public push {pushed}</sub>"
            )
    else:
        lines.append("_No active public repositories were returned by the GitHub API._")

    lines.append(END)
    replacement = "\n".join(lines)

    current = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)

    if not pattern.search(current):
        print("Live signal markers are missing from README.md", file=sys.stderr)
        return 1

    updated = pattern.sub(replacement, current)

    if updated == current:
        print("README live signal is already current.")
        return 0

    README.write_text(updated, encoding="utf-8")
    print("README live signal updated.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"GitHub API error {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"Profile update failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
