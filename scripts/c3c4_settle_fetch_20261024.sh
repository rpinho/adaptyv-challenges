#!/bin/zsh
# Read-only settle watcher: when an app stops with complete artifacts, run its
# read-only fetch locally. Never launches/stops compute, never touches CSVs.
cd /Users/ricardo/dev/adaptyv-c4 || exit 1
MODAL=./.venv-modal/bin/modal
LOG=results/settle_fetch_20261024.log
C4=ap-x8qUMEomla0Dhcf7x8Zzb8
C3=ap-yoYiuB1uFgZY7n807wWB8g
c4_done=0; c3_done=0
state_of() {
  $MODAL app list --json 2>/dev/null | python3 -c "
import json,sys
a={x['app_id']:x for x in json.load(sys.stdin)}
print((a.get('$1') or {}).get('state','not_listed'))"
}
for i in {1..240}; do
  if (( ! c4_done )); then
    s=$(state_of $C4)
    if [[ "$s" == stopped* ]]; then
      echo "$(date '+%F %T') C4 stopped -> fetch" >> $LOG
      $MODAL run modal_boltz2_apical.py::fetch >> $LOG 2>&1 && c4_done=1 \
        || echo "$(date '+%F %T') C4 fetch failed; will retry" >> $LOG
    fi
  fi
  if (( ! c3_done )); then
    s=$(state_of $C3)
    if [[ "$s" == stopped* ]]; then
      echo "$(date '+%F %T') C3 stopped -> fetch" >> $LOG
      $MODAL run modal_af2m_c3_complex.py::fetch >> $LOG 2>&1 && c3_done=1 \
        || echo "$(date '+%F %T') C3 fetch failed; will retry" >> $LOG
    fi
  fi
  (( c4_done && c3_done )) && { echo "$(date '+%F %T') ALL_SETTLED" >> $LOG; exit 0; }
  sleep 180
done
echo "$(date '+%F %T') watcher timeout" >> $LOG
