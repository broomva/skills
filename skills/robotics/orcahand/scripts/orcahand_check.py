#!/usr/bin/env python3
"""Health check for OrcaHand workspace — outputs JSON for bstack-check integration."""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def check_repos(workspace: Path) -> dict:
    repos = ["orcahand_description", "orca_sim", "orca_core", "orca_retargeter"]
    results = {}
    for repo in repos:
        path = workspace / repo
        if path.exists() and (path / ".git").exists():
            results[repo] = "PASS"
        elif path.exists():
            results[repo] = "WARN"  # exists but not a git repo
        else:
            results[repo] = "SKIP"  # may be sim-only
    # At minimum, orcahand_description and orca_sim should exist
    if results.get("orcahand_description") == "SKIP" or results.get("orca_sim") == "SKIP":
        return {"status": "FAIL", "details": results}
    return {"status": "PASS", "details": results}


def check_python_deps() -> dict:
    deps = {}
    for module in ["mujoco", "gymnasium", "numpy"]:
        try:
            __import__(module)
            deps[module] = "PASS"
        except ImportError:
            deps[module] = "FAIL"
    # Optional deps
    for module in ["dynamixel_sdk", "torch", "pytorch_kinematics"]:
        try:
            __import__(module)
            deps[module] = "PASS"
        except ImportError:
            deps[module] = "SKIP"
    has_fail = any(v == "FAIL" for v in deps.values())
    return {"status": "FAIL" if has_fail else "PASS", "details": deps}


def check_mujoco() -> dict:
    try:
        import mujoco
        # Try loading a simple model to verify it actually works
        xml = '<mujoco><worldbody><body><geom type="sphere" size="0.1"/></body></worldbody></mujoco>'
        mujoco.MjModel.from_xml_string(xml)
        return {"status": "PASS", "version": mujoco.__version__}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def check_serial() -> dict:
    import platform
    from glob import glob
    if platform.system() == "Darwin":
        ports = glob("/dev/tty.usbserial-*")
    else:
        ports = glob("/dev/ttyUSB*")
    if ports:
        return {"status": "PASS", "port": ports[0]}
    return {"status": "SKIP", "reason": "No U2D2 serial device detected"}


def check_calibration(workspace: Path) -> dict:
    cal_files = list(workspace.glob("**/calibration.yaml"))
    if not cal_files:
        return {"status": "SKIP", "reason": "No calibration.yaml found"}
    newest = max(cal_files, key=lambda p: p.stat().st_mtime)
    age_days = (time.time() - newest.stat().st_mtime) / 86400
    if age_days > 7:
        return {"status": "WARN", "file": str(newest), "age_days": round(age_days, 1)}
    return {"status": "PASS", "file": str(newest), "age_days": round(age_days, 1)}


def check_sim_env() -> dict:
    try:
        from orca_sim import OrcaHandRight
        env = OrcaHandRight(render_mode="rgb_array")
        obs, info = env.reset(seed=0)
        env.close()
        return {"status": "PASS", "obs_shape": list(obs.shape)}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def check_schemas(skill_dir: Path) -> dict:
    schema_dir = skill_dir / "schemas"
    if not schema_dir.exists():
        return {"status": "FAIL", "error": "schemas/ directory not found"}
    results = {}
    for schema_file in schema_dir.glob("*.json"):
        try:
            with open(schema_file) as f:
                data = json.load(f)
            if "$schema" in data and "properties" in data:
                results[schema_file.name] = "PASS"
            else:
                results[schema_file.name] = "WARN"
        except json.JSONDecodeError as e:
            results[schema_file.name] = f"FAIL: {e}"
    has_fail = any("FAIL" in str(v) for v in results.values())
    return {"status": "FAIL" if has_fail else "PASS", "details": results}


def check_plant_yaml(workspace: Path) -> dict:
    plant_yaml = workspace / ".control" / "plant.yaml"
    if not plant_yaml.exists():
        return {"status": "FAIL", "error": ".control/plant.yaml not found"}
    try:
        import yaml
        with open(plant_yaml) as f:
            data = yaml.safe_load(f)
        if "plant" in data and "name" in data["plant"]:
            return {"status": "PASS", "plant_name": data["plant"]["name"]}
        return {"status": "FAIL", "error": "Missing plant.name in .control/plant.yaml"}
    except ImportError:
        return {"status": "SKIP", "reason": "pyyaml not installed"}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="OrcaHand workspace health check")
    parser.add_argument("--workspace", default=os.path.expanduser("~/broomva/experiments/orcahand"))
    parser.add_argument("--skill-dir", default=None, help="Path to the orcahand skill directory")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    skill_dir = Path(args.skill_dir) if args.skill_dir else Path(__file__).parent.parent

    checks = {
        "repos_present": check_repos(workspace),
        "python_deps": check_python_deps(),
        "mujoco_working": check_mujoco(),
        "serial_connected": check_serial(),
        "calibration_fresh": check_calibration(workspace),
        "sim_env_loadable": check_sim_env(),
        "schemas_valid": check_schemas(skill_dir),
        "plant_yaml_present": check_plant_yaml(workspace),
    }

    any_fail = any(c["status"] == "FAIL" for c in checks.values())

    if args.json:
        print(json.dumps({"overall": "FAIL" if any_fail else "PASS", "checks": checks}, indent=2))
    else:
        for name, result in checks.items():
            status = result["status"]
            icon = {"PASS": "OK", "FAIL": "XX", "SKIP": "--", "WARN": "!!"}.get(status, "??")
            print(f"  [{icon}] {name}: {status}")
            if "error" in result:
                print(f"       {result['error']}")
        print(f"\nOverall: {'FAIL' if any_fail else 'PASS'}")

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
