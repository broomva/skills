The command palette combobox on earned glass — use for ⌘K anywhere in an app shell. Static: pass filtered groups; wrap in a fixed blue-black scrim for the overlay form.

```jsx
<CommandPalette
  query={q} onQuery={setQ} activeId="new-mission"
  groups={[{ label: "Actions", items: [
    { id: "new-mission", title: "New mission", meta: "Start a work item", kbd: "⌘N" },
  ]}]}
  onPick={(item) => …}
/>
```
