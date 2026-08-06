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

START = "<!-- CREST-ACTIVITY:START -->"
END = "<!-- CREST-ACTIVITY:END -->"

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "CREST-Interactive")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
API = "https://api.github.com"


def get_json(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "crest-profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(API + path, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def format_date(value: str | None) -> str:
    if not value:
        return "unknown"
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%d %b %Y")


def main() -> int:
    text = README.read_text(encoding="utf-8")

    user = get_json(f"/users/{urllib.parse.quote(OWNER)}")
    account_type = user.get("type", "User")

    if account_type == "Organization":
        endpoint = f"/orgs/{urllib.parse.quote(OWNER)}/repos?per_page=100&type=public&sort=pushed"
    else:
        endpoint = f"/users/{urllib.parse.quote(OWNER)}/repos?per_page=100&type=public&sort=pushed"

    repos = get_json(endpoint)
    repos = [
        repo
        for repo in repos
        if not repo.get("fork")
        and not repo.get("archived")
        and repo.get("name") != OWNER
    ]
    repos.sort(key=lambda repo: repo.get("pushed_at") or "", reverse=True)

    recent = repos[:4]
    languages = Counter(
        repo["language"] for repo in repos if repo.get("language")
    )
    language_text = ", ".join(name for name, _ in languages.most_common(5))
    language_text = language_text or "No public language data yet"

    refreshed = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y · %H:%M UTC")

    output = [
        START,
        f"<sub>Last refreshed **{refreshed}** · {len(repos)} active public repositories · visible languages: {markdown(language_text)}</sub>",
        "",
    ]

    if recent:
        for repo in recent:
            name = markdown(repo["name"])
            url = repo["html_url"]
            description = markdown(repo.get("description") or "No public description")
            language = markdown(repo.get("language") or "Mixed / unspecified")
            pushed = format_date(repo.get("pushed_at"))

            output.append(
                f"- **[{name}]({url})** — {description}  \n"
                f"  <sub>{language} · last public push {pushed}</sub>"
            )
    else:
        output.append("_No active public repositories were returned by GitHub._")

    output.append(END)
    replacement = "\n".join(output)

    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        print("README activity markers are missing.", file=sys.stderr)
        return 1

    updated = pattern.sub(replacement, text)
    if updated == text:
        print("README is already current.")
        return 0

    README.write_text(updated, encoding="utf-8")
    print("README activity section updated.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"GitHub API error {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
