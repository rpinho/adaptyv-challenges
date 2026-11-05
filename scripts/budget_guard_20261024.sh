#!/bin/zsh
# Executes Kimi decision record item 5 (budget ceiling). Mechanical only.
# Stops the C3 app if BILLED cost >= $190, or if a 15-min projection exceeds $200.
cd /Users/ricardo/dev/adaptyv-c4 || exit 1
MODAL=./.venv-modal/bin/modal
APP=ap-yoYiuB1uFgZY7n807wWB8g
LOG=results/budget_guard_20261024.log
last=""
for i in {1..400}; do
  billed=$($MODAL billing summary 2>/dev/null | awk -F'\\$' '/Billed Cost/ {print $2}' | tr -d ' ')
  state=$($MODAL app list --json 2>/dev/null | python3 -c "
import json,sys
a={x['app_id']:x for x in json.load(sys.stdin)}
print((a.get('$APP') or {}).get('state','not_listed'))")
  echo "$(date '+%F %T') billed=$billed c3=$state" >> $LOG
  if [[ "$state" == stopped* || "$state" == "not_listed" ]]; then
    echo "$(date '+%F %T') C3 no longer running; guard exiting" >> $LOG; exit 0
  fi
  if [[ -n "$billed" ]]; then
    if python3 -c "import sys;b=float('$billed');prev=float('${last:-$billed}');proj=b+(b-prev)*5;sys.exit(0 if (b>=190 or proj>200) else 1)"; then
      echo "$(date '+%F %T') STOPPING C3: billed=$billed (threshold 190 / projection>200)" >> $LOG
      $MODAL app stop --yes $APP >> $LOG 2>&1
      echo "$(date '+%F %T') stop issued; final billed=$($MODAL billing summary 2>/dev/null | awk -F'\\$' '/Billed Cost/ {print \$2}')" >> $LOG
      exit 0
    fi
    last=$billed
  fi
  sleep 180
done
exit 0
