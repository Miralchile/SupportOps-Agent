import json
import unittest

from service.supportops.data_quality import canonical_record, deterministic_split, redact_pii
from service.supportops.dataset_adapters import MSDialogAdapter, SupportOpsCsvAdapter, TweetSummAdapter


class DataQualityTest(unittest.TestCase):
    def test_redacts_common_pii(self):
        text, counts = redact_pii("Email me at person@example.com or +1 415 555 1212")
        self.assertIn("[EMAIL]", text)
        self.assertIn("[PHONE]", text)
        self.assertEqual(counts["email"], 1)

    def test_conversation_split_is_deterministic(self):
        self.assertEqual(deterministic_split("dialog-42"), deterministic_split("dialog-42"))

    def test_canonical_record_tracks_provenance(self):
        record = canonical_record(
            instruction="My account email is user@example.com",
            response="We sent a reset link to user@example.com",
            category="Account",
            intent="Password Reset",
            source="fixture",
            source_type="real_anonymized",
            external_id="42",
        )
        self.assertTrue(record["pii_redacted"])
        self.assertEqual(record["source_type"], "real_anonymized")
        self.assertEqual(len(record["content_hash"]), 64)


class DatasetAdapterTest(unittest.TestCase):
    def test_legacy_csv_remains_compatible(self):
        content = b"instruction,category,intent,response\nHow do I reset?,account,password_reset,Use settings\n"
        result = SupportOpsCsvAdapter().adapt(content, "legacy.csv")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["source_type"], "user_provided")

    def test_msdialog_uses_selected_answer_and_preserves_dialog_metadata(self):
        payload = {
            "20481": {
                "category": "Word",
                "title": "Spacing issue",
                "utterances": [
                    {"utterance_pos": 1, "actor_type": "User", "utterance": "How can I fix paragraph spacing?", "tags": "OQ"},
                    {"utterance_pos": 2, "actor_type": "Agent", "utterance": "Try the layout menu.", "is_answer": 0},
                    {"utterance_pos": 3, "actor_type": "Agent", "utterance": "Use Paragraph settings and reset spacing.", "is_answer": 1, "affiliation": "MVP"},
                ],
            }
        }
        result = MSDialogAdapter().adapt(json.dumps(payload).encode(), "msdialog.json")
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertIn("reset spacing", record["response"])
        self.assertEqual(record["source_type"], "real_anonymized")
        self.assertEqual(record["conversation_id"], "20481")
        self.assertTrue(record["metadata_json"]["selected_answer"])

    def test_tweetsumm_is_marked_real_derived_and_keeps_official_split(self):
        payload = {
            "conversation_id": "tweet-1",
            "annotations": [{"abstractive": ["Customer cannot update the watchlist.", "Agent recommends opening the show page."]}],
        }
        result = TweetSummAdapter().adapt((json.dumps(payload) + "\n").encode(), "final_test_tweetsum.jsonl")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["source_type"], "real_derived")
        self.assertEqual(result.records[0]["dataset_split"], "test")
        self.assertTrue(result.records[0]["metadata_json"]["derived_from_real_dialog"])


if __name__ == "__main__":
    unittest.main()
