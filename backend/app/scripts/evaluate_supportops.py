#!/usr/bin/env python3
"""Offline intent / escalation evaluation.

Runs the intent classifier and escalation checker over the labeled case set
and reports classification and escalation metrics, sliced by case tag:

- ``keyword``:    rule keywords present and aligned with the label
- ``paraphrase``: no rule keyword; requires semantic understanding
- ``trap``:       rule keywords present but misleading (measures rule FPs)

Modes:
- ``rules``: force the deterministic fallback path (no LLM calls)
- ``llm``:   use the configured DashScope key (fails over to rules per call
             if the key is missing/invalid, as in production)
- ``both``:  run rules first, then llm if a valid key is configured

Intent labels are evaluated as a closed set: the label inventory from the
case file is passed to the classifier as ``known_labels``, mirroring how the
production flow feeds labels from similar tickets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from service.supportops.api_key_context import use_api_key_config
from service.supportops.escalation_checker import check_escalation
from service.supportops.evaluation import binary_metrics, classification_metrics
from service.supportops.intent_classifier import classify_intent
from service.supportops.tools import has_valid_dashscope_key


def _probe_llm(api_config: Dict[str, Any] | None) -> bool:
    """One real round-trip: a wrong/expired key must fail loudly here instead
    of silently degrading every llm-mode call to the rules fallback."""
    if api_config and not has_valid_dashscope_key(api_config.get("api_key")):
        return False
    if not api_config and not has_valid_dashscope_key():
        return False
    from service.supportops.tools import call_json_llm

    with use_api_key_config(api_config):
        result = call_json_llm('请只输出 JSON：{"ok": true}', {"ok": False})
    return bool(isinstance(result, dict) and result.get("ok"))


def load_cases(path: Path) -> List[Dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for case in cases:
        case.setdefault("tag", "untagged")
    return cases


def run_mode(cases: List[Dict[str, Any]], mode: str, api_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    known_labels = []
    seen = set()
    for case in cases:
        key = (case["category"], case["intent"])
        if key not in seen:
            known_labels.append({"category": case["category"], "intent": case["intent"]})
            seen.add(key)

    # ``rules`` mode injects an empty runtime API key so every call_json_llm
    # falls back deterministically — the exact no-key production path.
    # ``llm`` mode uses the user's stored key (same resolution as production)
    # when --user-id is given, otherwise the environment key.
    context = use_api_key_config({"api_key": ""}) if mode == "rules" else use_api_key_config(api_config)

    predictions = []
    with context:
        for case in cases:
            classification = classify_intent(case["question"], known_labels)
            escalation = check_escalation(case["question"], classification, [], [])
            predictions.append(
                {
                    "id": case["id"],
                    "tag": case["tag"],
                    "category": classification["category"],
                    "intent": classification["intent"],
                    "need_human": escalation["need_human"],
                    "risk_level": escalation["risk_level"],
                }
            )

    report: Dict[str, Any] = {
        "mode": mode,
        "cases": len(cases),
        "category": classification_metrics(
            [c["category"] for c in cases], [p["category"] for p in predictions]
        ),
        "intent": classification_metrics(
            [c["intent"] for c in cases], [p["intent"] for p in predictions]
        ),
        "escalation": binary_metrics(
            [c["need_human"] for c in cases], [p["need_human"] for p in predictions]
        ),
        "escalation_by_tag": {},
        "failures": [],
    }

    tags = sorted({c["tag"] for c in cases})
    for tag in tags:
        subset = [(c, p) for c, p in zip(cases, predictions) if c["tag"] == tag]
        report["escalation_by_tag"][tag] = {
            "cases": len(subset),
            **binary_metrics([c["need_human"] for c, _ in subset], [p["need_human"] for _, p in subset]),
        }

    for case, pred in zip(cases, predictions):
        wrong = []
        if case["category"] != pred["category"]:
            wrong.append(f"category {case['category']}->{pred['category']}")
        if case["need_human"] != pred["need_human"]:
            wrong.append(f"need_human {case['need_human']}->{pred['need_human']}")
        if wrong:
            report["failures"].append({"id": case["id"], "tag": case["tag"], "errors": wrong})

    return report


def render_summary(reports: List[Dict[str, Any]]) -> str:
    lines = ["", "| mode | category acc / macro-F1 | intent acc | escalation P / R / F1 | FNR |", "|---|---|---|---|---|"]
    for r in reports:
        e = r["escalation"]
        lines.append(
            f"| {r['mode']} | {r['category']['accuracy']} / {r['category']['macro_f1']} "
            f"| {r['intent']['accuracy']} "
            f"| {e['precision']} / {e['recall']} / {e['f1']} | {e['false_negative_rate']} |"
        )
    lines.append("")
    for r in reports:
        lines.append(f"escalation by tag ({r['mode']}): " + json.dumps(
            {tag: {"recall": v["recall"], "precision": v["precision"], "n": v["cases"]}
             for tag, v in r["escalation_by_tag"].items()},
            ensure_ascii=False,
        ))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="SupportOps offline intent/risk evaluation")
    parser.add_argument("--dataset", type=Path, default=APP_ROOT / "evals" / "supportops_cases.jsonl")
    parser.add_argument("--mode", choices=("rules", "llm", "both"), default="both")
    parser.add_argument("--user-id", help="从数据库读取该用户的 active API Key（与生产一致的解析链路）")
    parser.add_argument("--output", type=Path, help="write the full JSON report to this path")
    args = parser.parse_args()

    api_config = None
    if args.user_id:
        from service.supportops.api_key_service import get_active_api_key_config
        from utils.database import SessionLocal

        db = SessionLocal()
        try:
            api_config = get_active_api_key_config(db, str(args.user_id))
        finally:
            db.close()
        if not api_config:
            print(f"[warn] 用户 {args.user_id} 没有 active API Key")

    cases = load_cases(args.dataset)
    modes = ["rules", "llm"] if args.mode == "both" else [args.mode]
    if "llm" in modes and not _probe_llm(api_config):
        print("[warn] LLM 探活失败（API Key 缺失或无效），跳过 llm 模式（仅运行 rules）")
        modes = [m for m in modes if m != "llm"] or ["rules"]

    reports = [run_mode(cases, mode, api_config) for mode in modes]
    print(render_summary(reports))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"reports": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nfull report -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
