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
        raise ValueError(f"Parameter '{spec.get('name', '<unnamed>')}' requires max > min")

    scale = str(spec.get("scale", "linear")).lower()
    step = spec.get("step")

    if step is not None:
        step_val = float(step)
        if step_val <= 0:
            raise ValueError(f"Parameter '{spec.get('name', '<unnamed>')}' requires step > 0")
        if scale != "linear":
            raise ValueError(f"Parameter '{spec.get('name', '<unnamed>')}' step is only supported for linear scale")
        count = int(np.floor((vmax - vmin) / step_val + 1e-12)) + 1
        vals = [vmin + i * step_val for i in range(count)]
        if vals[-1] < vmax:
            vals.append(vmax)
        return [float(v) for v in vals]

    steps = int(spec["steps"])
    if steps < 2:
        raise ValueError(f"Parameter '{spec.get('name', '<unnamed>')}' must have steps >= 2")

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


def _enforce_voltage_coupling(
    editor: SpiceEditor,
    coupling_cfg: dict[str, Any],
    fixed_components: dict[str, Any],
    x_param: dict[str, Any],
    y_param: dict[str, Any],
    x_value: float,
    y_value: float,
) -> None:
    if not coupling_cfg.get("enabled", False):
        return

    positive_component = str(coupling_cfg.get("positive_component", "V2"))
    negative_component = str(coupling_cfg.get("negative_component", "V1"))

    assigned: dict[str, float] = {}
    assigned[str(x_param["component"])] = float(x_value)
    assigned[str(y_param["component"])] = float(y_value)
    for comp, val in fixed_components.items():
        if isinstance(val, str):
            continue
        assigned.setdefault(str(comp), float(val))

    if positive_component in assigned:
        pos_val = float(assigned[positive_component])
        editor.set_component_value(positive_component, _format_value(pos_val))
        editor.set_component_value(negative_component, _format_value(-pos_val))
    elif negative_component in assigned:
        neg_val = float(assigned[negative_component])
        editor.set_component_value(negative_component, _format_value(neg_val))
        editor.set_component_value(positive_component, _format_value(-neg_val))


def run(cfg: dict[str, Any]) -> Path:
    simulator = _resolve_ltspice_simulator(cfg)
    base_net = _resolve_base_circuit(cfg["base_circuit"], simulator)
    _fix_subcircuit_deltaT(base_net)

    out_dir = Path(cfg.get("output_dir", "automation/results_two_param")).expanduser().resolve()
    raw_dir = out_dir / "raw_runs"
    plot_dir = out_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Keep coupling output folder synchronized with latest run only.
    _clear_directory_contents(raw_dir)
    _clear_directory_contents(plot_dir)
    csv_path = out_dir / "two_param_map_results.csv"
    if csv_path.exists():
        csv_path.unlink()

    trace_name = cfg.get("trace_name", "V(n003)")
    fixed_components = cfg.get("fixed_components", {})
    voltage_coupling = cfg.get("voltage_coupling", {})

    x_param = cfg["x_param"]
    y_param = cfg["y_param"]
    x_values = _build_values(x_param)
    y_values = _build_values(y_param)

    runner = SimRunner(
        simulator=simulator,
        parallel_sims=int(cfg.get("parallel_sims", 1)),
        timeout=float(cfg.get("timeout_s", 300.0)),
        output_folder=str(raw_dir),
        verbose=bool(cfg.get("verbose", False)),
    )

    records: list[dict[str, Any]] = []
    run_id = 0
    total = len(x_values) * len(y_values)

    for x_value in x_values:
        for y_value in y_values:
            editor = SpiceEditor(base_net)
            _apply_fixed_components(editor, fixed_components)
            editor.set_component_value(str(x_param["component"]), _format_value(x_value))
            editor.set_component_value(str(y_param["component"]), _format_value(y_value))
            _enforce_voltage_coupling(
                editor,
                voltage_coupling,
                fixed_components,
                x_param,
                y_param,
                x_value,
                y_value,
            )

            run_name = f"map_{run_id:04d}.net"
            task = runner.run(editor, run_filename=run_name, timeout=float(cfg.get("timeout_s", 300.0)))
            if task is None:
                records.append(
                    {
                        "run_id": run_id,
                        "status": "run_not_started",
                        f"{x_param['name']}_value": x_value,
                        f"{y_param['name']}_value": y_value,
                    }
                )
                run_id += 1
                continue

            try:
                raw_file, log_file = task.wait_results()
                raw_path = Path(raw_file)
                t, v = _get_trace(raw_path, trace_name)

                png_path = plot_dir / f"map_{run_id:04d}.png"
                plot_title = (
                    f"{x_param['name']}={x_value:.3e}, {y_param['name']}={y_value:.3e}"
                )
                _plot_waveform(t, v, png_path, plot_title)

                records.append(
                    {
                        "run_id": run_id,
                        "status": "ok",
                        f"{x_param['name']}_value": x_value,
                        f"{y_param['name']}_value": y_value,
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
                        "run_id": run_id,
                        "status": "failed",
                        f"{x_param['name']}_value": x_value,
                        f"{y_param['name']}_value": y_value,
                        "error": str(exc),
                    }
                )

            run_id += 1
            if run_id % 10 == 0 or run_id == total:
                print(f"Completed {run_id}/{total} runs")

    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)

    ok = int((df["status"] == "ok").sum()) if len(df) else 0
    print(f"Finished two-parameter map: {ok}/{len(df)} successful")
    print(f"Results CSV: {csv_path}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Two-parameter coupling map sweep")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("automation/config.r1_c1.example.json"),
        help="Path to JSON config for two-parameter coupling map",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)
    run(cfg)


if __name__ == "__main__":
    main()
