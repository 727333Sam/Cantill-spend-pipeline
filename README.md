# Cantill Spend Data Pipeline

This repository contains a local, config-driven spend pipeline for the Cantill.ai Data & ML Intern challenge.

## What is included

The repository includes the Python package, company configurations, tests, documentation, and the required A/B submission outputs. The confidential task kit is **not** included.

The A/B commands require the task kit supplied separately by Cantill.ai, extracted into a directory with this layout:

```text
<kit>/
  company_A/
    erp_goods_receipts.csv
    invoice_tool_export.csv
    labels_A.csv
    taxonomy_A.csv
  company_B/
    invoice_lines.csv
    fx_rates_usd.csv
    seed_labels.csv
    taxonomy_B.csv
```

Keep that directory outside the cloned repository. The CLI resolves all configured input files relative to the `--kit` path using `pathlib`.

## Requirements

- Python 3.10 or newer
- Internet access once to install packages from PyPI, unless dependencies are already available
- The confidential task kit for real Company A/B runs

The runtime dependencies are declared in `pyproject.toml`: `pandas` and `scikit-learn`. Test dependencies add `pytest`.

## Clone and install

### Windows PowerShell

```powershell
git clone <repository-url>
cd <repository-directory>
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

If PowerShell blocks activation, run the commands from an activated Python environment or use:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

### Linux/macOS

```bash
git clone <repository-url>
cd <repository-directory>
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

All commands below assume they are run from the repository root with the virtual environment active. Use `python -m ...`, so the commands work on both Windows and Linux/macOS.

## Run the tests

The tests create small synthetic inputs in temporary directories and do not require the confidential kit:

```bash
python -m pytest -q
```

Expected result for the validated repository: 11 passed.

## Run Company A

Replace `<KIT_DIR>` with the external task-kit directory. On Windows, use a path such as `C:\data\Cantill_DataML_Task_Kit`; on Linux/macOS, use `/data/Cantill_DataML_Task_Kit`.

```bash
python -m cantill_pipeline.cli \
  --config configs/company_a.json \
  --kit "<KIT_DIR>" \
  --output "outputs/<yourname>__A.csv" \
  --audit "outputs/A.audit.jsonl"
```

PowerShell accepts the same command as one line:

```powershell
python -m cantill_pipeline.cli --config configs/company_a.json --kit "C:\data\Cantill_DataML_Task_Kit" --output "outputs\yourname__A.csv" --audit "outputs\A.audit.jsonl"
```

## Run Company B

```bash
python -m cantill_pipeline.cli \
  --config configs/company_b.json \
  --kit "<KIT_DIR>" \
  --output "outputs/<yourname>__B.csv" \
  --audit "outputs/B.audit.jsonl"
```

PowerShell example:

```powershell
python -m cantill_pipeline.cli --config configs/company_b.json --kit "C:\data\Cantill_DataML_Task_Kit" --output "outputs\yourname__B.csv" --audit "outputs\B.audit.jsonl"
```

The CLI creates the `outputs/` directory automatically. The public CSV has exactly:

```text
record_id,include,exclusion_reason,supplier_key,item_key,spend,l1,l2,l3,l4,confidence
```

The optional JSONL audit file contains internal parsing, FX, matching, and decision fields. `outputs/` and audit files are ignored by Git. The required final submission files are kept separately in `submission/`.

## Company C / future company

Copy `configs/company_c.example.json` to a new config, map the invoice, optional FX, and taxonomy columns, and run the same CLI. No taxonomy category names or C-specific production code are required:

```bash
python -m cantill_pipeline.cli \
  --config configs/company_c.json \
  --kit "<EXTERNAL_C_DIR>" \
  --output "submission/<yourname>__C.csv"
```

## Important privacy rule

Do not copy the brief, raw CSV inputs, seed labels, FX data, taxonomies, or audit outputs into the repository. The `.gitignore` excludes common task-data, environment, cache, temporary, credential, and runtime-output locations. The committed A/B CSVs are submission artifacts, not raw input data.
