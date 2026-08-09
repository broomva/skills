Plain-voice work state (dot + label) — use wherever a work item's state shows. Canon words only: Queued, Running, Stuck, Needs you, Done, Standing.

```jsx
<WorkState state="running" />          // tidepool dot, live
<WorkState state="needs-you" variant="chip" />
```

Never render system enums (Todo, InProgress…) in UI. "Needs you" owns accent-blue — it is a gate, not a failure.
