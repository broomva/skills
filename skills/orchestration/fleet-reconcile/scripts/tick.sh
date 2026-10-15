#!/bin/bash
# fleet-reconcile is now the fleet skill (BRO-3122). Deprecated alias for one
# release: forwards every argument to ../../fleet/scripts/tick.sh.
dir=$(CDPATH='' cd -P -- "$(dirname -- "$0")/../../fleet/scripts" && pwd) || exit 70
echo "fleet-reconcile: deprecated, renamed to fleet; use $dir/tick.sh" >&2
exec /bin/bash "$dir/tick.sh" "$@"
