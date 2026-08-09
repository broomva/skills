Form row wrapper with a sentence-case label, one control, and one hint or error line.

```jsx
<Field label="Budget" hint="Maximum monthly amount">
  <Input defaultValue="$400" />
</Field>
```

`error` replaces the hint in danger color. Keep the control border semantic rather than turning the whole field red.
