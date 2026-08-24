Matte content card — work items, board cards, settings groups, integration rows. Never glass, never pill-radius.

```jsx
<Card interactive>…</Card>
<Card running>…</Card>
```

`interactive` adds the blue-tinted hover lift; `running` wraps the card in the Undertow — the contained halo that is THE running signal (the card itself stays matte; the border comet is retired). Pair with `<DotComet />` on the status row. Requires `styles.css`.
