import unittest

from service.supportops.evaluation import binary_metrics, classification_metrics, retrieval_metrics


class EvaluationMetricsTest(unittest.TestCase):
    def test_classification_metrics(self):
        result = classification_metrics(["a", "a", "b"], ["a", "b", "b"])
        self.assertAlmostEqual(result["accuracy"], 0.6667)
        self.assertGreater(result["macro_f1"], 0.6)

    def test_binary_metrics_exposes_false_negative_rate(self):
        result = binary_metrics([True, True, False, False], [True, False, True, False])
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["false_negative_rate"], 0.5)

    def test_retrieval_metrics(self):
        result = retrieval_metrics([
            {"relevant_ids": ["d2"], "retrieved_ids": ["d1", "d2"]},
            {"relevant_ids": ["d3"], "retrieved_ids": ["d3"]},
        ])
        self.assertEqual(result["recall_at_5"], 1.0)
        self.assertEqual(result["mrr"], 0.75)


if __name__ == "__main__":
    unittest.main()
