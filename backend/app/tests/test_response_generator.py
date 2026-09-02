import unittest
from unittest.mock import patch

from service.supportops.response_generator import generate_response


class ResponseGeneratorTests(unittest.TestCase):
    @patch("service.supportops.response_generator.call_json_llm")
    def test_high_risk_refund_uses_tool_result_without_requesting_order_id(self, mock_llm):
        mock_llm.side_effect = lambda _prompt, fallback, **_kwargs: fallback

        result = generate_response(
            question="那这个还能退款吗？",
            classification={"category": "refund", "intent": "refund_request", "confidence": 0.72},
            sources=[],
            similar_tickets=[],
            escalation={"need_human": True, "risk_level": "high"},
            tool_results=[
                {
                    "tool": "check_refund_eligibility",
                    "status": "ok",
                    "order_id": "ORD345678",
                    "eligible": True,
                    "days_since_receipt": 5,
                    "window_days": 7,
                }
            ],
        )

        self.assertIn("ORD345678", result["reply"])
        self.assertIn("符合退款申请条件", result["reply"])
        self.assertNotIn("补充订单号", result["reply"])
        self.assertEqual(result["next_action"], "转人工")
        self.assertEqual(
            result["citations"],
            [{"type": "tool", "id": "check_refund_eligibility"}],
        )


if __name__ == "__main__":
    unittest.main()
