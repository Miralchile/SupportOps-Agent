"""编辑工单时的字段重算逻辑（纯函数，离线可测）。"""

import unittest

from service.supportops.data_quality import revised_ticket_fields, ticket_content_hash


class RevisedTicketFieldsTest(unittest.TestCase):
    def test_recomputes_governance_fields(self):
        fields = revised_ticket_fields(
            "订单一直没有发货，请帮我查一下进度",
            "已为您催促仓库，预计 24 小时内更新物流信息。",
        )
        self.assertEqual(fields["language"], "zh")
        self.assertFalse(fields["pii_redacted"])
        self.assertEqual(
            fields["content_hash"],
            ticket_content_hash(fields["instruction"], fields["response"]),
        )
        self.assertGreater(fields["quality_score"], 0)

    def test_redacts_pii_on_edit(self):
        fields = revised_ticket_fields(
            "请联系我 user@example.com 处理退款",
            "好的，我们会发送确认邮件到您的邮箱。",
        )
        self.assertTrue(fields["pii_redacted"])
        self.assertIn("[EMAIL]", fields["instruction"])
        self.assertNotIn("user@example.com", fields["instruction"])

    def test_content_hash_tracks_text_changes(self):
        before = revised_ticket_fields("如何开发票", "请在个人中心申请开票。")
        after = revised_ticket_fields("如何开发票", "请在订单详情页点击申请开票。")
        self.assertNotEqual(before["content_hash"], after["content_hash"])

    def test_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            revised_ticket_fields("", "回复不能配空问题")
        with self.assertRaises(ValueError):
            revised_ticket_fields("问题不能配空回复", "   ")

    def test_strips_markup_like_import_path(self):
        fields = revised_ticket_fields(
            "<p>账号无法登录</p>",
            "请尝试<strong>重置密码</strong>后再登录。",
        )
        self.assertNotIn("<", fields["instruction"])
        self.assertNotIn("<", fields["response"])


if __name__ == "__main__":
    unittest.main()
