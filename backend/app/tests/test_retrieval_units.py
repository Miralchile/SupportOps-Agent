import unittest

from service.retrieval.doc_parser import chunk_text, is_supported_file
from service.retrieval.search import hybrid_search
from service.retrieval.text_utils import fine_grained_tokenize, tokenize


class TextUtilsTest(unittest.TestCase):
    def test_tokenize_mixed_language(self):
        tokens = tokenize("支付失败怎么办 Payment FAILED")
        self.assertIn("支付", tokens)
        self.assertIn("payment", tokens)
        self.assertIn("failed", tokens)

    def test_tokenize_drops_punctuation_and_empty(self):
        self.assertEqual(tokenize("！！！。。。"), "")
        self.assertEqual(tokenize(None), "")

    def test_fine_grained_splits_long_words(self):
        tokens = fine_grained_tokenize("中华人民共和国")
        self.assertIn("共和国", tokens.split())


class ChunkTextTest(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("   \n  "), [])

    def test_short_text_single_chunk(self):
        self.assertEqual(chunk_text("退款处理指南"), ["退款处理指南"])

    def test_long_text_respects_max_chars(self):
        text = "退款问题请先核对订单号。" * 200
        chunks = chunk_text(text, max_chars=100, overlap=20)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))

    def test_paragraphs_are_merged(self):
        chunks = chunk_text("第一段。\n\n第二段。", max_chars=100)
        self.assertEqual(len(chunks), 1)
        self.assertIn("第一段", chunks[0])
        self.assertIn("第二段", chunks[0])


class SupportedFileTest(unittest.TestCase):
    def test_supported_extensions(self):
        for name in ("faq.pdf", "manual.DOCX", "note.txt", "guide.md"):
            self.assertTrue(is_supported_file(name), name)
        for name in ("slides.pptx", "sheet.xlsx", "archive.zip", "noext"):
            self.assertFalse(is_supported_file(name), name)


class HybridSearchGuardTest(unittest.TestCase):
    def test_blank_question_returns_empty_without_es(self):
        # Must not raise even when Elasticsearch is unreachable.
        self.assertEqual(hybrid_search("supportops_docs_test", "   "), [])


if __name__ == "__main__":
    unittest.main()
