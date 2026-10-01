#!/usr/bin/env python3
"""Mutation check for the System 1 gate, System 2 and the E1/E3 evals.

Each mutant breaks one protection in a scratch copy of the skill and runs the
test that pins it; that test must fail. The first two are the brief's: a gate
that injects whatever the floor says (always-inject) and a gate that looks up
the wrong keys (wrong-key). E1 must catch both on the synthetic fixture
(test_s1_e1_synthetic.py): separation on its test split fails. Exit 1 on any
mutant that survives, whose anchor is gone (STALE), or whose run errored. The
owner's real snapshot is private and plays no part here.

    python3 tests/mutation_check_s1.py
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

SKILL = pathlib.Path(__file__).resolve().parents[1]
S1, S2, KEYS = "scripts/ctx_s1.py", "scripts/ctx_s2.py", "scripts/ctx_keys.py"
REPLAY, EVAL, HOOK, SH = "scripts/ctx_s1_replay.py", "scripts/ctx_s1_eval.py", "scripts/ctx_s1_hook.py", \
    "scripts/ctx-s1-hook.sh"
T = "tests/"
G, F, E, C = T + "test_s1_gate.py::", T + "test_s1_failopen.py::", T + "test_s1_eval.py::", T + "test_s2_cache.py::"
SYN = T + "test_s1_e1_synthetic.py"
BND = T + "test_s1_boundaries.py::"

MUTANTS = [
    # --- the brief's two: E1 must catch them
    ("always-inject (floor ignored)", S1,
     "        pool = [(iid, s) for iid, s in pool if s >= float(floor)]\n",
     "        pool = list(pool)\n",
     [SYN]),
    ("wrong-key (lookup on a corrupted key)", S1,
     "                for idx, s, tc in reader.postings(k):",
     "                for idx, s, tc in reader.postings(k[:-1]):",
     [SYN]),
    ("wrong-key (prompt words from the wrong text)", S1,
     '        tk["w"] = ["w:" + w for w in K.unique(K.terms(text))[:PROMPT_TERMS]]',
     '        tk["w"] = ["w:" + w for w in K.unique(K.terms(text[::-1]))[:PROMPT_TERMS]]',
     [SYN]),
    # --- the gate's own protections
    ("no floor means inject", S1, '            return _abstain("no-floor", **base)', "            floor = 0.0",
     [G + "test_the_shipped_parameters_abstain_on_everything"]),
    ("no dedup", S1,
     '        if stage not in ("compact", "subagent") and iid in injected:\n            continue\n', "",
     [G + "test_a_claim_is_never_injected_twice_in_a_session"]),
    ("the edited file offered for itself", S1, "        if obj & self_obj or (",
     "        if False and (", [G + "test_the_edited_file_is_never_offered_for_itself"]),
    ("reviewers get the parent's claims", S1,
     '    if stage == "subagent" and REVIEWER_RE.search(agent_type or ""):',
     "    if False:", [G + "test_subagent_gets_the_parents_claims_once_and_reviewers_get_none"]),
    ("tool stages inject inside subagents", S1, "    if stage in TOOL_STAGES and agent_id:",
     "    if False:", [G + "test_tool_stages_abstain_inside_a_subagent"]),
    ("no path-once", S1,
     '        if cfg.get("path_once") and path_key and path_key in state.get("paths", {}).get(stage, []):',
     "        if False:", [G + "test_a_path_is_injected_for_once_per_session_per_stage"]),
    ("no stage cap", S1, '        if cfg.get("per_session") and used >= int(cfg["per_session"]):',
     "        if False:", [G + "test_the_per_stage_session_cap"]),
    ("a line over budget is cut, not dropped", S1,
     '        if len(render(stage, label, lines + [line])) > budget and mode != "always":',
     "        if False:", [G + "test_the_session_cap_and_the_budget"]),
    ("already-opened files offered", S1,
     "    opened = set(state.get(\"opened\") or [])\n", "    opened = set()\n",
     [G + "test_a_file_the_session_already_opened_is_not_offered"]),
    ("prompt text in the decisions log", S1, "    for k in (\"prompt_id\", \"tool_use_id\",",
     "    rec[\"prompt\"] = data.get(\"prompt\")\n    for k in (\"prompt_id\", \"tool_use_id\",",
     [G + "test_the_decisions_log_holds_no_prompt_text_and_no_key"]),
    ("the Python flag check alone (shell flags removed)", SH,
     '[ "${CTX_S1:-0}" = 1 ] || exit 0\n', "",
     [F + "test_an_off_stage_costs_one_shell"]),
    ("a blocking session lock", S1, "            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)",
     "            fcntl.flock(fd, fcntl.LOCK_EX)", [F + "test_a_held_session_lock_abstains_quickly"]),
    # --- fail-open
    ("exceptions escape the hook", HOOK,
     "        ctx_s1.run_stage(stage, raw, deadline=_T0 + budget, emit=_emit)\n    except BaseException as exc:",
     "        ctx_s1.run_stage(stage, raw, deadline=_T0 + budget, emit=_emit)\n    except KeyError as exc:",
     [F + "test_a_decision_that_raises_injects_nothing"]),
    ("no self-deadline", HOOK,
     "        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget - (time.monotonic() - _T0)))\n", "",
     [F + "test_the_self_deadline_exits_0_and_records_a_miss"]),
    # --- System 2: exclusions and the cache
    ("person entities indexed by type", S2,
     '    if fm.get("type", "").lower() in EXCLUDED_ENTITY_TYPES:\n        return None, "person"',
     '    if False:\n        return None, "person"',
     [G + "test_person_crm_and_credential_shaped_items_are_never_candidates"]),
    ("crm path words indexed", S2, '    keys["w"] = ["w:" + w for w in K.terms(_CRM_PATH.sub(" ", word_text))]',
     '    keys["w"] = ["w:" + w for w in K.terms(word_text)]',
     [G + "test_person_crm_and_credential_shaped_items_are_never_candidates"]),
    ("credential-shaped claims indexed", S2,
     '        if not ctx.guard_ok(it["claim"]) or not ctx.guard_ok(it["source"]):', "        if False:",
     [G + "test_person_crm_and_credential_shaped_items_are_never_candidates"]),
    ("the link moves before the build is complete", S2,
     '    (tmp / "items").mkdir(mode=0o700)\n',
     '    (tmp / "items").mkdir(mode=0o700)\n    _swap_link(store, final.name)\n',
     [C + "test_a_build_that_dies_midway_leaves_the_current_cache_alone"]),
    ("a dead build leaves its debris", S2,
     "    except BaseException:\n        shutil.rmtree(str(tmp), ignore_errors=True)\n        raise",
     "    except BaseException:\n        raise",
     [C + "test_a_build_that_dies_midway_leaves_the_current_cache_alone"]),
    ("person entities indexed by directory", S2,
     '    if etype in EXCLUDED_ENTITY_TYPES:\n        return None, "person"',
     '    if False:\n        return None, "person"',
     [G + "test_person_crm_and_credential_shaped_items_are_never_candidates"]),
    ("readers follow the link per read", S1,
     '    def postings(self, key: str) -> List[List[Any]]:\n        b = K.bucket(key)',
     '    def postings(self, key: str) -> List[List[Any]]:\n        self.dir = self.dir.parent / os.readlink(str(self.dir.parent / K.CACHE_LINK))\n        self._post = {}\n        b = K.bucket(key)',
     [C + "test_a_reader_stays_on_its_build_across_a_swap"]),
    # --- E1 / E3
    ("pointed mask removed", REPLAY, "        if i in pointed_at and pointed_at[i] <= o:\n            continue\n", "",
     [E + "test_truth_is_counterfactual_and_masked"]),
    ("authored mask removed", REPLAY, "        if i in authored_at and authored_at[i] <= o:\n            continue\n", "",
     [E + "test_truth_is_counterfactual_and_masked"]),
    ("snapshot keys not hashed", REPLAY,
     '            h = ch + ":" + hmac.new(self.salt, k.encode("utf-8"), hashlib.sha256).hexdigest()[:HASH_HEX]',
     "            h = k", [E + "test_the_snapshot_holds_no_text"]),
    ("snapshot integrity not checked", REPLAY, "        if want and want != got:", "        if False:",
     [E + "test_a_changed_snapshot_is_refused"]),
    ("tune accepts a validation regression", EVAL, '    if new_valid[k] < cur_valid[k]:',
     "    if False:", [E + "test_tune_accepts_only_what_holds_out"]),
    ("tune lets bytes grow without recall", EVAL,
     '    if new_valid["bytes"] > cur_valid["bytes"] and new_valid["strict_recall"] <= cur_valid["strict_recall"]:',
     "    if False:", [E + "test_tune_accepts_only_what_holds_out"]),
    # --- round-1 fixes (Cross-Review strata B and C)
    ("a subagent gets branch-keyed items its parent never had", S1,
     '        if stage in ("compact", "subagent"):\n            # compact and subagent offer only',
     '        if stage == "compact":\n            # compact and subagent offer only',
     [G + "test_a_subagent_gets_only_what_the_parent_received"]),
    ("Explore is not treated as a reviewer", S1, "red-?team|^explore$", "red-?team",
     [G + "test_subagent_gets_the_parents_claims_once_and_reviewers_get_none"]),
    ("an injection too late to deliver is recorded", S1,
     '        if decision.get("outcome") == "inject" and not shadow and left() <= DELIVERY_MARGIN_S:',
     "        if False:", [G + "test_an_injection_too_late_to_deliver_is_not_recorded"]),
    ("stale session and PR claims offered", S1, "                    if stale and reader.type_of(tc) in stale:",
     "                    if False:", [T + "test_s2_sources.py::test_stale_session_and_pr_claims_are_not_offered"]),
    ("fork PRs become claims", S2, '    if r.get("isCrossRepository") is not False:',
     "    if False:", [T + "test_s2_sources.py::test_only_the_repos_own_people_author_a_pr_claim"]),
    ("a failed PR fetch reads as no PRs", S2, '                if rows is None:\n                    excluded["pr-fetch-failed"] += 1\n',
     "", [T + "test_s2_sources.py::test_a_failed_pr_fetch_is_counted_not_silent"]),
    ("a PR touching crm/ is indexed", S2,
     '    if any("crm/" in "/" + p.lower() for p in paths) or "crm" in K.terms(str(r.get("title") or "")):',
     "    if False:", [T + "test_s2_sources.py::test_a_pr_touching_crm_is_left_out_whole"]),
    ("the loader passes a missing script's exit 2 through", SH, "    raise SystemExit(0)", "    raise SystemExit(2)",
     [F + "test_the_wrapper_exits_0_when_the_hook_or_interpreter_is_gone"]),
    ("replay keys sorted, not in the event's order", REPLAY,
     '"k": {ch: [H.key(k) for k in K.unique(ks)] for ch, ks in keys.items() if ks},',
     '"k": {ch: sorted({H.key(k) for k in ks}) for ch, ks in keys.items() if ks},',
     [E + "test_the_snapshot_keeps_each_events_key_order"]),
    ("a search-listed hit counted as strict", EVAL,
     '                    easy = bool(idx in echo or listed or edited)',
     '                    easy = bool(idx in echo or edited)',
     [E + "test_e1_scores_the_gate_and_separates_always_from_never"]),
    ("skill bodies do not mask", REPLAY, "            objs = point(_meta_text(obj), where)", "            objs = set()",
     [E + "test_truth_is_counterfactual_and_masked"]),
    ("items created later are candidates", EVAL,
     '            eligible = (lambda idx, ts=ts: items[idx].get("c", 0) <= ts)',
     "            eligible = (lambda idx, ts=ts: True)",
     [SYN]),
    ("a fetch outside the window is a hit", EVAL, "                if o is not None and a <= o < a + w:",
     "                if o is not None:", [SYN]),
    ("the spec bar not enforced", EVAL,
     '        if not _clears(b):\n            cfg["floor"] = None', '        if False:\n            cfg["floor"] = None',
     [E + "test_the_spec_bar_removes_a_floor_that_did_not_earn_it"]),
    # --- round-2 fixes (Cross-Review strata B and C)
    ("separation read on train", EVAL, '"separation": separation(results)}',
     '"separation": separation(results, "train")}', [SYN]),
    ("separation's default split is train", EVAL, 'def separation(results: Dict[str, Any], split: str = "test")',
     'def separation(results: Dict[str, Any], split: str = "train")',
     [E + "test_e1_scores_the_gate_and_separates_always_from_never"]),
    ("tune scores easy hits", EVAL, '    k = "strict_f05"\n', '    k = "f05"\n',
     [E + "test_tune_accepts_only_what_holds_out"]),
    ("re-offer stages tuned alone", EVAL,
     "TUNED_STAGES = tuple(s for s in EVAL_STAGES if s in ctx_s1.ALONE_STAGES)", "TUNED_STAGES = EVAL_STAGES",
     [E + "test_tune_scores_strict_f05_and_skips_stages_that_only_reoffer"]),
    ("the snapshot may be written in a checkout", REPLAY, "    if checkout is not None:\n", "    if False:\n",
     [E + "test_the_snapshot_is_private_by_place"]),
    ("a nested repo's path keyed as the session's", S1,
     '            if os.path.lexists(os.path.join(d, ".git")):', "            if False:",
     [BND + "test_a_path_in_a_nested_repo_of_another_scope_is_not_keyed"]),
    ("another scope's repo keyed", S1, "        return False, None\n", "        return True, loc.toplevel\n",
     [BND + "test_a_path_in_an_unscoped_repo_is_not_keyed"]),
    ("gh -R ignored", KEYS, "                    repo = args[j + 1]\n", "                    pass\n",
     [BND + "test_a_pr_in_another_repo_is_keyed_to_that_repo"]),
    ("re-offered claims never age", S1, "            if now is not None and kind in MAX_AGE_S and (",
     "            if False and (", [BND + "test_a_reoffered_session_or_pr_claim_ages_out"]),
    ("a lock on an unlinked file is used", S1, "        if same:\n            break\n", "        break\n",
     [BND + "test_a_lock_unlinked_under_a_waiting_hook_is_not_used"]),
    ("a used lock is not touched", S1, "        os.utime(fd)  # in use", "        pass  # in use",
     [BND + "test_housekeeping_never_removes_a_held_or_recently_used_lock"]),
    ("the output waits for the log line", S1, "        emit(out)\n", "        pass\n",
     [BND + "test_the_output_is_emitted_before_the_log_line"]),
    ("the hook's emit drops the output", HOOK, '    data = out.encode("utf-8")\n', '    data = b""\n',
     [G + "test_all_turns_every_stage_on_and_the_kill_file_turns_them_off"]),
    # --- round 3 (fresh ledger, round 1) fixes
    ("the replay's payload has no cwd", REPLAY, '            payload = {"tool_name": name, "cwd": where.cwd,',
     '            payload = {"tool_name": name,', [E + "test_a_relative_shell_read_keys_as_it_does_live"]),
    ("parallel calls not anchored after their message", REPLAY,
     '            ev["anchor"] = batch_end[ev["mid"]] + 1', "            pass",
     [E + "test_calls_issued_together_anchor_after_their_message"]),
    ("truth resolves paths without the scope", REPLAY, "        out.update(_path_objs(p, where, scope_id))",
     "        out.update(_path_objs(p, where, None))", [E + "test_truth_and_the_gate_resolve_a_path_the_same_way"]),
    ("a bare PR number is not an echo", REPLAY,
     '        out |= {"o:pr:%s#%s" % (repo, n) for n in ctx_s1.BARE_PR_RE.findall(text)}', "        out |= set()",
     [E + "test_a_bare_pr_number_the_gate_keys_on_is_an_echo"]),
    ("a slug in injected text does not mask", REPLAY, "        out |= slugs.get(tok, set())",
     "        out |= set()", [E + "test_a_wikilink_in_injected_text_masks_the_item"]),
    ("a subagent's listed fetch is not flagged", REPLAY,
     "                    out.append((n, sorted(objs), sorted(o for o in objs if _obj_named(o, seen))))",
     "                    out.append((n, sorted(objs), []))", [E + "test_a_subagent_is_masked_and_listed_like_its_parent"]),
    ("a subagent's own injected text does not mask", REPLAY, "            pointed.append((n, sorted(objs)))",
     "            pass", [E + "test_a_subagent_is_masked_and_listed_like_its_parent"]),
    ("an edit after the event is not easy", EVAL, '                edited = items[idx].get("m", 0) > ts',
     "                edited = False", [E + "test_an_item_edited_after_the_event_is_an_easy_hit"]),
    ("a date-only creation counts from midnight", REPLAY,
     "        return m if c <= m < c + DATE_ONLY_SLACK else c + DATE_ONLY_SLACK", "        return c",
     [E + "test_a_date_only_creation_counts_from_late_that_day"]),
    ("tune accepts a one-hit gain", EVAL, '    if new_train.get("strict_hits", 0) < MIN_TRAIN_STRICT_HITS:',
     "    if False:", [E + "test_tune_accepts_only_what_holds_out"]),
    ("tune scores a proposal twice", EVAL,
     "                    if sig not in tried and sig != json.dumps(_canon(cur), sort_keys=True):",
     "                    if True:", [E + "test_tune_scores_strict_f05_and_skips_stages_that_only_reoffer"]),
    ("gh: an option's value read as the PR", KEYS, "                    j += 1  # its value is not the PR number (`--interval 10`)",
     "                    pass", [BND + "test_a_pr_in_another_repo_is_keyed_to_that_repo"]),
    ("gh: attached -R ignored", KEYS, "                    repo = t[2:]", "                    pass",
     [BND + "test_a_pr_in_another_repo_is_keyed_to_that_repo"]),
    ("a nested repo that cannot be placed is keyed", S1, "        return (nested is None), None",
     "        return True, None", [BND + "test_a_nested_repo_that_cannot_be_placed_is_not_keyed"]),
    ("re-offered claims age from when they were received", S1,
     'now - float(rec.get("as_of") or rec.get("ts") or 0)', 'now - float(rec.get("ts") or 0)',
     [BND + "test_a_reoffered_session_or_pr_claim_ages_out"]),
    ("a subagent spends the session's allowance", S1,
     '        room = SESSION_MAX - total if stage not in ("compact", "subagent") else cfg["max"]',
     '        room = SESSION_MAX - total if stage != "compact" else cfg["max"]',
     [BND + "test_a_subagent_does_not_spend_the_sessions_allowance"]),
    ("housekeeping removes state under a held lock", S2,
     "            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n            if os.fstat",
     "            if os.fstat", [BND + "test_housekeeping_leaves_a_sessions_state_while_its_lock_is_held"]),
    # --- round 3 (fresh ledger, round 2) fixes
    ("a pointer after the fetch voids the hit", EVAL,
     "                if not (o is not None and a <= o < a + w) and p_at is not None and p_at < a + w:",
     "                if p_at is not None and p_at < a + w:", [E + "test_a_fetch_before_a_later_pointer_is_still_a_hit"]),
    ("the replay drops the tool's output", REPLAY,
     '                        ev_b["payload"]["tool_response"] = {"stdout": out_text[:4000]}',
     "                        pass", [E + "test_a_numberless_gh_pr_view_keys_the_pr_its_output_names"]),
    ("the repo is fixed for the whole session", REPLAY, "        repo = K.repo_name(where.common_dir) or repo0",
     "        repo = repo0", [E + "test_after_a_cd_the_event_is_the_new_repos"]),
    ("a cache claim's as-of is not kept", S1, '                                  "as_of": rec.get("as_of_ts"),',
     '                                  "as_of": None,',
     [BND + "test_a_claim_received_from_the_cache_carries_the_builds_time"]),
    ("the echo check ignores the scope's roots", REPLAY,
     "    out = pointer_objs(text) | _echo_paths(text, where, cap, roots)",
     "    out = pointer_objs(text) | _echo_paths(text, where, cap)",
     [E + "test_truth_and_the_gate_resolve_a_path_the_same_way"]),
    ("the snapshot dates items by their raw creation", REPLAY, '"c": _eligible_from(it),',
     '"c": int(it.get("created") or 0),', [E + "test_times_are_exact_so_a_same_day_item_is_judged_to_the_second"]),
    ("old temp files are never swept", S2, '    for p in d.glob(".*.tmp"):', "    for p in []:",
     [BND + "test_housekeeping_sweeps_an_old_temp_file"]),
    ("gh short flags read across subcommands", KEYS,
     "            takes_value = _GH_LONG_VALUES | _GH_SHORT_VALUES.get(toks[2], frozenset())",
     '            takes_value = _GH_LONG_VALUES | frozenset(("-s", "-a", "-m", "-r", "-t", "-b"))',
     [BND + "test_a_short_flag_is_read_per_subcommand"]),
    ("a default-equal setting counts as a change", EVAL,
     '        p["stages"][st] = {k: v for k, v in cfg.items() if not (k in ("max", "budget") and base.get(k) == v)}',
     '        p["stages"][st] = dict(cfg)', [E + "test_tune_scores_strict_f05_and_skips_stages_that_only_reoffer"]),
    # --- review threads on the PR (Copilot)
    ("a non-executable CTX_PYTHON path is exec'd", SH, '  */*) [ -f "$py" ] && [ -x "$py" ] || exit 0 ;;',
     '  */*) [ -f "$py" ] || exit 0 ;;', [F + "test_the_wrapper_exits_0_when_the_hook_or_interpreter_is_gone"]),
    ("gh's exit status ignored", S2, "            if proc.returncode != 0:\n                return None",
     "            if False:\n                return None", [T + "test_s2_sources.py::test_a_gh_call_that_exits_nonzero_is_a_failed_fetch"]),
    ("tune runs past --trials", EVAL, "                if t >= trials:\n                    break  # `trials` bounds",
     "                if False:\n                    break  # `trials` bounds", [E + "test_tune_never_runs_more_trials_than_asked"]),
    ("a stage named twice is registered twice", "scripts/register_s1_hooks.py",
     '    stages = list(dict.fromkeys(s.strip() for s in args.stages.split(",") if s.strip()))',
     '    stages = [s.strip() for s in args.stages.split(",") if s.strip()]',
     [T + "test_s1_register.py::test_a_stage_named_twice_is_registered_once"]),
]


def main() -> int:
    bad = 0
    env = {k: v for k, v in os.environ.items() if k != "CTX_S1_FROZEN"}
    for name, rel, old, new, args in MUTANTS:
        with tempfile.TemporaryDirectory() as d:
            dst = pathlib.Path(d) / "ctx-core"
            shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            f = dst / rel
            text = f.read_text(encoding="utf-8")
            if text.count(old) != 1:
                print("STALE    %s: the original text is not in %s exactly once" % (name, rel))
                bad += 1
                continue
            f.write_text(text.replace(old, new), encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "-x", "-p", "no:cacheprovider"],
                               cwd=str(dst), capture_output=True, text=True, timeout=900, env=env)
            skipped = " skipped" in r.stdout and " passed" not in r.stdout and " failed" not in r.stdout
            verdict = {0: "SURVIVED", 1: "KILLED  "}.get(r.returncode, "ERROR   ")
            if skipped:
                verdict = "SKIPPED "  # a skipped pinning test proves nothing
            bad += verdict != "KILLED  "
            print("%s %s  (%s)%s" % (verdict, name, " ".join(args),
                                     "" if r.returncode in (0, 1) else "  pytest exit %d" % r.returncode), flush=True)
    print("not killed: %d of %d" % (bad, len(MUTANTS)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
