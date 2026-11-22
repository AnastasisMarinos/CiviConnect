"""Regression checks for assessing municipal claims without external API calls."""
import unittest
from unittest.mock import patch

from civiconnect.search import verification
from civiconnect.search.topic_ranker import ClaimCheck, validate_check


class VerificationTests(unittest.TestCase):
    def test_approval_does_not_verify_completion(self):
        decision = {"id": "ada:1", "kind": "decision", "approval": True, "completion": False}
        check = ClaimCheck(claim="Το έργο ολοκληρώθηκε", stage="implementation",
                           assessment="supported", source_numbers=[1])
        self.assertEqual(validate_check(check, [decision])["assessment"], "partial")
        check.stage = "approval"
        self.assertEqual(validate_check(check, [decision])["assessment"], "supported")

    def test_title_alone_does_not_verify_approval(self):
        decision = {"id": "ada:1", "kind": "decision", "scope": "metadata"}
        check = ClaimCheck(claim="Το έργο εγκρίθηκε", stage="approval",
                           assessment="supported", source_numbers=[1])
        self.assertEqual(validate_check(check, [decision])["assessment"], "partial")

    def test_missing_reference_does_not_verify(self):
        check = ClaimCheck(claim="Το έργο ολοκληρώθηκε", stage="implementation",
                           assessment="supported", source_numbers=[22])
        self.assertEqual(validate_check(check, [])["assessment"], "unconfirmed")

    def test_news_discovery_kept_separate_from_evidence(self):
        headline = {"source": "https://news.google.com/rss/articles/one", "title": "Νέοι κάδοι στον Δήμο"}
        with (patch.object(verification, "decisions", side_effect=TimeoutError) as official,
              patch.object(verification, "headlines", return_value=[headline]) as news,
              patch.object(verification, "reporting", return_value=[])):
            records, links, coverage = verification.lookup(
                "Καθαριότητα και απορρίμματα", "My private street address", "2025-11-21", "2026-11-21"
            )
        self.assertEqual(records, [])
        self.assertEqual(links, [headline])
        self.assertEqual(coverage["decision"], "unavailable")
        self.assertEqual(official.call_args.args[0], "απορρίμματα")
        self.assertEqual(news.call_args.args[0], "απορρίμματα")

    def test_duplicate_headlines_collapsed(self):
        title = "Ο Δήμος Αθηναίων προμηθεύεται νέους υπόγειους κάδους"
        common = {"title": title, "source": "https://example.com/first"}
        copy = dict(common, source="https://example.org/second")
        self.assertEqual(verification.distinct_stories([common, copy]), [common])


if __name__ == "__main__":
    unittest.main()
