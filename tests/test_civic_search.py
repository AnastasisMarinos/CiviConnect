"""Regression questions for the Athens search index (no Gemini calls)."""
import re
import unittest
from unittest.mock import patch

from civiconnect import storage as db
from civiconnect.opencouncil.evidence import window
from civiconnect.search import civic_index, topic_ranker
from civiconnect.search.civic_index import INDEX_FILE, normalize
from civiconnect.search.topic_ranker import diverse_excerpts, lexical_fallback, retrieve


class LocalRelevanceTests(unittest.TestCase):
    def test_nightlife_without_hybrid_index(self):
        noise = {"id": "noise", "title": "Ωράριο μουσικής", "date": "2026-02-01",
                 "kind": "summary", "text": "Εξετάστηκαν καταγγελίες για ηχορύπανση από τα μπαρ."}
        earthquake = dict(noise, id="earthquake", title="Σεισμοί",
                          text="Το σπίτι δίπλα στο σχολείο χρειάζεται αντισεισμικό έλεγχο.")
        question = "το club διπλα απο το σπιτι μου δεν με αφηνει να κοιμηθω"
        label, result = lexical_fallback([noise, earthquake], question, "2025-11-21", "2026-11-21")
        self.assertIn("Νυχτερινός θόρυβος", label)
        self.assertEqual([row["id"] for row in result], ["noise"])

    def test_topic_hints_allow_an_indirect_second_issue(self):
        lighting = {"id": "lighting", "title": "Δημοτικός φωτισμός", "date": "2026-02-01",
                    "kind": "summary", "text": "Αντικατάσταση φωτιστικών στους δρόμους."}
        waste = dict(lighting, id="waste", title="Αποκομιδή απορριμμάτων",
                     text="Το θέμα είναι η συχνότητα αποκομιδής απορριμμάτων.")
        unrelated = dict(lighting, id="unrelated", title="Εθελοντισμός", text="Εθελοντική αιμοδοσία.")
        candidates = [(waste, .89, True, True), (lighting, .87, False, False),
                      (unrelated, .76, False, False)]
        with (patch.object(civic_index, "candidates", return_value=candidates),
              patch.object(topic_ranker, "infer_topics", return_value=[])):
            label, result = retrieve("Σκουπίδια παντού και ο δρόμος μαυρίζει μόλις πέσει ο ήλιος.",
                                     "2025-11-21", "2026-11-21")
        self.assertIn("Καθαριότητα", label)
        self.assertEqual({row["id"] for row in result}, {"waste", "lighting"})


@unittest.skipUnless((db.DATA / INDEX_FILE).is_file(), "Build the Athens search index first.")
class AthensRelevanceTests(unittest.TestCase):
    def test_relevant_evidence_in_first_five(self):
        cases = [
            ("το club διπλα απο το σπιτι μου δεν με αφηνει να κοιμηθω", r"ηχορυπ|μουσικ|ηχοεντασ"),
            ("The nightclub next door is too loud and I cannot sleep", r"ηχορυπ|μουσικ|ηχοεντασ"),
            ("θωριβος απο το κλαμπ τη νυχτα", r"ηχορυπ|μουσικ|ηχοεντασ"),
            ("who is working on garbage collection?", r"απορριμ|αποκομιδ|ανακυκλ"),
            ("My wheelchair can't get up onto the curb", r"πεζοδρομ|ραμπ|προσβασ"),
            ("The street goes pitch black when the sun sets", r"φωτισμ|φωτιστικ"),
            ("τι αποφάσισαν για ωράριο μουσικής στην Αγίου Μάρκου 16", r"αγιου μαρκου 16"),
        ]
        for question, expected in cases:
            with self.subTest(question=question):
                _, rows = retrieve(question, *window())
                top = diverse_excerpts(rows)[:5]
                text = [normalize(row["title"] + " " + row["text"]) for row in top]
                self.assertTrue(any(re.search(expected, passage) for passage in text), text)
                if "club" in question or "κλαμπ" in question:
                    self.assertTrue(all("αντισεισμ" not in passage for passage in text))

    def test_abstains_for_vague_or_unrelated_questions(self):
        for question in ("το σπιτι μου ειναι διπλα", "What is tomorrow's winning lottery number?"):
            with self.subTest(question=question):
                self.assertEqual(retrieve(question, *window())[1], [])

    def test_mixed_topic_shortlist_covers_both_issues(self):
        label, rows = retrieve("Σκουπίδια παντού και ο δρόμος μαυρίζει μόλις πέσει ο ήλιος.", *window())
        self.assertIn("Καθαριότητα", label)
        self.assertIn("Δημοτικός φωτισμός", label)
        labels = {label for row in diverse_excerpts(rows)[:5] for label in row["search_topics"]}
        self.assertIn("Καθαριότητα και απορρίμματα", labels)
        self.assertIn("Δημοτικός φωτισμός", labels)


if __name__ == "__main__":
    unittest.main()
