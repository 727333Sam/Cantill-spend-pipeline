import argparse
import json
from pathlib import Path

from .config import load_config
from .pipeline import run_pipeline, write_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the config-driven Cantill spend pipeline.")
    parser.add_argument("--config", required=True, help="Company JSON config")
    parser.add_argument("--kit", required=True, help="External directory containing task data")
    parser.add_argument("--output", required=True, help="Public output CSV path")
    parser.add_argument("--audit", help="Optional private JSONL audit path")
    args = parser.parse_args()

    config = load_config(args.config)
    frame, audit = run_pipeline(args.kit, config)
    write_outputs(frame.to_dict("records"), args.output)

    if args.audit:
        audit_path = Path(args.audit)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("w", encoding="utf-8") as handle:
            for record in audit:
                handle.write(json.dumps(record, default=str) + "\n")

    print(
        f"{config['company']}: wrote {len(frame)} rows to {args.output}; "
        f"included={int(frame['include'].sum())}; excluded={int((frame['include'] == 0).sum())}"
    )


if __name__ == "__main__":
    main()
