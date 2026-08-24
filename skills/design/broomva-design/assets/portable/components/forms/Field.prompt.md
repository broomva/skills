Form row wrapper with a sentence-case label, one control, and one hint or error line.

```jsx
<Field label="Budget" hint="Maximum monthly amount">
  <Input defaultValue="$400" />
</Field>
```

`error` replaces the hint in danger color. Keep the control border semantic rather than turning the whole field red.

Pass exactly one control. `Field` gives it a stable ID, associates the visible label, merges hint or error IDs into `aria-describedby`, and sets `aria-invalid` when `error` is present. A child control's own ID takes precedence; otherwise use `id`, `hintId`, or `errorId` only when the surrounding form already owns those identifiers.
