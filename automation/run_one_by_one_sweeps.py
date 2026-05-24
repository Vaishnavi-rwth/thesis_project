from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PyLTSpice import LTspice, RawRead, SimRunner, SpiceEditor


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _resolve_ltspice_simulator(cfg: dict[str, Any]):
    ltspice_exe = (cfg.get("ltspice_exe") or "").strip()
    if ltspice_exe:
        exe = Path(ltspice_exe).expanduser().resolve()
        if not exe.exists():
            raise FileNotFoundError(f"Configured LTspice executable not found: {exe}")
        return LTspice.create_from(str(exe))

    common_candidates = [
        Path("C:/Program Files/ADI/LTspice/LTspice.exe"),
        Path("C:/Program Files/LTC/LTspiceXVII/XVIIx64.exe"),
    ]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        common_candidates.append(Path(local_appdata) / "Programs/ADI/LTspice/LTspice.exe")

    for candidate in common_candidates:
        if candidate.exists():
            return LTspice.create_from(str(candidate.resolve()))
    return LTspice


def _resolve_base_circuit(base_circuit: str, simulator) -> Path:
    base = Path(base_circuit).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(f"Base circuit not found: {base}")
    if base.suffix.lower() == ".asc":
        return Path(simulator.create_netlist(base)).resolve()
    if base.suffix.lower() not in {".net", ".cir", ".sp", ".spi"}:
        raise ValueError("base_circuit must be .asc, .net, .cir, .sp, or .spi")
    return base


def _fix_subcircuit_deltaT(net_path: Path) -> None:
    """Convert Tamb/Tmit params to deltaT in subcircuit instance lines.

    Some circuit schematics pass Tamb and Tmit as separate parameters to
    the NDR_VO2 subcircuit, but the subcircuit only defines functions in
    terms of *deltaT*.  This rewrites the netlist in-place so that
    ``Tamb=X, Tmit=Y`` becomes ``deltaT=(Y-X)``.
    """
    text = net_path.read_text(encoding="utf-8")
    if "Tamb" not in text:
        return
    lines = text.split("\n")
    changed = False
    for i, line in enumerate(lines):
        if not line.strip().startswith("XX"):
            continue
        tamb_m = re.search(r"Tamb\s*=\s*([\d.eE+-]+)", line)
        tmit_m = re.search(r"Tmit\s*=\s*([\d.eE+-]+)", line)
        if not (tamb_m and tmit_m):
            continue
        delta_t = float(tmit_m.group(1)) - float(tamb_m.group(1))
        line = re.sub(
            r"Tamb\s*=\s*[\d.eE+-]+\s*,\s*Tmit\s*=\s*[\d.eE+-]+",
            f"deltaT={delta_t:g}",
            line,
        )
        lines[i] = line
        changed = True
    if changed:
        net_path.write_text("\n".join(lines), encoding="utf-8")


def _get_trace(raw_path: Path, trace_name: str) -> tuple[np.ndarray, np.ndarray]:
    raw = RawRead(raw_path, verbose=False)
    names = set(raw.get_trace_names())
    if trace_name not in names:
        available = ", ".join(sorted(names))
        raise KeyError(f"Trace '{trace_name}' not found in {raw_path}. Available: {available}")
    time_s = np.asarray(raw.get_time_axis(), dtype=float)
    wave = np.asarray(raw.get_wave(trace_name), dtype=float)
    return time_s, wave


def _plot_waveform(time_s: np.ndarray, voltage_v: np.ndarray, png_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.plot(time_s * 1e6, voltage_v, linewidth=1.0)
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("V(n003) (V)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(png_path)
    plt.close(fig)


def _clear_directory_contents(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except (FileNotFoundError, PermissionError):
                pass


def _format_value(v: float) -> str:
    return f"{float(v):.10g}"


def _build_values(spec: dict[str, Any]) -> list[float]:
    if "values" in spec:
        return [float(v) for v in spec["values"]]

    vmin = float(spec["min"])
    vmax = float(spec["max"])
    if vmax <= vmin:
        raise ValueError(f"Sweep '{spec.get('name', '<unnamed>')}' requires max > min")

    scale = str(spec.get("scale", "linear")).lower()
    step = spec.get("step")

    if step is not None:
        step_val = float(step)
        if step_val <= 0:
            raise ValueError(f"Sweep '{spec.get('name', '<unnamed>')}' requires step > 0")
        if scale != "linear":
            raise ValueError(f"Sweep '{spec.get('name', '<unnamed>')}' step is only supported for linear scale")
        count = int(np.floor((vmax - vmin) / step_val + 1e-12)) + 1
        vals = [vmin + i * step_val for i in range(count)]
        if vals[-1] < vmax:
            vals.append(vmax)
        return [float(v) for v in vals]

    steps = int(spec["steps"])
    if steps < 2:
        raise ValueError(f"Sweep '{spec.get('name', '<unnamed>')}' must have steps >= 2")

    if scale == "linear":
        vals = np.linspace(vmin, vmax, steps)
    elif scale == "log":
        if vmin <= 0:
            raise ValueError(f"Log sweep requires positive min for '{spec.get('name', '<unnamed>')}'")
        vals = np.logspace(np.log10(vmin), np.log10(vmax), steps)
    else:
        raise ValueError(f"Unsupported scale '{scale}'")
    return [float(v) for v in vals]


def _apply_fixed_components(editor: SpiceEditor, fixed_components: dict[str, Any]) -> None:
    for component, value in fixed_components.items():
        if isinstance(value, str):
            editor.set_component_value(component, value)
        else:
            editor.set_component_value(component, _format_value(float(value)))


def _apply_sweep_components(editor: SpiceEditor, spec: dict[str, Any], value: float) -> tuple[str, float]:
    component = str(spec["component"])
    editor.set_component_value(component, _format_value(value))

    coupled_component = spec.get("coupled_negative_of")
    if coupled_component:
        editor.set_component_value(str(coupled_component), _format_value(-value))
        return f"{component}|{coupled_component}", value

    return component, value


def _run_sweep_set(
    *,
    simulator,
    base_net: Path,
    trace_name: str,
    fixed_components: dict[str, Any],
    sweep_specs: list[dict[str, Any]],
    root_out_dir: Path,
    cfg: dict[str, Any],
) -> None:
    for sweep_index, spec in enumerate(sweep_specs):
        sweep_name = str(spec["name"])
        values = _build_values(spec)

        out_dir = root_out_dir / f"{sweep_index + 1:02d}_{sweep_name}"
        raw_dir = out_dir / "raw_runs"
        plot_dir = out_dir / "plots"
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        plot_dir.mkdir(parents=True, exist_ok=True)

        # Keep each sweep folder synchronized with the latest run only.
        _clear_directory_contents(raw_dir)
        _clear_directory_contents(plot_dir)
        csv_path = out_dir / "sweep_results.csv"
        if csv_path.exists():
            csv_path.unlink()

        runner = SimRunner(
            simulator=simulator,
            parallel_sims=int(cfg.get("parallel_sims", 1)),
            timeout=float(cfg.get("timeout_s", 300.0)),
            output_folder=str(raw_dir),
            verbose=bool(cfg.get("verbose", False)),
        )

        records: list[dict[str, Any]] = []
        total = len(values)

        # Validate that this sweep's target component(s) exist before launching all runs.
        try:
            precheck_editor = SpiceEditor(base_net)
            _apply_fixed_components(precheck_editor, fixed_components)
            _apply_sweep_components(precheck_editor, spec, values[0])
        except Exception as exc:
            records.append(
                {
                    "sweep_name": sweep_name,
                    "component": str(spec.get("component", "")),
                    "swept_value": values[0] if values else np.nan,
                    "coupled_negative_component": spec.get("coupled_negative_of", ""),
                    "coupled_negative_value": -values[0] if values and spec.get("coupled_negative_of") else np.nan,
                    "run_id": 0,
                    "status": "component_not_found",
                    "error": str(exc),
                }
            )
            df = pd.DataFrame(records)
            df.to_csv(csv_path, index=False)
            print(f"[{sweep_name}] Skipped: component not found")
            print(f"[{sweep_name}] Results CSV: {csv_path}")
            continue

        for run_id, value in enumerate(values):
            editor = SpiceEditor(base_net)
            _apply_fixed_components(editor, fixed_components)
            component_label, stored_value = _apply_sweep_components(editor, spec, value)

            run_name = f"{sweep_name}_{run_id:04d}.net"
            task = runner.run(editor, run_filename=run_name, timeout=float(cfg.get("timeout_s", 300.0)))
            if task is None:
                records.append(
                    {
                        "sweep_name": sweep_name,
                        "component": component_label,
                        "swept_value": stored_value,
                        "coupled_negative_component": spec.get("coupled_negative_of", ""),
                        "coupled_negative_value": -stored_value if spec.get("coupled_negative_of") else np.nan,
                        "run_id": run_id,
                        "status": "run_not_started",
                    }
                )
                continue

            try:
                raw_file, log_file = task.wait_results()
                raw_path = Path(raw_file)
                t, v = _get_trace(raw_path, trace_name)

                png_path = plot_dir / f"{sweep_name}_{run_id:04d}.png"
                if spec.get("coupled_negative_of"):
                    coupled_component = str(spec["coupled_negative_of"])
                    title = (
                        f"{sweep_name}: {str(spec['component'])}={stored_value:.3e}, "
                        f"{coupled_component}={-stored_value:.3e}"
                    )
                else:
                    title = f"{sweep_name}: {component_label}={stored_value:.3e}"
                _plot_waveform(t, v, png_path, title)

                records.append(
                    {
                        "sweep_name": sweep_name,
                        "component": component_label,
                        "swept_value": stored_value,
                        "coupled_negative_component": spec.get("coupled_negative_of", ""),
                        "coupled_negative_value": -stored_value if spec.get("coupled_negative_of") else np.nan,
                        "run_id": run_id,
                        "status": "ok",
                        "raw_file": str(raw_file),
                        "log_file": str(log_file),
                        "plot_file": str(png_path),
                        "manual_behavior_label": "",
                        "manual_notes": "",
                    }
                )
            except Exception as exc:
                records.append(
                    {
                        "sweep_name": sweep_name,
                        "component": component_label,
                        "swept_value": stored_value,
                        "coupled_negative_component": spec.get("coupled_negative_of", ""),
                        "coupled_negative_value": -stored_value if spec.get("coupled_negative_of") else np.nan,
                        "run_id": run_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

            if (run_id + 1) % 5 == 0 or (run_id + 1) == total:
                print(f"[{sweep_name}] Completed {run_id + 1}/{total} runs")

        df = pd.DataFrame(records)
        df.to_csv(csv_path, index=False)
        ok = int((df["status"] == "ok").sum()) if len(df) else 0
        print(f"[{sweep_name}] Finished: {ok}/{len(df)} successful")
        print(f"[{sweep_name}] Results CSV: {csv_path}")


def run(cfg: dict[str, Any]) -> Path:
    simulator = _resolve_ltspice_simulator(cfg)
    base_net = _resolve_base_circuit(cfg["base_circuit"], simulator)
    _fix_subcircuit_deltaT(base_net)

    trace_name = cfg.get("trace_name", "V(n003)")
    default_sweep_specs = cfg.get("sweeps", [])
    default_fixed_components = cfg.get("fixed_components", {})

    root_out_dir = Path(cfg.get("output_dir", "automation/results_one_by_one")).expanduser().resolve()
    root_out_dir.mkdir(parents=True, exist_ok=True)

    behavior_profiles = cfg.get("behavior_profiles", [])
    if behavior_profiles:
        for profile_idx, profile in enumerate(behavior_profiles):
            if profile.get("enabled", True) is False:
                continue

            profile_name = str(profile["name"])
            profile_dir = root_out_dir / f"{profile_idx + 1:02d}_{profile_name}"
            profile_dir.mkdir(parents=True, exist_ok=True)

            profile_fixed_components = {
                **default_fixed_components,
                **profile.get("fixed_components", {}),
            }
            profile_sweeps = profile.get("sweeps", default_sweep_specs)
            if not profile_sweeps:
                print(f"[{profile_name}] Skipped: no sweeps configured")
                continue

            print(f"Running behavior profile: {profile_name}")
            _run_sweep_set(
                simulator=simulator,
                base_net=base_net,
                trace_name=trace_name,
                fixed_components=profile_fixed_components,
                sweep_specs=profile_sweeps,
                root_out_dir=profile_dir,
                cfg=cfg,
            )
    else:
        if not default_sweep_specs:
            raise ValueError("Config must contain 'sweeps' or 'behavior_profiles'")
        _run_sweep_set(
            simulator=simulator,
            base_net=base_net,
            trace_name=trace_name,
            fixed_components=default_fixed_components,
            sweep_specs=default_sweep_specs,
            root_out_dir=root_out_dir,
            cfg=cfg,
        )

    return root_out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequential one-by-one parameter sweeps for LTspice")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("automation/config.one_by_one.example.json"),
        help="Path to JSON config for one-by-one sweeps",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)
    run(cfg)


if __name__ == "__main__":
    main()
