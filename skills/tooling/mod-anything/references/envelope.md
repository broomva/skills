# The envelope: what this skill will and will not do, and why

This is a planning summary, not legal advice. It covers US and EU sources only; check the law
where the user is.

## The rules and their reasons

| Rule | Why |
|---|---|
| The user must have the right to modify the target | The owner of a device or a game copy can change it for their own use. A licensed app (SaaS client, firmware) is governed by its terms: if they prohibit client modification, the app is out of scope. Vencord's own FAQ says "Client modifications are against Discord's Terms of Service." |
| Never defeat a protection | Integrity checks, anti-cheat, anti-automation, licence and DRM checks, and access controls on others' data exist to say no. The law's interoperability exceptions are narrow (below), and this skill's rule is stricter: if a route needs a protection defeated, pick another route. |
| Stay within the user's own account and data on online services | A client mod that talks to a live service acts on other people's infrastructure. Act only on the user's own account and data, ask before sending it writes or replayed requests even there, and publish nothing that automates, scrapes or writes to a live service. A cosmetic mod that only changes what the user sees is fine, if the terms allow it. |
| Bring your own files | Studying a program to interoperate is protected far more than shipping its bytes. Ship code, patches and converters that run on the user's own install. |
| Ask before touching the user's real environment | Driving input takes over the user's machine. Installing into a real profile can lose state. Labs (a separate profile, a copy of a vault or a save) need no ask, but a lab that raises system UI on the user's screen (a keychain prompt, a permission dialog) is touching the user's environment: stop it by exact PID and fix the lab. A copied browser profile is never a lab. |
| Back up first; kill by PID | A mod that corrupts a profile or kills the wrong process costs more than the mod is worth. Never `pkill -f`: the pattern can match the agent's own shell. |
| Ask before connecting to a device, pairing with it, or sending it anything but a documented read | Undocumented commands, probes and replayed captures can actuate hardware (a motor, a relay, a heater, a lock) or brick it, and pairing can evict the vendor's app. Reading advertisements needs no ask. A device that controls something physical is the user's call each time. Recordings of its traffic stay private: they can carry addresses, serials and keys. A device that obeys a replayed command with no pairing or authentication is a disclosure finding: the user's own mod may still drive it locally, but nothing describing the protocol ships until disclosure clears. |
| Ask before using the user's real signed-in session | Testing a userscript or automation in the user's own browser profile or running app acts as them on live services. A website lab is a fresh profile the user logs into. A copied profile carries their cookies and saved logins, so it is never a lab, and cookies are never read out of the real one. |

## The legal line, briefly

| Source | What it says | What it means here |
|---|---|---|
| Sega v. Accolade (9th Cir. 1992) | Disassembly for a legitimate reason, when there is no other way to reach the functional elements, is fair use. | Studying to interoperate is protected. |
| Sony v. Connectix (9th Cir. 2000) | Intermediate copies made while reverse engineering were fair use; the shipped product held none of the original code. | The product must carry none of the original. |
| Google v. Oracle (US 2021) | Reusing the Java SE declaring code was fair use. | Reimplementing an interface is defensible; it is not a blanket licence. |
| EU Directive 2009/24/EC, Art. 6 | Decompiling for interoperability is allowed when indispensable. The information may not be used to develop a program substantially similar in its expression. | Byte-matching someone else's program is the most exposed form of reverse engineering. |
| DMCA §1201(f) | Circumvention, and sharing the means, is allowed solely for interoperability. Other exemptions are narrow and category by category. | Our rule (never defeat a protection) is stricter. |
| EU Data Act (from 12 Sep 2025) | Users can get their connected product's data, but may not use it to build a competing product. | "Bring your own data" has a footing for devices in the EU. |
| EU repair directive 2024/1799 (from 31 Jul 2026) | Bars parts or software that block repair, for the goods listed in its Annex II. | Supports repair-framed work on those goods only; it grants no right to change features. |

## Disclosure

Reverse engineering finds vulnerabilities, in apps (an open debugging port, a reachable
command shell) and in devices (a signature check that can be poked off). When you find one:

1. Keep working privately. Journals, private notes and private knowledge-graph commits stay
   unblocked, because the method depends on them.
2. Nothing describing the flaw leaves the private repo until three things are true: the vendor
   has been contacted, the disclosure date agreed with them has passed (or they shipped a
   fix), and the owner has signed off. That covers a public field note, a pull request to a
   public knowledge base, a post or a release. A vendor that never answers gets a deadline the
   owner sets.
3. A published field note describes the mod, not the exploit. Defeating the protection was
   never in scope.
4. The note's `Disclosure:` line records the state: `none found`, `embargoed (...)` while the
   embargo holds, and `cleared YYYY-MM-DD (...)` once step 2's conditions are met.
   `modlog.py lint-note` refuses `embargoed`, a `cleared` date in the future, and any line
   that mentions an embargo without being `cleared`, so the documented publish flow (SKILL.md
   steps 8-9) stops there until step 2's conditions are met.
5. The user contacts the vendor. The agent drafts the report; sending it reaches outside the
   user's machine, which is the user's call (SKILL.md §Rules, ask before).

One public write-up shows the pattern. It reverse-engineered five peripherals and found a
microphone command shell and a light whose signature check could be disabled, and its author
writes "I've shared everything in this post with the vendors involved."
