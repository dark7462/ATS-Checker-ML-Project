import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from matcher import extract_items, focus_jd_text, read_jd, read_resume_pdf, score


def item(label, canonical=None, kind="skill", vector=None):
    return {"label": label, "canonical": canonical or label.lower(), "kind": kind, "vector": vector or [1.0, 0.0]}


class MatcherTests(unittest.TestCase):
    def test_three_skill_example(self):
        jd = [item("React.js", "react"), item("AWS", "aws"), item("Express", "express")]
        resume = [item("React", "react"), item("Azure", "azure"), item("Express", "express")]
        result = score(jd, resume)
        self.assertEqual((result["points"], result["total"], result["score"]), (2.5, 3, 83.33))

    def test_aliases_and_duplicate_jd(self):
        extracted = extract_items("React.js, AWS, Express\nReact, AWS, Express")
        self.assertEqual({x["canonical"] for x in extracted}, {"react", "aws", "express"})
        result = score(extracted + [extracted[0]], [item("React", "react"), item("AWS", "aws"), item("Express", "express")])
        self.assertEqual(result["score"], 100)

    def test_exact_reserved_before_partial(self):
        result = score([item("AWS", "aws"), item("Azure", "azure")], [item("Azure", "azure")])
        self.assertEqual(result["points"], 1)
        self.assertEqual(result["matched"][0]["jd"], "Azure")

    def test_vector_suggestion_has_no_credit(self):
        result = score([item("React", "react")], [item("Vue", "vue")])
        self.assertEqual(result["score"], 0)
        self.assertEqual(len(result["suggestions"]), 1)

    def test_full_sentences_are_not_items(self):
        extracted = extract_items("Requirements:\n- Build scalable distributed systems\n- Experience with React.js, AWS, and Express")
        self.assertEqual({x["canonical"] for x in extracted}, {"react", "aws", "express"})
        self.assertTrue(all(x["kind"] == "skill" for x in extracted))

    def test_copied_jd_ignores_site_chrome(self):
        text = "Good match\nAWS\nResponsibilities\nBuild reliable systems\nQualifications\nAlgorithms\nThis position will be open for 5 days\nInsights from previous hires\nAzure"
        focused = focus_jd_text(text)
        self.assertNotIn("Good match", focused)
        self.assertNotIn("Azure", focused)

    def test_required_excludes_preferred(self):
        text = "Responsibilities\nUse AWS\nRequired Qualifications:\nObject-oriented language\nPreferred Qualifications:\nData structures and algorithms\nInsights from previous hires\nAzure"
        focused = focus_jd_text(text)
        self.assertEqual({x["canonical"] for x in extract_items(focused)}, {"object-oriented programming"})

    def test_empty_jd_and_empty_score(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "jd.txt"
            path.write_text("  ")
            with self.assertRaisesRegex(ValueError, "empty"):
                read_jd(path)
            with self.assertRaisesRegex(ValueError, "Cannot parse JD"):
                read_jd(path.with_name("missing.txt"))
        with self.assertRaisesRegex(ValueError, "no JD items"):
            score([], [])

    def test_image_only_pdf_error(self):
        fake_module = types.ModuleType("pypdf")
        fake_module.PdfReader = lambda path: types.SimpleNamespace(pages=[types.SimpleNamespace(extract_text=lambda: "")])
        with patch.dict(sys.modules, {"pypdf": fake_module}):
            with self.assertRaisesRegex(ValueError, "no selectable text"):
                read_resume_pdf("image-only.pdf")

    def test_corrupt_pdf_error(self):
        fake_module = types.ModuleType("pypdf")
        def fail(path):
            raise RuntimeError("damaged file")
        fake_module.PdfReader = fail
        with patch.dict(sys.modules, {"pypdf": fake_module}):
            with self.assertRaisesRegex(ValueError, "Cannot parse resume PDF"):
                read_resume_pdf("broken.pdf")


if __name__ == "__main__":
    unittest.main()
