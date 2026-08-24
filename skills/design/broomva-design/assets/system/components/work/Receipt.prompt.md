Receipt block — evidence over claims. Use instead of progress bars: branch, diffstat, judge verdict.

```jsx
<Receipt rows={[
  { label: "branch", code: "run/7c2f" },
  { label: "diff",   code: "+214 −38 · 6 files" },
  { label: "judge",  code: "pass · 9/9 checks" },
]} />
```

Machine facts go in `code` (mono); rows accept a 13px `icon`.
