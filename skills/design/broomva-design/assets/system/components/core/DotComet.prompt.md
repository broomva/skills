The tidepool dot — the running signal at dot scale: the Undertow's blue→ice weather drifting inside the 15px circle. Use it wherever a status dot would mark running work: list rows, badges, the status line of a card, and the bench in the chrome (presence, not a button).

```jsx
<DotComet />
<DotComet size={13} />
```

Renders `.bv-dot-live`. Blue → ice only; stops under reduced motion. Don't use it for any state except running/live. For cards, pair with `<Card running>`.
