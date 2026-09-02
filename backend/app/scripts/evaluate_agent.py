#!/usr/bin/env python3
"""Run a deterministic end-to-end SupportOps scenario benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import types
import uuid
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from service.supportops.agent_benchmark import aggregate_results, evaluate_turn
from service.supportops.api_key_context import use_api_key_config
from service.supportops import workflow


class FakeDB:
    def close(self) -> None:
        pass


def load_scenarios(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end SupportOps Agent benchmark")
    parser.add_argument("--dataset", type=Path, default=APP_ROOT / "evals" / "supportops_agent_scenarios.jsonl")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-task-success", type=float, default=0.8)
    args = parser.parse_args()

    support_agent = types.ModuleType("service.supportops.support_agent")
    support_agent.search_support_docs = lambda *_: [
        {"document_id": "faq-1", "document_name": "benchmark_faq", "content": "请按帮助中心步骤操作。", "score": 0.9}
    ]
    support_agent._write_final_to_history = lambda *_: None
    similar = types.ModuleType("service.supportops.similar_ticket_search")
    similar.search_similar_tickets = lambda *_, **__: []

    rows = []
    with use_api_key_config({"api_key": ""}), mock.patch.dict(sys.modules, {
        "service.supportops.support_agent": support_agent,
        "service.supportops.similar_ticket_search": similar,
    }), mock.patch.object(workflow, "_record_trace", lambda *_: None):
        for scenario in load_scenarios(args.dataset):
            graph = workflow.build_supportops_graph(InMemorySaver())
            config = {"configurable": {"thread_id": f"bench:{scenario['id']}:{uuid.uuid4().hex[:8]}"}}
            context = workflow.SupportOpsRuntimeContext(db_factory=FakeDB, max_retries=0)
            for turn_index, turn in enumerate(scenario["turns"]):
                events = list(graph.stream(
                    workflow.new_turn_state("benchmark", scenario["id"], turn["message"]),
                    config,
                    context=context,
                    stream_mode="updates",
                ))
                if any("__interrupt__" in event for event in events):
                    list(graph.stream(
                        Command(resume={"action": "approve", "reviewer_note": "benchmark"}),
                        config,
                        context=context,
                        stream_mode="updates",
                    ))
                final = graph.get_state(config).values.get("final_answer") or {}
                score = evaluate_turn(final, turn["expected"])
                rows.append({
                    "scenario": scenario["id"],
                    "turn": turn_index + 1,
                    "score": score,
                    "actual": {
                        "category": final.get("category"),
                        "intent": final.get("intent"),
                        "tools": [item.get("tool") for item in final.get("tool_results") or []],
                        "next_action": final.get("next_action"),
                    },
                })

    report = {"summary": aggregate_results(item["score"] for item in rows), "results": rows}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["summary"]["task_success_rate"] >= args.min_task_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
