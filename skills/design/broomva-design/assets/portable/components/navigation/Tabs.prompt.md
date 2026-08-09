Quiet frost-pill tab strip for switching related views inside a product surface. The active tab uses Frosted selection; do not add underlines.

```jsx
<Tabs tabs={["Overview", "Details", "History"]} defaultActive={0} onChange={setView} />
```

Tabs also accept `{ label, icon, count }`. Keep labels short and preserve standard tab keyboard behavior.
