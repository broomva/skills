Modal dialog on earned glass over a blue-black scrim. Use for confirmations and focused forms. Escape and safe scrim clicks close it.

```jsx
<Dialog open title="Remove this payment method?" onClose={close}
  actions={<><Button variant="ghost">Cancel</Button><Button>Remove</Button></>}>
  Future renewals will use your remaining default payment method.
</Dialog>
```

`ConfirmDialog` provides the common cancel plus confirm shape. The implementation moves focus inside, traps Tab and Shift+Tab, then returns focus to the trigger. Pass `ariaLabel` whenever `title` is omitted.
