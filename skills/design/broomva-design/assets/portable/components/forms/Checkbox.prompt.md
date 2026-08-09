18px checkbox with an ink fill when checked. Use it for multi-choice options and consent rows.

```jsx
<Checkbox defaultChecked onChange={(value) => setEmailUpdates(value)}>
  Email me product updates
</Checkbox>
```

Control it with `checked` when the parent owns state. The visible label is the children and uses sentence case.
