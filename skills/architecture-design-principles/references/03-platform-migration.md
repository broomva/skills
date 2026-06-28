# Platform Migration: Forcing Functions

## The core problem

You've built a better platform. You want every team to move to it. But
teams are busy shipping their own work, and migrating doesn't show up on
*their* OKRs.

**Result**: voluntary migration is asymptotic — the last 20% never moves.
You end up running both platforms forever, which doubles operational cost
and means new platform features must be replicated in the old platform.

## The talk's solution: remove the alternative

> "They forced a switch to where you could no longer expose your service
> publicly through their [old] load balancer, which is too basic, and you
> had to go through our centralized load balancing infrastructure and to
> explicitly configure it as a way of signaling your intention for that
> service to be publicly accessible."

The mechanism: the old basic load balancer **kept working**, but it stopped
accepting *public traffic*. You could still use it internally. The forcing
function was specific (public exposure) rather than total (delete the old
thing).

**Why specificity matters**: a total deprecation is a cliff. A specific
forcing function is a wall — teams can choose when to climb it, but
eventually they must.

## The migration ladder (general shape)

1. **Build the new thing alongside the old.** Both run. New teams adopt
   new platform. Old teams keep using old platform. Voluntary.
2. **Add a clear feature gap.** New platform gets a feature old platform
   can't have (in this case: centralized auth, rate limiting, edge
   features). Now there's a *reason* for old teams to move.
3. **Migrate the easy ones.** Use platform team time to migrate
   willing-but-busy teams. Make the migration script idempotent.
4. **Migrate the strategic ones.** Identify which migrations create the
   strongest forcing function for the rest. At Atlassian: Jira, Confluence,
   Bitbucket, Status Page. When the top products are on the new platform,
   "this is unsupported" becomes credible.
5. **Forcing function.** Remove the path of least resistance from the old
   platform for new use cases (here: new public services must use new
   platform).
6. **Deprecation date.** Announce a hard date. By this time the cost of
   not migrating exceeds the cost of migrating.

**Critical sequencing**: steps 1-4 must be done *before* step 5. If you
flip the forcing function while the new platform is missing features or
poorly tested, you create a riot.

## The cost calculus (why migrations are slow)

```
Migration cost per team =
    (engineer-days to migrate)
  × (number of services)
  × (regression risk factor)
  − (value of new features over time horizon)
```

This is why migrations stall: each team independently solves this
equation and sets "migrate" priority based on their estimated cost. For
most teams, even when net value is positive, the *upfront* cost loses to
"ship the next feature".

**The forcing function changes the equation**: when "don't migrate"
becomes "no public traffic", the cost of not migrating becomes infinite.
Suddenly even pessimistic migration estimates are obviously cheaper.

## Migration cost reduction tactics

The talk implies these but doesn't name them all:

- **Script the migration.** Don't ask teams to read docs and execute steps
  — give them a one-command tool that does it.
- **Make the new config compatible with the old**. The OSB pattern helped
  here: the dev contract (JSON in version control) was simpler than the
  old basic LB config, not more complex. Migration was "delete old config,
  write small JSON".
- **Take ownership of the migration**. Platform team does the migration
  *to* the team's repo (PR'd into their codebase), not the team migrating
  themselves.
- **Migrate the hardest service first as a credibility move**. If you can
  migrate Jira (the hardest), every other team's "but my service is
  special" becomes less believable.

## Anti-patterns

### Big-bang migration

"Everyone moves on March 1st." Doesn't work for orgs >10 teams. Too many
conflicts, no time for the platform team to react to issues, no escape
valve.

### Voluntary migration with no end state

"Please migrate when you can." Forever-state. The platform team operates
both platforms in perpetuity, and the new platform never gets the
investment it needs.

### Forcing function before parity

"You can no longer use the old platform" but the new one is missing
features. Teams revolt. Platform team's credibility is destroyed and the
next forcing function attempt fails too.

### Forcing function without notice

"Today, we deprecated the old API." A surprise forcing function gets one
emergency Slack channel and a year of trust deficit.

## The implicit cultural prerequisite

A forcing function can only work if the platform team has organizational
backing to enforce it. The talk doesn't dwell on this but it's there
between the lines: "we could enforce that through the platform" is a
sentence that only an org-supported platform team can say.

If your platform team is purely service-oriented (no enforcement
authority), forced migration becomes pleading. You'll need either:

1. **Executive backing** to add the forcing function, or
2. **A natural forcing function** — e.g., a security incident that forces
   everyone off the old thing, or a vendor deprecation that does it for
   you.

Plan around whichever you have. Don't assume you have authority you don't.

## The migration as a service

At a certain scale, migrations become a permanent function of the
platform team. New platforms will be introduced; old ones will be
deprecated. The migration ladder becomes a playbook the platform team
runs every 18-24 months.

Treat it as a service:
- Catalog of currently-supported platforms with deprecation dates
- Migration scripts maintained for each transition
- Time-bounded support windows for each old version
- Forcing-function language consistent across migrations

The Atlassian story implies this maturity — moving Jira/Confluence/
Bitbucket/Status Page through migrations is muscle memory at that point,
not a one-off project.
