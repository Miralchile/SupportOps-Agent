"""Deterministic metrics used by the SupportOps offline evaluation suite."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence


def classification_metrics(expected: Sequence[str], predicted: Sequence[str]) -> Dict[str, float]:
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted must have the same length")
    if not expected:
        return {"accuracy": 0.0, "macro_f1": 0.0}

    labels = sorted(set(expected) | set(predicted))
    f1_scores = []
    correct = sum(left == right for left, right in zip(expected, predicted))
    for label in labels:
        tp = sum(left == label and right == label for left, right in zip(expected, predicted))
        fp = sum(left != label and right == label for left, right in zip(expected, predicted))
        fn = sum(left == label and right != label for left, right in zip(expected, predicted))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1_scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return {
        "accuracy": round(correct / len(expected), 4),
        "macro_f1": round(sum(f1_scores) / len(f1_scores), 4),
    }


def binary_metrics(expected: Sequence[bool], predicted: Sequence[bool]) -> Dict[str, float]:
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted must have the same length")
    tp = sum(left and right for left, right in zip(expected, predicted))
    fp = sum(not left and right for left, right in zip(expected, predicted))
    fn = sum(left and not right for left, right in zip(expected, predicted))
    tn = sum(not left and not right for left, right in zip(expected, predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    total = tp + fp + fn + tn
    return {
        "accuracy": round((tp + tn) / total, 4) if total else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_negative_rate": round(fn / (tp + fn), 4) if tp + fn else 0.0,
    }


def retrieval_metrics(cases: Iterable[Dict[str, Any]], top_k: int = 5) -> Dict[str, float]:
    recalls: List[float] = []
    reciprocal_ranks: List[float] = []
    for case in cases:
        relevant = {str(item) for item in case.get("relevant_ids", [])}
        retrieved = [str(item) for item in case.get("retrieved_ids", [])[:top_k]]
        if not relevant:
            continue
        hits = relevant.intersection(retrieved)
        recalls.append(len(hits) / len(relevant))
        rank = next((index for index, item in enumerate(retrieved, start=1) if item in relevant), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    return {
        f"recall_at_{top_k}": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else 0.0,
    }


def group_failures(cases: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    failures: Dict[str, int] = defaultdict(int)
    for case in cases:
        for failure in case.get("failures", []):
            failures[str(failure)] += 1
    return dict(sorted(failures.items(), key=lambda item: (-item[1], item[0])))
