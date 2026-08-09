The look — the gate's run card: what changed · what it decided · what it asks, with Approve / Send back as the only controls.

```jsx
<RunCard
  state="needs-you" agent="claude" duration="3h 40m"
  title="Ported the billing reducer to event sourcing"
  decided="replay beats snapshot; kept event ids stable"
  asks="approve the schema migration before it touches prod data"
  receipts={[{ label: "branch", code: "run/7c2f" }, { label: "diff", code: "+214 −38" }]}
  onApprove={…} onSendBack={…}
/>
```

Wrap in `<Undertow>` while still running. Duration reads "3h 40m unsupervised" — the score that matters.
