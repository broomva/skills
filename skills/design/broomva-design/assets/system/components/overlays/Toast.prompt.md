Floating glass notice with a status dot and one optional action — use for quiet confirmations and background-event notices. Never celebratory.

```jsx
<Toast status="success" title="Run approved" meta="claude continues on run/7c2f"
  action="Open" onAction={…} onDismiss={…} />
```

Stack them bottom-right, newest last; caller owns timing.
