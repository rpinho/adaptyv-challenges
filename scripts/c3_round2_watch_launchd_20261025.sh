#!/bin/bash
# One iteration: pull round-2 pod artifacts and re-run the independent verifier.
# Installed as a launchd StartInterval job so it survives shell exit / session teardown.
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin
cd /Users/ricardo/dev/adaptyv-c4 || exit 1
exec ./scripts/c3_round2_pull_verify_20261025.sh
