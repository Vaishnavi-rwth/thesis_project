from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PyLTSpice import LTspice, SimRunner, SpiceEditor


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_ltspice_simulator(cfg: dict[str, Any]):
    """Resolve LTspice simulator class from config or common Windows locations."""
    ltspice_exe = (cfg.get("ltspice_exe") or "").strip()
    if ltspice_exe:
        exe = Path(ltspice_exe).expanduser().resolve()
        if not exe.exists():
            raise FileNotFoundError(
                f"Configured LTspice executable not found: {exe}. "
                "Set 'ltspice_exe' in config to a valid LTspice.exe path."
            )
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


def _resolve_base_circuit(cfg: dict[str, Any], simulator) -> Path:
    base = Path(cfg["base_circuit"]).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(f"Base circuit not found: {base}")

    if base.suffix.lower() == ".asc":
        try:
            generated_net = simulator.create_netlist(base)
            return Path(generated_net).resolve()
        except Exception as exc:
            raise RuntimeError(
                "Unable to convert .asc to netlist. LTspice executable was not found. "
                "Set 'ltspice_exe' in automation/config.example.json, or provide a .net/.cir file "
                "as 'base_circuit'."
            ) from exc

    if base.suffix.lower() not in {".net", ".cir", ".sp", ".spi"}:
        raise ValueError("base_circuit must be .asc, .net, .cir, .sp, or .spi")
    return base


def _lhs_samples(num_samples: int, bounds: dict[str, dict[str, float]], seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    names = list(bounds.keys())
    dim = len(names)
    if num_samples < 1 or dim < 1:
        raise ValueError("num_samples and number of parameters must be >= 1")

    lhs = np.zeros((num_samples, dim), dtype=float)
    for j in range(dim):
        cut = np.linspace(0.0, 1.0, num_samples + 1)
        u = rng.uniform(size=num_samples)
        points = cut[:num_samples] + u * (cut[1:] - cut[:num_samples])
        rng.shuffle(points)
        lhs[:, j] = points

    samples = {}
    for j, name in enumerate(names):
        low = float(bounds[name]["min"])
        high = float(bounds[name]["max"])
        if not high > low:
            raise ValueError(f"Invalid bounds for {name}: min={low}, max={high}")

        scale = bounds[name].get("scale", "linear").lower()
        if scale == "linear":
            samples[name] = low + (high - low) * lhs[:, j]
        elif scale == "log":
            if low <= 0:
                raise ValueError(f"Log scale requires positive min for {name}")
            samples[name] = np.exp(np.log(low) + (np.log(high) - np.log(low)) * lhs[:, j])
        else:
            raise ValueError(f"Unsupported scale '{scale}' for {name}")

    return pd.DataFrame(samples)


def _format_for_spice(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("Non-finite parameter value encountered")
    return f"{value:.10g}"


def run(cfg: dict[str, Any], dry_run: bool = False) -> Path:
    out_dir = Path(cfg.get("output_dir", "automation/results")).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    simulator = _resolve_ltspice_simulator(cfg)

    base_net: Path | None = None
    if not dry_run:
        base_net = _resolve_base_circuit(cfg, simulator)
    sampling = cfg.get("sampling", {})
    param_bounds = cfg["parameters"]
    samples = _lhs_samples(
        num_samples=int(sampling.get("num_samples", 50)),
        bounds=param_bounds,
        seed=int(sampling.get("seed", 1234)),
    )

    samples_csv = out_dir / "sampled_parameters.csv"
    samples.to_csv(samples_csv, index=False)
    if dry_run:
        print(f"Dry run complete. Parameter table written to: {samples_csv}")
        return out_dir

    runner = SimRunner(
        simulator=simulator,
        parallel_sims=int(cfg.get("parallel_sims", 1)),
        timeout=float(cfg.get("timeout_s", 300.0)),
        output_folder=str(out_dir / "raw_runs"),
        verbose=bool(cfg.get("verbose", False)),
    )

    records: list[dict[str, Any]] = []
    for i, row in samples.iterrows():
        editor = SpiceEditor(base_net)
        row_dict = row.to_dict()
        for name, val in row_dict.items():
            editor.set_parameter(name, _format_for_spice(float(val)))

        run_name = f"run_{i:04d}.net"
        task = runner.run(editor, run_filename=run_name, timeout=float(cfg.get("timeout_s", 300.0)))
        if task is None:
            rec = {**row_dict, "run_id": i, "status": "run_not_started"}
            records.append(rec)
            continue

        try:
            raw_file, log_file = task.wait_results()
            rec = {
                **row_dict,
                "run_id": i,
                "status": "ok",
                "raw_file": str(raw_file),
                "log_file": str(log_file),
            }
        except Exception as exc:
            rec = {
                **row_dict,
                "run_id": i,
                "status": "failed",
                "error": str(exc),
            }
        records.append(rec)

        if (i + 1) % 10 == 0:
            print(f"Completed {i + 1}/{len(samples)} runs")

    df = pd.DataFrame(records)
    all_csv = out_dir / "sweep_results.csv"
    df.to_csv(all_csv, index=False)

    print(f"Finished. Results written to: {all_csv}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated LTspice sensitivity sweep")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("automation/config.example.json"),
        help="Path to JSON configuration file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only generate and export the sampled parameter table",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)
    run(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
