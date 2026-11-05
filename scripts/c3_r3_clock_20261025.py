#!/usr/bin/env python3
"""Hard clock for R3 downstream work. Returns 0 if new work may start, 3 if not."""
import datetime, sys
NOW = datetime.datetime.now()
CHECKS = [('admissions', '2026-10-25 03:00:00'), ('quiesce', '2026-10-25 03:15:00')]
phase = None
for name, s in CHECKS:
    if NOW >= datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S'):
        phase = name
print(f'{NOW:%Y-%m-%d %H:%M:%S %Z} {phase or "open"}')
sys.exit(3 if phase else 0)
