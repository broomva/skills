---------------------------- MODULE P9Lifecycle ----------------------------
(***************************************************************************)
(* The P20 verdict gate of p9's merge predicate, as a state machine.       *)
(*                                                                         *)
(* Code modelled: skills/orchestration/p9/scripts/p9.py, _p20_verdict()    *)
(* A PASS verdict names a commit. At the head it passes. At an older       *)
(* commit it carries forward only if no later commit touches a reviewed    *)
(* file or a current PR file ("Anything else is new, unreviewed code").    *)
(*                                                                         *)
(* The property is about CONTENT, not about the rule restated: whatever    *)
(* merges is exactly what the reviewer read, and a generated file in the   *)
(* PR is generator output, never hand-written content.                     *)
(*                                                                         *)
(* Gate variants (constant Mode):                                          *)
(*   "p9"           the rule as implemented                                *)
(*   "anyPass"      any PASS on the PR clears it (a broken variant)        *)
(*   "reviewedOnly" only reviewed files void it; files added to the PR     *)
(*                  after review do not (a broken variant)                 *)
(* ExemptDerived: the change proposed in BRO-1966 — later commits that     *)
(*   change only generated files do not void the verdict.                  *)
(* DerivedCI: CI regenerates each generated file and requires equality.    *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS Files,          \* files a PR can touch
          Derived,        \* generated files, a subset of Files
          MaxCommits,     \* bound on commits, keeps the state space finite
          Mode,           \* "p9" | "anyPass" | "reviewedOnly"
          ExemptDerived,  \* BOOLEAN
          DerivedCI       \* BOOLEAN

Authored == Files \ Derived

VARIABLES av,       \* [Authored -> Nat]: content version of each authored file at the head
          dv,       \* [Derived -> record]: what each generated file holds
          pr,       \* files the PR changes relative to its base
          hist,     \* Seq of SUBSET Files: what each commit changed
          verdict,  \* the latest PASS, or a record with none = TRUE
          merged,   \* BOOLEAN
          baseAfterVerdict  \* a base update landed after the verdict (for the reachability check)

vars == <<av, dv, pr, hist, verdict, merged, baseAfterVerdict>>

Generated(a) == [src |-> a, hand |-> FALSE]          \* generator output of authored content a
NoVerdict == [none |-> TRUE, sha |-> 0, reviewed |-> {}, av |-> [f \in Authored |-> 0],
              dv |-> [d \in Derived |-> Generated([f \in Authored |-> 0])]]

Tip == Len(hist)   \* the head commit's index (Head is taken by Sequences)
Delta(n) == UNION {hist[i] : i \in (n + 1)..Tip}
Exempt == IF ExemptDerived THEN Derived ELSE {}
DerivedOK == \A d \in Derived : dv[d] = Generated(av)

Gate ==
    /\ ~verdict.none
    /\ CASE Mode = "anyPass"      -> TRUE
         [] Mode = "reviewedOnly" -> \/ verdict.sha = Tip
                                     \/ (Delta(verdict.sha) \cap verdict.reviewed) \subseteq Exempt
         [] Mode = "p9"           -> \/ verdict.sha = Tip
                                     \/ (Delta(verdict.sha) \cap (verdict.reviewed \cup pr)) \subseteq Exempt
    \* A derived exemption is only claimed with the CI check that makes it safe in force.
    /\ (ExemptDerived /\ DerivedCI) => DerivedOK

Init ==
    /\ av = [f \in Authored |-> 0]
    /\ dv = [d \in Derived |-> Generated([f \in Authored |-> 0])]
    /\ pr = {}
    /\ hist = << >>
    /\ verdict = NoVerdict
    /\ merged = FALSE
    /\ baseAfterVerdict = FALSE

\* The author edits a file; generated files are regenerated in the same commit.
Author(f) ==
    /\ ~merged /\ Tip < MaxCommits
    /\ av' = [av EXCEPT ![f] = @ + 1]
    /\ dv' = [d \in Derived |-> Generated(av')]
    /\ pr' = pr \cup {f} \cup Derived
    /\ hist' = Append(hist, {f} \cup Derived)
    /\ UNCHANGED <<verdict, merged, baseAfterVerdict>>

\* The base branch changed f and the PR merged it in; generated files are regenerated.
\* If the PR also changed f, the merged f is new content (it stays a PR file).
BaseUpdate(f) ==
    /\ ~merged /\ Tip < MaxCommits
    /\ av' = [av EXCEPT ![f] = @ + 1]
    /\ dv' = [d \in Derived |-> Generated(av')]
    /\ pr' = pr \cup (IF f \in pr THEN {f} ELSE {}) \cup (IF pr = {} THEN {} ELSE Derived)
    /\ hist' = Append(hist, {f} \cup Derived)
    /\ baseAfterVerdict' = (~verdict.none \/ baseAfterVerdict)
    /\ UNCHANGED <<verdict, merged>>

\* Someone edits a generated file by hand (what the CI derived check exists to catch).
HandEdit(d) ==
    /\ ~merged /\ Tip < MaxCommits
    /\ dv' = [dv EXCEPT ![d] = [src |-> av, hand |-> TRUE]]
    /\ pr' = pr \cup {d}
    /\ hist' = Append(hist, {d})
    /\ UNCHANGED <<av, verdict, merged, baseAfterVerdict>>

\* A reviewer reads the head and records PASS for it.
Review ==
    /\ ~merged /\ pr # {}
    /\ verdict' = [none |-> FALSE, sha |-> Tip, reviewed |-> pr, av |-> av, dv |-> dv]
    /\ baseAfterVerdict' = FALSE
    /\ UNCHANGED <<av, dv, pr, hist, merged>>

\* CI must also pass: with DerivedCI, a generated file must equal regeneration.
Merge ==
    /\ ~merged /\ Gate
    /\ DerivedCI => DerivedOK
    /\ merged' = TRUE
    /\ UNCHANGED <<av, dv, pr, hist, verdict, baseAfterVerdict>>

Next ==
    \/ \E f \in Authored : Author(f) \/ BaseUpdate(f)
    \/ \E d \in Derived : HandEdit(d)
    \/ Review
    \/ Merge

Spec == Init /\ [][Next]_vars

TypeOK ==
    /\ merged \in BOOLEAN
    /\ pr \subseteq Files
    /\ Tip <= MaxCommits

(* SAFETY: what merges is what was reviewed. Every authored PR file holds the  *)
(* content the reviewer read, and every generated PR file is generator output *)
(* of the merged authored content (so it carries nothing the reviewer and the *)
(* base did not already vouch for).                                           *)
SafeMerge ==
    merged =>
        /\ \A f \in pr \cap Authored : av[f] = verdict.av[f]
        /\ \A d \in pr \cap Derived : dv[d] = Generated(av)

(* REACHABILITY probe, not a requirement: "a PR never merges after a base     *)
(* update without a new review". The current rule keeps it true, which is the *)
(* friction of ws#1296; the derived exemption is expected to VIOLATE it, which *)
(* shows the exemption actually lets such a PR merge.                         *)
NoMergeAfterBaseUpdate == ~(merged /\ baseAfterVerdict)
=============================================================================
