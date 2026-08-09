Floating glass notice with a status dot and one optional action. Use it for quiet confirmations and background-event notices.

```jsx
<Toast status="success" title="Saved" meta="Your changes are available"
  action="Open" onAction={openItem} onDismiss={dismissToast} />
```

Stack notices bottom-right with the newest last. The caller owns timing.
