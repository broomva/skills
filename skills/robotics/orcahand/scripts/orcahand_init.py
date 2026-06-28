#!/usr/bin/env python3
"""Bootstrap an OrcaHand workspace: clone repos, install deps, detect hardware."""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from glob import glob
from pathlib import Path

REPOS = [
    ("orcahand_description", "https://github.com/orcahand/orcahand_description.git", False),
    ("orca_sim", "https://github.com/orcahand/orca_sim.git", False),
    ("orca_core", "https://github.com/orcahand/orca_core.git", True),
    ("orca_retargeter", "https://github.com/orcahand/orca_retargeter.git", True),
    ("rwr_system", "https://github.com/orcahand/rwr_system.git", True),
]


def run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def clone_repos(workspace: Path, sim_only: bool) -> dict[str, str]:
    results = {}
    for name, url, hardware_only in REPOS:
        if sim_only and hardware_only:
            results[name] = "SKIPPED (--sim-only)"
            continue
        dest = workspace / name
        if dest.exists():
            results[name] = "EXISTS"
            continue
        r = run(["git", "clone", url, str(dest)])
        results[name] = "OK" if r.returncode == 0 else f"FAIL: {r.stderr.strip()}"
    return results


def install_deps(workspace: Path, sim_only: bool) -> dict[str, str]:
    results = {}
    use_uv = shutil.which("uv") is not None
    installer = "uv pip install" if use_uv else "pip install"
    if not use_uv:
        print("  Warning: uv not found, falling back to pip")

    packages = [("orca_sim", workspace / "orca_sim")]
    if not sim_only:
        packages.insert(0, ("orca_core", workspace / "orca_core"))
        packages.append(("orca_retargeter", workspace / "orca_retargeter"))

    for name, path in packages:
        if not path.exists():
            results[name] = "SKIPPED (not cloned)"
            continue
        cmd = installer.split() + ["-e", str(path)]
        r = run(cmd)
        results[name] = "OK" if r.returncode == 0 else f"FAIL: {r.stderr.strip()[:200]}"
    return results


def detect_serial() -> str | None:
    if platform.system() == "Darwin":
        ports = glob("/dev/tty.usbserial-*")
    else:
        ports = glob("/dev/ttyUSB*")
    return ports[0] if ports else None


def verify_mujoco() -> bool:
    try:
        r = run([sys.executable, "-c", "import mujoco; print(mujoco.__version__)"])
        return r.returncode == 0
    except Exception:
        return False


def generate_plant_yaml(workspace: Path, sim_only: bool, serial_port: str | None):
    plant_dir = workspace / ".control"
    plant_dir.mkdir(exist_ok=True)
    config = {
        "plant": {
            "name": "orcahand",
            "type": "simulated" if sim_only else "physical",
            "interface": "orcahand-plant",
            "state_schema": "schemas/orcahand-state.schema.json",
            "action_schema": "schemas/orcahand-action.schema.json",
            "trace_schema": "schemas/orcahand-trace.schema.json",
            "shields": ["joint_rom", "max_current", "temperature", "velocity", "tactile_overload"],
            "emergency_fallback": "disable_all_torque",
            "estimator": "pass-through",
            "backends": {
                "simulated": {
                    "driver": "orca_sim",
                    "environment": "OrcaHandRight-v2",
                    "render_mode": "human",
                },
            },
        }
    }
    if not sim_only:
        config["plant"]["backends"]["physical"] = {
            "driver": "orca_core",
            "serial_port": serial_port or "auto-detect",
            "baudrate": 3000000,
        }

    import yaml  # noqa: delayed import — pyyaml may not be installed yet

    (plant_dir / "plant.yaml").write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


def main():
    parser = argparse.ArgumentParser(description="Bootstrap an OrcaHand workspace")
    parser.add_argument("--workspace", default=os.path.expanduser("~/broomva/experiments/orcahand"))
    parser.add_argument("--sim-only", action="store_true", help="Skip hardware-related repos")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    print(f"Workspace: {workspace}")

    print("\n1. Cloning repos...")
    clone_results = clone_repos(workspace, args.sim_only)
    for name, status in clone_results.items():
        print(f"   {name}: {status}")

    print("\n2. Installing dependencies...")
    install_results = install_deps(workspace, args.sim_only)
    for name, status in install_results.items():
        print(f"   {name}: {status}")

    serial_port = None
    if not args.sim_only:
        print("\n3. Detecting serial port...")
        serial_port = detect_serial()
        print(f"   {'Found: ' + serial_port if serial_port else 'No U2D2 detected (connect hardware later)'}")

    print("\n4. Verifying MuJoCo...")
    mujoco_ok = verify_mujoco()
    print(f"   {'OK' if mujoco_ok else 'Not found — run: pip install mujoco'}")

    print("\n5. Generating .control/plant.yaml...")
    try:
        generate_plant_yaml(workspace, args.sim_only, serial_port)
        print("   OK")
    except ImportError:
        print("   SKIP (pyyaml not installed yet — run manually after install)")

    print("\n--- Summary ---")
    any_fail = any("FAIL" in v for v in {**clone_results, **install_results}.values())
    if any_fail:
        print("Some steps failed. Check output above.")
        sys.exit(1)
    else:
        print("Workspace ready!")
        if args.sim_only:
            print("\nNext: python -c 'from orca_sim import OrcaHandRight; env = OrcaHandRight(); env.reset()'")
        else:
            print("\nNext: cd orca_core && python scripts/tension.py orca_core/models/orcahand_v1_right")


if __name__ == "__main__":
    main()
