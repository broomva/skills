Single-line text input for forms, search, and settings.

```jsx
<Field label="Search catalog">
  <Input type="search" placeholder="Name or SKU" />
</Field>
```

The control is 36px tall with a restrained radius and a visible global focus ring. Use `Field` for persistent labels. When an input must stand alone, provide `aria-label` or `aria-labelledby`. A placeholder is never the accessible label.
