Modal dialog on earned glass over the blue-black scrim — use for confirmations and focused forms. Esc and scrim-click close.

```jsx
<Dialog open title="Send this run back?" onClose={close}
  actions={<><Button variant="ghost">Cancel</Button><Button>Send back</Button></>}>
  The agent keeps its branch and retries with your note.
</Dialog>
```

`ConfirmDialog` is the ready-made confirm shape (ghost cancel + primary confirm).
