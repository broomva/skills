# falling-body

The smallest package the audit passes. A body falls from rest in vacuum.

| Quantity | Checked against | Agreement |
|---|---|---|
| Fall time from 1, 5, 20 and 100 m | The stored table | 0.001 s |
| Fall time from 5 m | Stepping the motion forward in its own test | 0.1% |
| Impact speed | Energy conservation | 1e-9 |
| Zero height | Takes no time | exact |

From 5 m the fall takes 1.010 s and the body lands at 9.90 m/s.

Not compared with a measurement: none of these numbers was timed on a real drop.

Left out: air drag and buoyancy. g is taken as the standard value everywhere.

```bash
python3 ../../../scripts/sim_audit.py . --run-report --run-mutations --strict
```
