from __future__ import annotations

import argparse
import json
import os
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


def run(cfg: dict[str, Any]) -> Path:
    simulator = _resolve_ltspice_simulator(cfg)

    out_dir = Path(cfg.get("output_dir", "automation/results_c1_c2")).expanduser().resolve()
    raw_dir = out_dir / "raw_runs"
    plot_dir = out_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    base_net = _resolve_base_circuit(cfg["base_circuit"], simulator)
    trace_name = cfg.get("trace_name", "V(n003)")
    c1_component = cfg.get("c1_component", "C1")
    c2_component = cfg.get("c2_component", "C2")

    c1_values = [float(v) for v in cfg["c1_values_f"]]
    c2_values = [float(v) for v in cfg["c2_values_f"]]

    runner = SimRunner(
        simulator=simulator,
        parallel_sims=int(cfg.get("parallel_sims", 1)),
        timeout=float(cfg.get("timeout_s", 300.0)),
        output_folder=str(raw_dir),
        verbose=bool(cfg.get("verbose", False)),
    )

    records: list[dict[str, Any]] = []
    run_id = 0
    total = len(c1_values) * len(c2_values)

    for c1 in c1_values:
        for c2 in c2_values:
            editor = SpiceEditor(base_net)
            editor.set_component_value(c1_component, f"{c1:.10g}")
            editor.set_component_value(c2_component, f"{c2:.10g}")

            run_name = f"c1c2_{run_id:04d}.net"
            task = runner.run(editor, run_filename=run_name, timeout=float(cfg.get("timeout_s", 300.0)))
            if task is None:
                records.append(
                    {
                        "run_id": run_id,
                        "status": "run_not_started",
                        "C1_F": c1,
                        "C2_F": c2,
                    }
                )
                run_id += 1
                continue

            try:
                raw_file, log_file = task.wait_results()
                raw_path = Path(raw_file)
                t, v = _get_trace(raw_path, trace_name)

                png_name = f"c1c2_{run_id:04d}.png"
                png_path = plot_dir / png_name
                _plot_waveform(t, v, png_path, f"C1={c1:.3e} F, C2={c2:.3e} F")

                records.append(
                    {
                        "run_id": run_id,
                        "status": "ok",
                        "C1_F": c1,
                        "C2_F": c2,
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
                        "C1_F": c1,
                        "C2_F": c2,
                        "error": str(exc),
                    }
                )

            run_id += 1
            if run_id % 10 == 0:
                print(f"Completed {run_id}/{total} runs")

    df = pd.DataFrame(records)
    csv_path = out_dir / "c1_c2_map_results.csv"
    df.to_csv(csv_path, index=False)

    ok = int((df["status"] == "ok").sum()) if len(df) else 0
    print(f"Finished C1-C2 map runs: {ok}/{len(df)} successful")
    print(f"Results CSV: {csv_path}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="C1-C2 map sweep for V(n003) capture")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("automation/config.c1_c2.example.json"),
        help="Path to JSON config for C1-C2 sweep",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)
    run(cfg)


if __name__ == "__main__":
    main()
