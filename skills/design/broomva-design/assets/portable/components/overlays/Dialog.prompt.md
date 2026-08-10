Modal dialog on earned glass over a blue-black scrim. Use for confirmations and focused forms. Escape and safe scrim clicks close it.

```jsx
<Dialog open title="Remove this payment method?" onClose={close}
  actions={<><Button variant="ghost">Cancel</Button><Button>Remove</Button></>}>
  Future renewals will use your remaining default payment method.
</Dialog>
```

`ConfirmDialog` provides the common cancel plus confirm shape and requires a title. The implementation moves focus inside, traps Tab and Shift+Tab, then returns focus to the trigger. `Dialog` requires either a non-empty visible `title` or an `ariaLabel` and throws before rendering an unnamed open modal. When migrating, add a concise `ariaLabel` only if no visible heading is appropriate.
