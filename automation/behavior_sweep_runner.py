from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from run_one_by_one_sweeps import run as run_one_by_one
from run_two_param_map import run as run_two_param


BASE_CIRCUIT = "C:/Users/vchat/Downloads/LTspice/my_neuron_tonic-Abs_&_Rel_Ref_Period_ReRs.asc"
LTSPICE_EXE = "C:/Users/vchat/LTspice/LTspice.exe"


BEHAVIOR_PROFILES: dict[str, dict[str, Any]] = {
    "all_or_nothing": {
        "title": "All-or-Nothing",
        "input_mode": "voltage_pulse",
        "base_circuit": "C:/Users/vchat/Downloads/LTspice/my_neuron_tonic-AllorNothing_ReRs.asc",
        "voltage_sources": ["V3", "V4", "V5", "V6"],
        "current_sources": [],
        "assumptions": [
            "This behavior uses the Vin-driven variant in Supplementary Table 2 (S10).",
            "Voltage pulse input is applied through multiple voltage-source components (V3, V4, V5, V6).",
        ],
        "table2_defaults": {
            "R1": 6000,
            "R2": 6000,
            "C1": 2e-9,
            "C2": 2e-9,
            "V1": -1.35,
            "V2": 1.35,
        },
        "fixed_components": {
            "R1": 6000,
            "R2": 6000,
            "C1": 2e-9,
            "C2": 2e-9,
            "V2": 1.35,
            "V1": -1.35,
            "V3": "PULSE(0 0.10 110u 1n 1n 10u 120u 1)",
            "V4": "PULSE(0 0.15 220u 1n 1n 10u 120u 1)",
            "V5": "PULSE(0 0.45 330u 1n 1n 10u 120u 1)",
            "V6": "PULSE(0 0.55 440u 1n 1n 10u 120u 1)",
        },
        "single_windows": {
            "RL1": {"name": "RL1_single", "component": "R1", "min": 3000, "max": 9000, "step": 250, "scale": "linear"},
            "RL2": {"name": "RL2_single", "component": "R2", "min": 3000, "max": 9000, "step": 250, "scale": "linear"},
            "C1": {"name": "C1_single", "component": "C1", "min": 0.8e-9, "max": 12e-9, "steps": 15, "scale": "log"},
            "C2": {"name": "C2_single", "component": "C2", "min": 0.8e-9, "max": 12e-9, "steps": 15, "scale": "log"},
        },
        "pairs": {
            "RL1_C1": {
                "x_param": {"name": "RL1", "component": "R1", "min": 3000, "max": 9000, "step": 250, "scale": "linear"},
                "y_param": {"name": "C1", "component": "C1", "min": 0.8e-9, "max": 12e-9, "steps": 17, "scale": "log"},
            },
            "RL2_C2": {
                "x_param": {"name": "RL2", "component": "R2", "min": 3000, "max": 9000, "step": 250, "scale": "linear"},
                "y_param": {"name": "C2", "component": "C2", "min": 0.8e-9, "max": 12e-9, "steps": 17, "scale": "log"},
            },
        },
    },
    "refractory": {
        "title": "Refractory Period",
        "input_mode": "voltage_pulse",
        "base_circuit": "C:/Users/vchat/Downloads/LTspice/my_neuron_tonic-Refractory_period.asc",
        "voltage_sources": ["V3", "V4"],
        "current_sources": [],
        "assumptions": [
            "This behavior uses the Vin-driven variant in Supplementary Table 2 (S11).",
            "The default waveform is a voltage-pulse doublet using separate sources V3 and V4.",
        ],
        "table2_defaults": {
            "R1": 5000,
            "R2": 5000,
            "C1": 5e-9,
            "C2": 5e-9,
            "V1": -1.6,
            "V2": 1.6,
        },
        "fixed_components": {
            "R1": 5000,
            "R2": 5000,
            "C1": 5e-9,
            "C2": 5e-9,
            "V2": 1.6,
            "V1": -1.6,
            "V3": "PULSE(0 0.45 10u 1e-9 1e-9 10e-6 200e-6 1)",
            "V4": "PULSE(0 0.45 35u 1e-9 1e-9 10e-6 200e-6 1)",
        },
        "single_windows": {
            "RL1": {"name": "RL1_single", "component": "R1", "min": 2500, "max": 8500, "step": 250, "scale": "linear"},
            "RL2": {"name": "RL2_single", "component": "R2", "min": 2500, "max": 8500, "step": 250, "scale": "linear"},
            "C1": {"name": "C1_single", "component": "C1", "min": 1e-9, "max": 20e-9, "steps": 17, "scale": "log"},
            "C2": {"name": "C2_single", "component": "C2", "min": 1e-9, "max": 20e-9, "steps": 17, "scale": "log"},
        },
        "pairs": {
            "RL1_C1": {
                "x_param": {"name": "RL1", "component": "R1", "min": 2500, "max": 8500, "step": 250, "scale": "linear"},
                "y_param": {"name": "C1", "component": "C1", "min": 1e-9, "max": 20e-9, "steps": 19, "scale": "log"},
            },
            "RL2_C2": {
                "x_param": {"name": "RL2", "component": "R2", "min": 2500, "max": 8500, "step": 250, "scale": "linear"},
                "y_param": {"name": "C2", "component": "C2", "min": 1e-9, "max": 20e-9, "steps": 19, "scale": "log"},
            },
        },
    },
    "tonic_spiking": {
        "title": "Tonic Spiking",
        "input_mode": "current_dc",
        "base_circuit": "C:/Users/vchat/Downloads/LTspice/my_neuron_tonic-Tonic_spiking.asc",
        "current_sources": ["I1"],
        "assumptions": [
            "Tonic spike profile follows Supplementary Table 2 (S13).",
            "Sustained DC current drive is applied through I1.",
            "I2 is disabled for cleaner tonic-drive analysis.",
        ],
        "table2_defaults": {
            "R1": 5000,
            "R2": 5000,
            "C1": 5e-9,
            "C2": 2e-9,
            "V1": -1.5,
            "V2": 1.5,
        },
        "fixed_components": {
            "R1": 5000,
            "R2": 5000,
            "C1": 5e-9,
            "C2": 2e-9,
            "V2": 1.5,
            "V1": -1.5,
            "I1": "DC 60u",
        },
        "single_windows": {
            "RL1": {"name": "RL1_single", "component": "R1", "min": 3500, "max": 11000, "step": 250, "scale": "linear"},
            "RL2": {"name": "RL2_single", "component": "R2", "min": 5500, "max": 14000, "step": 250, "scale": "linear"},
            "C1": {"name": "C1_single", "component": "C1", "min": 2e-9, "max": 60e-9, "steps": 17, "scale": "log"},
            "C2": {"name": "C2_single", "component": "C2", "min": 0.8e-9, "max": 20e-9, "steps": 17, "scale": "log"},
        },
        "pairs": {
            "RL1_C1": {
                "x_param": {"name": "RL1", "component": "R1", "min": 3500, "max": 11000, "step": 250, "scale": "linear"},
                "y_param": {"name": "C1", "component": "C1", "min": 2e-9, "max": 60e-9, "steps": 21, "scale": "log"},
            },
            "RL2_C2": {
                "x_param": {"name": "RL2", "component": "R2", "min": 5500, "max": 14000, "step": 250, "scale": "linear"},
                "y_param": {"name": "C2", "component": "C2", "min": 0.8e-9, "max": 20e-9, "steps": 21, "scale": "log"},
            },
        },
    },
    "tonic_bursting": {
        "title": "Tonic Bursting",
        "input_mode": "current_dc",
        "base_circuit": "C:/Users/vchat/Downloads/LTspice/my_neuron_tonic-Tonic_spiking.asc",
        "current_sources": ["I1"],
        "assumptions": [
            "Tonic burst profile based on custom working parameters.",
            "Sustained current drive is applied through I1 (-90uA PWL).",
            "Primary behavior matches screenshots with C1=30nF for bursting.",
        ],
        "table2_defaults": {
            "R1": 6000,
            "R2": 6000,
            "C1": 30e-9,
            "C2": 3e-9,
            "V1": -1.4,
            "V2": 1.4,
        },
        "fixed_components": {
            "R1": 6000,
            "R2": 6000,
            "C1": 30e-9,
            "C2": 3e-9,
            "V2": 1.4,
            "V1": -1.4,
            "I1": "PWL(0 0 0.0001m -90u 1m -90u 1.0001m 0)",
        },
        "single_windows": {
            "RL1": {"name": "RL1_single", "component": "R1", "min": 4500, "max": 12000, "step": 250, "scale": "linear"},
            "RL2": {"name": "RL2_single", "component": "R2", "min": 6000, "max": 15000, "step": 250, "scale": "linear"},
            "C1": {"name": "C1_single", "component": "C1", "min": 5e-9, "max": 120e-9, "steps": 19, "scale": "log"},
            "C2": {"name": "C2_single", "component": "C2", "min": 1e-9, "max": 30e-9, "steps": 19, "scale": "log"},
        },
        "pairs": {
            "RL1_C1": {
                "x_param": {"name": "RL1", "component": "R1", "min": 4500, "max": 12000, "step": 250, "scale": "linear"},
                "y_param": {"name": "C1", "component": "C1", "min": 5e-9, "max": 120e-9, "steps": 21, "scale": "log"},
            },
            "RL2_C2": {
                "x_param": {"name": "RL2", "component": "R2", "min": 6000, "max": 15000, "step": 250, "scale": "linear"},
                "y_param": {"name": "C2", "component": "C2", "min": 1e-9, "max": 30e-9, "steps": 21, "scale": "log"},
            },
        },
    },
}


def _print_assumptions(profile: dict[str, Any]) -> None:
    print("Assumptions for this behavior profile:")
    for idx, item in enumerate(profile.get("assumptions", []), start=1):
        print(f"  {idx}. {item}")


def _ask_choice(prompt: str, options: list[str], default: str) -> str:
    options_display = "/".join(options)
    text = input(f"{prompt} ({options_display}) [{default}]: ").strip()
    return text if text in options else default


def _ask_text(prompt: str, default: str) -> str:
    text = input(f"{prompt} [{default}]: ").strip()
    return text if text else default


def _ask_float(prompt: str, default: float) -> float:
    while True:
        text = input(f"{prompt} [{default}]: ").strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            print("Please enter a valid number.")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        text = input(f"{prompt} [{default}]: ").strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            print("Please enter a valid integer.")


def _customize_window(spec: dict[str, Any], label: str, force: bool) -> dict[str, Any]:
    updated = dict(spec)
    if force:
        return updated

    adjust = _ask_choice(f"Adjust sweep window for {label}", ["yes", "no"], "no")
    if adjust == "no":
        return updated

    updated["min"] = _ask_float(f"{label} min", float(updated["min"]))
    updated["max"] = _ask_float(f"{label} max", float(updated["max"]))
    default_scale = str(updated.get("scale", "linear"))
    updated["scale"] = _ask_choice(f"{label} scale", ["linear", "log"], default_scale)

    if "step" in updated:
        default_step = float(updated["step"])
        updated["step"] = _ask_float(f"{label} step", default_step)
        updated.pop("steps", None)
    else:
        default_steps = int(updated.get("steps", 11))
        updated["steps"] = _ask_int(f"{label} steps", default_steps)
        updated.pop("step", None)

    return updated


def _configure_inputs(profile: dict[str, Any], force: bool) -> dict[str, Any]:
    fixed = dict(profile.get("fixed_components", {}))
    mode = str(profile.get("input_mode", "current_dc"))

    if force:
        return fixed

    if mode == "voltage_pulse":
        voltage_sources = profile.get("voltage_sources", ["V3"])
        for src in voltage_sources:
            default_expr = str(fixed.get(src, "PULSE(0 0.1 10u 1n 1n 10u 100u 1)"))
            fixed[src] = _ask_text(f"Voltage stimulus {src} expression", default_expr)

        disable_current = _ask_choice("Disable I1/I2 current sources for this run", ["yes", "no"], "yes")
        if disable_current == "yes":
            for current_src in profile.get("current_sources", ["I1", "I2"]):
                fixed[str(current_src)] = "DC 0"
    else:
        current_sources = profile.get("current_sources", ["I1"])
        for src in current_sources:
            default_expr = str(fixed.get(src, "DC 60u" if src == "I1" else "DC 0"))
            fixed[src] = _ask_text(f"Current input {src} expression", default_expr)

    print("Confirm input settings:")
    for k in sorted(fixed.keys()):
        if k.startswith("V") or k.startswith("I"):
            print(f"  {k} = {fixed[k]}")
    confirm = _ask_choice("Are these input settings correct", ["yes", "no"], "yes")
    if confirm == "no":
        print("Re-entering input settings...")
        return _configure_inputs(profile, force=False)

    return fixed


def _ask_fixed_param_overrides(fixed_components: dict[str, Any], force: bool) -> dict[str, Any]:
    fixed = dict(fixed_components)
    if force:
        return fixed

    print("Review fixed parameter assumptions (press Enter to keep default):")
    for key in ["R1", "R2", "C1", "C2", "V1", "V2", "Re1", "Re2", "Rshunt1", "Rshunt2"]:
        if key in fixed:
            fixed[key] = _ask_text(f"  {key}", str(fixed[key]))
    return fixed


def _coerce_fixed_values(values: dict[str, Any]) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for k, v in values.items():
        if isinstance(v, (int, float)):
            coerced[k] = v
            continue
        text = str(v).strip()
        try:
            coerced[k] = float(text)
        except ValueError:
            coerced[k] = text
    return coerced


def _write_assumptions(
    out_dir: Path,
    *,
    behavior_key: str,
    profile_title: str,
    mode: str,
    fixed_components: dict[str, Any],
    sweep_info: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "behavior_key": behavior_key,
        "profile_title": profile_title,
        "sweep_mode": mode,
        "fixed_components_assumed": fixed_components,
        "sweep_info": sweep_info,
    }
    meta_path = out_dir / "assumptions.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _build_common_cfg(output_dir: Path, fixed_components: dict[str, Any], base_circuit: str | None = None) -> dict[str, Any]:
    return {
        "base_circuit": base_circuit or BASE_CIRCUIT,
        "ltspice_exe": LTSPICE_EXE,
        "output_dir": str(output_dir),
        "parallel_sims": 1,
        "timeout_s": 600,
        "verbose": False,
        "trace_name": "V(n003)",
        "fixed_components": fixed_components,
    }


def run_behavior(
    behavior_key: str,
    mode: str,
    pair: str,
    single_param: str,
    force: bool,
) -> Path:
    if behavior_key not in BEHAVIOR_PROFILES:
        raise ValueError(f"Unsupported behavior '{behavior_key}'")

    profile = BEHAVIOR_PROFILES[behavior_key]

    print(f"Behavior: {profile['title']}")
    table2_defaults = profile.get("table2_defaults", {})
    if table2_defaults:
        print("Table 2 default anchors:")
        for k, v in table2_defaults.items():
            print(f"  {k} = {v}")
    _print_assumptions(profile)
    if not force:
        proceed = input("Proceed with these assumptions? [y/N]: ").strip().lower()
        if proceed not in {"y", "yes"}:
            raise RuntimeError("User did not confirm assumptions.")

    chosen_mode = mode
    if chosen_mode == "ask":
        chosen_mode = _ask_choice(
            "Sweep type",
            ["single", "coupling"],
            "coupling",
        )

    root = Path("automation/results_behavior_windows") / behavior_key
    root.mkdir(parents=True, exist_ok=True)

    configured_fixed = _configure_inputs(profile, force=force)
    configured_fixed = _ask_fixed_param_overrides(configured_fixed, force=force)
    configured_fixed = _coerce_fixed_values(configured_fixed)

    print("Fixed parameters assumed for this run:")
    for k in sorted(configured_fixed.keys()):
        print(f"  {k} = {configured_fixed[k]}")

    if chosen_mode == "single":
        param = single_param
        if param == "ask":
            param = _ask_choice("Single parameter", ["RL1", "RL2", "C1", "C2"], "RL1")

        spec = _customize_window(profile["single_windows"][param], f"{param} ({profile['title']})", force=force)
        out_dir = root / f"single_{param.lower()}"
        cfg = _build_common_cfg(out_dir, configured_fixed, base_circuit=profile.get("base_circuit"))
        cfg["sweeps"] = [spec]
        _write_assumptions(
            out_dir,
            behavior_key=behavior_key,
            profile_title=profile["title"],
            mode="single",
            fixed_components=configured_fixed,
            sweep_info={"single_param": param, "spec": spec},
        )
        run_one_by_one(cfg)
        return out_dir

    selected_pair = pair
    if selected_pair == "ask":
        selected_pair = _ask_choice("Coupling pair", ["RL1_C1", "RL2_C2"], "RL1_C1")

    pair_spec = dict(profile["pairs"][selected_pair])
    pair_spec["x_param"] = _customize_window(
        pair_spec["x_param"],
        f"{selected_pair} X ({pair_spec['x_param']['name']})",
        force=force,
    )
    pair_spec["y_param"] = _customize_window(
        pair_spec["y_param"],
        f"{selected_pair} Y ({pair_spec['y_param']['name']})",
        force=force,
    )
    out_dir = root / f"coupling_{selected_pair.lower()}"
    cfg = _build_common_cfg(out_dir, configured_fixed, base_circuit=profile.get("base_circuit"))
    cfg["x_param"] = pair_spec["x_param"]
    cfg["y_param"] = pair_spec["y_param"]
    cfg["voltage_coupling"] = {
        "enabled": True,
        "positive_component": "V2",
        "negative_component": "V1",
    }
    _write_assumptions(
        out_dir,
        behavior_key=behavior_key,
        profile_title=profile["title"],
        mode="coupling",
        fixed_components=configured_fixed,
        sweep_info={"pair": selected_pair, "x_param": pair_spec["x_param"], "y_param": pair_spec["y_param"]},
    )
    run_two_param(cfg)
    return out_dir


def main_for_behavior(behavior_key: str) -> None:
    parser = argparse.ArgumentParser(description=f"Behavior-window sweep runner: {behavior_key}")
    parser.add_argument("--mode", choices=["ask", "single", "coupling"], default="ask")
    parser.add_argument("--pair", choices=["ask", "RL1_C1", "RL2_C2"], default="ask")
    parser.add_argument("--single-param", choices=["ask", "RL1", "RL2", "C1", "C2"], default="ask")
    parser.add_argument("--force", action="store_true", help="Skip assumption confirmation prompt")
    args = parser.parse_args()

    out_dir = run_behavior(
        behavior_key=behavior_key,
        mode=args.mode,
        pair=args.pair,
        single_param=args.single_param,
        force=args.force,
    )
    print(f"Results: {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive behavior-window sweep runner")
    parser.add_argument(
        "--behavior",
        choices=["ask", "all_or_nothing", "refractory", "tonic_spiking", "tonic_bursting"],
        default="ask",
        help="Behavior profile to run",
    )
    parser.add_argument("--mode", choices=["ask", "single", "coupling"], default="ask")
    parser.add_argument("--pair", choices=["ask", "RL1_C1", "RL2_C2"], default="ask")
    parser.add_argument("--single-param", choices=["ask", "RL1", "RL2", "C1", "C2"], default="ask")
    parser.add_argument("--force", action="store_true", help="Skip assumption/input/window confirmation prompts")
    args = parser.parse_args()

    behavior = args.behavior
    if behavior == "ask":
        behavior = _ask_choice(
            "Behavior",
            ["all_or_nothing", "refractory", "tonic_spiking", "tonic_bursting"],
            "all_or_nothing",
        )

    out_dir = run_behavior(
        behavior_key=behavior,
        mode=args.mode,
        pair=args.pair,
        single_param=args.single_param,
        force=args.force,
    )
    print(f"Results: {out_dir}")


if __name__ == "__main__":
    main()
