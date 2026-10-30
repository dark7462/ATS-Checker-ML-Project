import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from matcher import extract_items, focus_jd_text, read_jd, read_resume_pdf, read_resume_pdf_bytes, score


def item(label, canonical=None, kind="skill", vector=None):
    return {"label": label, "canonical": canonical or label.lower(), "kind": kind, "vector": vector or [1.0, 0.0]}


class MatcherTests(unittest.TestCase):
    def test_three_skill_example(self):
        jd = [item("React.js", "react", vector=[1, 0]), item("AWS", "aws", vector=[0, 1]), item("Express", "express", vector=[-1, 0])]
        resume = [item("React", "react", vector=[0.8, 0.6]), item("Azure", "azure", vector=[0, -1]), item("Express", "express", vector=[-1, 0])]
        result = score(jd, resume)
        self.assertEqual((result["points"], result["total"], result["score"]), (1.5, 3, 50))

    def test_aliases_and_duplicate_jd(self):
        extracted = extract_items("React.js, AWS, Express\nReact, AWS, Express")
        self.assertEqual({x["canonical"] for x in extracted}, {"react", "aws", "express"})
        for skill in extracted:
            skill["vector"] = {"react": [1, 0, 0], "aws": [0, 1, 0], "express": [0, 0, 1]}[skill["canonical"]]
        result = score(extracted + [extracted[0]], [item("React", "react", vector=[1, 0, 0]), item("AWS", "aws", vector=[0, 1, 0]), item("Express", "express", vector=[0, 0, 1])])
        self.assertEqual(result["score"], 100)

    def test_one_resume_skill_cannot_cover_two_jd_skills(self):
        result = score([item("AWS", "aws"), item("Azure", "azure")], [item("Azure", "azure")])
        self.assertEqual(result["points"], 1)
        self.assertEqual(len(result["matched"]), 1)

    def test_unrelated_vectors_have_no_credit(self):
        result = score([item("React", "react", vector=[1, 0])], [item("Vue", "vue", vector=[0, 1])])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["matched"], [])

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

    def test_article_skill_section_excludes_example_tools_and_footer(self):
        text = ("Monitoring solutions like Splunk\n"
                "Site reliability engineer skills to kick-start your role\n"
                "Good grasp of scripting languages\nPython and Bash\n"
                "Automation of processes.\nTroubleshooting issues.\n"
                "(Related reading: monitoring.)\n"
                "Expertise in Kubernetes\nKubernetes and containerization technologies\n"
                "Understanding of CI/CD\n(Learn more about monitoring.)\n"
                "Ready to start your SRE job?\nJira")
        focused = focus_jd_text(text)
        self.assertNotIn("Splunk", focused)
        self.assertNotIn("Jira", focused)
        self.assertNotIn("Related reading", focused)
        self.assertNotIn("Learn more about", focused)
        self.assertIn("Python and Bash", focused)

    def test_sre_skill_terms_are_extracted_from_jd_and_resume(self):
        text = ("Python and Bash scripting; automation, troubleshooting, Kubernetes, "
                "containerization, CI/CD, monitoring, logging, observability, "
                "incident management, root cause analysis, disaster recovery, Splunk")
        expected = {"python", "bash", "automation", "troubleshooting", "kubernetes",
                    "containerization", "ci/cd", "monitoring", "logging", "observability",
                    "incident management", "root cause analysis", "disaster recovery", "splunk"}
        self.assertEqual({x["canonical"] for x in extract_items(text)}, expected)
        self.assertEqual({x["canonical"] for x in extract_items(text, source="resume")}, expected)

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

    def test_uploaded_pdf_prefers_layout_text_for_multiword_skills(self):
        fake_module = types.ModuleType("pypdf")
        page = types.SimpleNamespace(extract_text=lambda extraction_mode="plain":
                                     "Incident Management" if extraction_mode == "layout" else "Incident\nManagement")
        fake_module.PdfReader = lambda stream: types.SimpleNamespace(pages=[page])
        with patch.dict(sys.modules, {"pypdf": fake_module}):
            self.assertEqual(read_resume_pdf_bytes(b"fake pdf"), "Incident Management")


if __name__ == "__main__":
    unittest.main()
