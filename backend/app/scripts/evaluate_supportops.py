#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from service.supportops.escalation_checker import check_escalation
from service.supportops.evaluation import binary_metrics, classification_metrics
from service.supportops.intent_classifier import classify_intent


def load_cases(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SupportOps offline intent/risk evaluation")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=APP_ROOT / "evals" / "supportops_cases.jsonl",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    predictions = []
    for case in cases:
        classification = classify_intent(case["question"])
        escalation = check_escalation(case["question"], classification, [], [])
        predictions.append({
            "id": case["id"],
            "category": classification["category"],
            "intent": classification["intent"],
            "need_human": escalation["need_human"],
        })

    report = {
        "cases": len(cases),
        "category": classification_metrics(
            [case["category"] for case in cases],
            [item["category"] for item in predictions],
        ),
        "intent": classification_metrics(
            [case["intent"] for case in cases],
            [item["intent"] for item in predictions],
        ),
        "escalation": binary_metrics(
            [case["need_human"] for case in cases],
            [item["need_human"] for item in predictions],
        ),
        "predictions": predictions,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
