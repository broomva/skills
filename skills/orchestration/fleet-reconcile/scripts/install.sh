#!/bin/bash
# fleet-reconcile is now the fleet skill (BRO-3122). Deprecated alias for one
# release: forwards every argument to ../../fleet/scripts/install.sh.
dir=$(CDPATH='' cd -P -- "$(dirname -- "$0")/../../fleet/scripts" && pwd) || exit 70
echo "fleet-reconcile: deprecated, renamed to fleet; use $dir/install.sh" >&2
exec /bin/bash "$dir/install.sh" "$@"
