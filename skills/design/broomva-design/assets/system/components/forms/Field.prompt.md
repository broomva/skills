Form row wrapper: sentence-case label, the control, one hint or error line — use to compose any labeled form.

```jsx
<Field label="Budget" hint="Hours before the loop must check in">
  <Input defaultValue="4h" />
</Field>
```

`error` replaces the hint in danger color; the control itself never turns red.
