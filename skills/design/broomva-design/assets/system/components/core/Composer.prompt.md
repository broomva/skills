The chat composer — the one place glass and dramatic depth are allowed. Use at the bottom of any chat surface.

```jsx
<Composer onSend={(t) => addMessage(t)} leading={<IconButton label="Attach"><PlusIcon /></IconButton>} />
```

Requires styles.css for the .bv-glass-composer halo. Keep placeholder as "Message <agent>".
