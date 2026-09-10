#!/usr/bin/env python3
"""Write the generated highlight HTML into README.md between markers.

Also updates the "> Last updated: ..." line to today's date.
"""

import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(ROOT, "README.md")
HIGHLIGHT_PATH = os.path.join(ROOT, "data", "cache", "highlight.html")

START_MARK = "<!-- PROFILE-HIGHLIGHT:START -->"
END_MARK = "<!-- PROFILE-HIGHLIGHT:END -->"


def main():
    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()

    if START_MARK not in readme or END_MARK not in readme:
        print("[render] markers not found in README.md", file=sys.stderr)
        sys.exit(2)

    if os.path.exists(HIGHLIGHT_PATH):
        with open(HIGHLIGHT_PATH, "r", encoding="utf-8") as f:
            highlight = f.read().strip()
    else:
        highlight = ""

    # Replace everything between the markers.
    pattern = re.compile(
        re.escape(START_MARK) + r".*?" + re.escape(END_MARK),
        re.DOTALL,
    )
    readme = pattern.sub(START_MARK + "\n" + highlight + "\n" + END_MARK, readme)

    # Update the last-updated line.
    today = datetime.now(timezone.utc).strftime("%b %d, %Y")
    readme = re.sub(
        r"> Last updated: .*",
        f"> Last updated: {today}.",
        readme,
    )

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"[render] ok: README updated ({today})")


if __name__ == "__main__":
    main()