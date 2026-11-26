#!/usr/bin/env python3
"""Prove that executable tests catch defects in every Soundcraft QA gate."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/audio_qa.py")
TESTS = Path("tests/test_soundcraft.py")

# Each replacement must alter exactly one predicate or operation. Run only its
# behavioral tests so an unrelated failure cannot claim the kill.
MUTATIONS = (
    ("integrated loudness ignored", "abs(integrated - args.target_lufs) <= args.lufs_tol + 1e-9",
     "True", "test_integrated_loudness_failure"),
    ("true peak ignored", "true_peak <= args.max_tp", "True", "test_true_peak_failure_without_pcm_clip"),
    ("loudness range ignored", "lra >= args.min_lra", "True", "test_loudness_range_failure"),
    ("clip sample includes only positive values", "abs(sample) >= CLIP_LEVEL",
     "sample >= CLIP_LEVEL", "test_clipping_threshold_includes_both_polarities"),
    ("clip sample drops the threshold itself", "abs(sample) >= CLIP_LEVEL",
     "abs(sample) > CLIP_LEVEL", "test_clipping_threshold_includes_both_polarities"),
    ("clipping budget ignored", "clipped <= args.max_clipped",
     "True", "test_clipping_threshold_includes_both_polarities"),
    ("DC offsets cancel across channels", "max(map(abs, dc)) <= MAX_DC_OFFSET",
     "abs(statistics.mean(dc)) <= MAX_DC_OFFSET", "test_dc_offset_checks_each_channel"),
    ("dead silence ignored", "rms > MIN_RMS_DBFS", "True", "test_dead_silence_failure"),
    ("A/V length mismatch ignored", 'metrics["av_delta_ms"] <= args.max_av_delta_ms + 1e-9',
     "True", "test_av_duration_failure"),
    ("A/V start mismatch ignored", 'metrics["av_start_delta_ms"] <= args.max_av_delta_ms + 1e-9',
     "True", "test_av_start_failure"),
    ("expected duration ignored", 'metrics["expected_delta_ms"] <= args.max_av_delta_ms + 1e-9',
     "True", "test_expected_duration_failure_and_boundary"),
    ("late peak ignored", "peak_frac <= MAX_PEAK_TIME_FRAC", "True", "test_logo_peak_gate_is_opt_in"),
    ("loudest RMS window ignored", "if energy > best_energy:",
     "if False:", "test_default_audio_only_passes"),
    ("speech noise floor ignored", "voice_db > noise_floor + 12 and voice_db > -42",
     "voice_db > -42", "test_voice_snr_activity_is_relative_to_noise_floor"),
    ("absolute speech floor ignored", "voice_db > noise_floor + 12 and voice_db > -42",
     "voice_db > noise_floor + 12", "test_voice_snr_rejects_no_activity"),
    ("speech coverage ignored", 'snr["covered_speech_frames"] == snr["active_speech_frames"] > 0',
     "True", "test_voice_snr_checks_coverage"),
    ("zero active speech accepted as covered", 'snr["covered_speech_frames"] == snr["active_speech_frames"] > 0',
     'snr["covered_speech_frames"] == snr["active_speech_frames"]', "test_voice_snr_rejects_no_activity"),
    ("median voice SNR ignored", "median >= MIN_MEDIAN_SNR_DB",
     "True", "test_voice_has_independent_median_and_soft_frame_gates"),
    ("lower voice SNR tail ignored", "p15 >= MIN_P15_SNR_DB",
     "True", "test_voice_has_independent_median_and_soft_frame_gates"),
    ("per-stem peak threshold ignored", "peak < 0.999", "True", "test_repeatable_stem_peak_gate"),
    ("only one stem needs to pass peak gate", 'all(stem["peak_passed"] for stem in stems)',
     'any(stem["peak_passed"] for stem in stems)', "test_repeatable_stem_peak_gate"),
    ("stem length ignored", "duration >= expected_dur - MAX_STEM_SHORTFALL_S",
     "True", "test_stem_truncation_and_sidechain_pad"),
    ("quarter-second stem tolerance removed", "duration >= expected_dur - MAX_STEM_SHORTFALL_S",
     "duration >= expected_dur", "test_stem_allows_quarter_second_shortfall"),
    ("no silence appended by pad-sidechain", "apad=pad_dur={args.pad_s:.9f}",
     "anull", "test_stem_truncation_and_sidechain_pad"),
    ("gate failures still exit successfully", "return int(bool(failed))",
     "return 0", "test_cli_text_success_and_gate_failure"),
)


def pytest_at(root: Path, selection: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", str(TESTS) + selection],
        cwd=root, capture_output=True, text=True,
    )


def main() -> int:
    original = (SOURCE / SCRIPT).read_text()
    survived = []
    with tempfile.TemporaryDirectory(prefix="mut_soundcraft_") as temporary:
        root = Path(temporary)
        for relative in (SCRIPT, TESTS):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, root / relative)

        baseline = pytest_at(root)
        if baseline.returncode != 0:
            print(f"ERROR baseline pytest exited {baseline.returncode}\n{baseline.stdout}{baseline.stderr}")
            return 2
        print("Baseline passed", flush=True)

        for name, anchor, replacement, test in MUTATIONS:
            if original.count(anchor) != 1:
                print(f"ERROR {name}: mutation anchor must occur exactly once")
                return 2
            source = original.replace(anchor, replacement, 1)
            compile(source, str(SCRIPT), "exec")
            (root / SCRIPT).write_text(source)
            result = pytest_at(root, f"::{test}")
            if result.returncode == 1:
                print(f"KILLED   {name}", flush=True)
            elif result.returncode == 0:
                survived.append(name)
                print(f"SURVIVED {name}", flush=True)
            else:
                print(f"ERROR {name}: pytest exited {result.returncode}\n{result.stdout}{result.stderr}")
                return 2

    total = len(MUTATIONS)
    print(f"\n{total - len(survived)}/{total} mutations killed")
    return int(bool(survived))


if __name__ == "__main__":
    sys.exit(main())
