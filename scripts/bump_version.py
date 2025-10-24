#!/usr/bin/env python3
import re
import sys
from pathlib import Path

PYPROJECT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pyproject.toml")

if not PYPROJECT.exists():
    print(f"pyproject.toml not found at: {PYPROJECT}", file=sys.stderr)
    sys.exit(0)

text = PYPROJECT.read_text(encoding="utf-8")

# Find [project] section boundaries
project_start = text.find("[project]")
if project_start == -1:
    print("[project] section not found; skipping version bump", file=sys.stderr)
    sys.exit(0)

# Find next section header to limit search range
next_section = text.find("[", project_start + 1)
section_text = text[project_start: next_section if next_section != -1 else len(text)]

# Regex to capture semantic version in version = "X.Y.Z"
version_re = re.compile(r"^version\s*=\s*['\"](\d+)\.(\d+)\.(\d+)['\"]", re.MULTILINE)
match = version_re.search(section_text)

if not match:
    print("Version line not found in [project] section; skipping", file=sys.stderr)
    sys.exit(0)

major, minor, patch = map(int, match.groups())
new_patch = patch + 1
new_version = f"{major}.{minor}.{new_patch}"

# Replace only within the section to avoid unintended changes
new_section_text = version_re.sub(f"version = \"{new_version}\"", section_text, count=1)

if new_section_text == section_text:
    print("No changes made (version unchanged)")
    sys.exit(0)

new_text = text[:project_start] + new_section_text + (text[next_section:] if next_section != -1 else "")
PYPROJECT.write_text(new_text, encoding="utf-8")
print(f"Bumped version: {major}.{minor}.{patch} -> {new_version}")