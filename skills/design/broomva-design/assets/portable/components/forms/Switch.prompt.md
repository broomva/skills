Compact toggle, Resonant AI Blue when on. Use for immediate binary settings that do not require a separate save action.

```jsx
<span id="email-alerts-label">Email alerts</span>
<Switch aria-labelledby="email-alerts-label" defaultChecked
  onChange={(enabled) => setEnabled(enabled)} />
```

The thumb slides in 150ms without bounce. Keep a persistent text label outside the control and connect it with `aria-labelledby` or wrap the switch in `Field`; use `aria-label` only when visible text is unavailable. Development builds warn when neither an associated label nor an ARIA name is present.
