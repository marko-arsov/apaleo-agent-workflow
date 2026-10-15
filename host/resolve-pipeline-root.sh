#!/usr/bin/env bash
set -euo pipefail
python3 - "${1:-$PWD}" <<'PYROOT'
from pathlib import Path
import sys
start = Path(sys.argv[1]).expanduser().resolve()
if start.is_file():
    start = start.parent
for root in [start, *start.parents]:
    marker = root / 'AGENTS.md'
    if (marker.is_file() and '# Apaleo workspace' in marker.read_text()
            and all((root / name).is_dir() for name in ('.claude/skills', 'apaleo', 'development'))):
        print('apaleo\t' + str(root))
        raise SystemExit(0)
raise SystemExit(1)
PYROOT
