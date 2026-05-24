# Automated LTspice Sensitivity Workflow

This folder contains a starter automation framework for your thesis extension:

- Parameter sampling (Latin Hypercube)
- LTspice runs orchestrated from Python via PyLTSpice
- Run-manifest export (`.raw` and `.log` paths per parameter set)
- CSV outputs for downstream analysis

## Why this is a new contribution

Instead of manually editing and running one case at a time, this pipeline provides reproducible LTspice control from Python and supports:

1. systematic parameter sweeps,
2. batch run orchestration,
3. reproducible artifact collection for later analysis.

## Requirements

Install the Python dependencies in your thesis virtual environment:

```powershell
c:/Users/vchat/Downloads/Vaishnavi_s_Thesis/.venv/Scripts/python.exe -m pip install PyLTSpice==5.5.1 ltspice numpy pandas
```

## Prepare LTspice Circuit

1. Use `.param` names in the netlist matching keys in `config.example.json` (example: `RL1`, `RL2`, `C1`, `C2`, `ENa`, `EK`).
2. Ensure transient simulation is defined (for example with `.tran ...`).
3. Set `base_circuit` in your config to the `.net`/`.cir` file path (or `.asc`, which will be converted to netlist).

## Run

Dry run (sampling only):

```powershell
c:/Users/vchat/Downloads/Vaishnavi_s_Thesis/.venv/Scripts/python.exe automation/run_sensitivity.py --config automation/config.example.json --dry-run
```

Full sweep:

```powershell
c:/Users/vchat/Downloads/Vaishnavi_s_Thesis/.venv/Scripts/python.exe automation/run_sensitivity.py --config automation/config.example.json
```

## C1-C2 Behavior Mapping (V(n003))

To start with the C1/C2 regime exploration and collect LTspice plots for manual comparison:

```powershell
c:/Users/vchat/Downloads/Vaishnavi_s_Thesis/.venv/Scripts/python.exe automation/run_c1_c2_map.py --config automation/config.c1_c2.example.json
```

Outputs under `automation/results_c1_c2`:

- `c1_c2_map_results.csv`: one row per C1/C2 pair
- `plots/*.png`: V(n003) waveform images for visual comparison against reference figures
- `raw_runs/*.raw` and `raw_runs/*.log`: LTspice artifacts per run

The CSV includes editable columns:

- `manual_behavior_label`
- `manual_notes`

Use those columns to annotate each run based on your provided behavior image set.

## Sequential One-By-One Sweeps (RL1, RL2, C1, C2, ENa, EK)

To sweep parameters one at a time in order (RL1, then RL2, then C1, then C2, then ENa, then EK):

```powershell
c:/Users/vchat/Downloads/Vaishnavi_s_Thesis/.venv/Scripts/python.exe automation/run_one_by_one_sweeps.py --config automation/config.one_by_one.example.json
```

The config currently uses:

- RL1: 2 kOhm to 12 kOhm
- RL2: 3 kOhm to 15 kOhm
- C1: 1 nF to 200 nF (log scale)
- C2: 0.5 nF to 20 nF (log scale)
- ENa (V1): -2.5 V to -0.5 V
- EK (V2): 0.5 V to 2.5 V

Outputs are organized per sweep under `automation/results_one_by_one`, each with:

- `sweep_results.csv`
- `plots/*.png`
- `raw_runs/*.raw` and `raw_runs/*.log`

## Two-Parameter Coupling Maps (example: R1-C1)

To run a two-parameter coupling map (RL1 vs C1):

```powershell
c:/Users/vchat/Downloads/Vaishnavi_s_Thesis/.venv/Scripts/python.exe automation/run_two_param_map.py --config automation/config.r1_c1.example.json
```

This generates:

- `two_param_map_results.csv`
- waveform plots for each RL1-C1 pair
- raw LTspice artifacts per run

You can adapt the same config pattern for other pairs like RL2-C2, ENa-EK, RL1-ENa, etc.

## Outputs

Generated under `output_dir` (default `automation/results`):

- `sampled_parameters.csv`: sampled parameter sets
- `sweep_results.csv`: per-run parameters, run status, and `.raw`/`.log` paths
- `raw_runs/`: LTspice output files per run

## Next extensions (recommended for thesis)

1. Add parameter sweeps grouped by neuron mode (tonic/phasic/mixed).
2. Add LTspice `.meas` statements in your netlist and parse `.log` files in Python.
3. Add optional plotting scripts (frequency, latency, and envelope metrics) from `.meas` outputs.
4. Add Monte Carlo local perturbations around selected operating points.
