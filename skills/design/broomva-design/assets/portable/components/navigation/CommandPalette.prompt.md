Command palette combobox on earned glass. Use for keyboard-driven actions or navigation when the product has enough commands to justify search.

```jsx
<CommandPalette
  label="Document actions" query={query} onQuery={setQuery} activeId="new-document"
  groups={[{ label: "Actions", items: [
    { id: "new-document", title: "New document", meta: "Create a blank draft", kbd: "⌘N" },
  ]}]}
  onPick={(item) => choose(item)}
/>
```

Arrow keys change the active option, Enter picks it, and Escape calls `onEscape`. Wrap the modal form in a blue-black scrim and return focus to its trigger on close.
