# Reproductions

Timing-dependent demonstrations that are **not** part of the default suite.

A race that only manifests under a wide read/write window makes a poor CI test:
it is slow, and it is flaky in the direction that matters least (a pass proves
nothing on a fast machine). These scripts exist so the claims made in
`p9.py`'s docstrings have a runnable artifact behind them rather than being
prose nobody can check.

## `lock_necessity.py`

Shows that `append_state_event`'s guarded path needs its read and its append
under **one** lock acquisition, not two.

A superseding writer races a guarded folder, barrier-synchronized so both are
fully warm before either proceeds. The guarded read parses the whole log, so a
large log widens the window the lock closes.

```
python3 tests/reproductions/lock_necessity.py <scripts-dir> <state-dir> <rows>
```

Measured at 60000 rows, 3 runs each:

| build | `w2` buried by a stale fold |
|---|---|
| shipped (lock held across read+append) | 0/3 |
| lock removed from the CAS | 3/3 |

Exit status is 1 when the live watcher was buried, so it is usable as a gate
if you want to run it deliberately.
