Popover menu on earned glass for contextual actions. Position it relative to its trigger and preserve keyboard navigation.

```jsx
<Menu ariaLabel="Document actions" onEscape={closeMenu}>
  <MenuItem kbd="⌘O">Open document</MenuItem>
  <MenuItem>Make a copy</MenuItem>
  <MenuDivider />
  <MenuItem danger>Delete</MenuItem>
</Menu>
```

The first enabled item receives focus. Arrow keys, Home, and End move between enabled items; Escape calls `onEscape`. Use the danger treatment only for destructive actions and keep each label explicit.
