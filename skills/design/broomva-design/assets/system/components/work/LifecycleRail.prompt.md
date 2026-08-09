The lifecycle rail — horizontal stage tracker for the work-item inspector. Position evidence, never a progress bar.

```jsx
<LifecycleRail stages={[
  { name: "proposed", state: "passed" },
  { name: "queued",   state: "passed" },
  { name: "running",  state: "current", note: "since 09:14" },
  { name: "review" },
  { name: "done" },
]} />
```

`state: "warn"` marks a stuck stage in warning color.
