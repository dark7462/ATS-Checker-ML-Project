import math
import unittest

from matcher import embed_items, extract_items, project_items, score


def skill(label, vector):
    return {"kind": "skill", "label": label, "canonical": label.lower(), "vector": vector}


class VectorScoringTests(unittest.TestCase):
    def test_opaque_aliases_use_expanded_text_before_vector_scoring(self):
        import numpy as np

        class WordModel:
            def encode(self, labels, normalize_embeddings=True):
                vectors = {
                    "machine learning": [1, 0], "typescript": [0, 1],
                    "kubernetes": [-1, 0], "scikit-learn": [0, -1],
                    "continuous integration and continuous deployment": [0.7, 0.7],
                    "amazon web services": [-0.7, 0.7], "apache spark": [0.7, -0.7],
                }
                return np.asarray([vectors[label.lower()] for label in labels])

        model = WordModel()
        for jd_label, resume_label in [
            ("machine learning", "ML"), ("TypeScript", "TS"),
            ("Kubernetes", "K8s"), ("Scikit-learn", "sklearn"),
            ("CI/CD", "continuous integration"),
            ("AWS", "Amazon Web Services"), ("Spark", "Apache Spark"),
        ]:
            jd = embed_items(extract_items(jd_label), model)
            resume = embed_items(extract_items(resume_label, source="resume"), model)
            self.assertEqual(score(jd, resume)["score"], 100, (jd_label, resume_label))

    def test_react_aliases_keep_their_measured_similarity(self):
        import numpy as np

        class WordModel:
            def encode(self, labels, normalize_embeddings=True):
                return np.asarray([{"React.js": [1, 0], "React": [0.8, 0.6]}[label] for label in labels])

        jd = embed_items(extract_items("React.js"), WordModel())
        resume = embed_items(extract_items("React", source="resume"), WordModel())
        self.assertEqual(score(jd, resume)["score"], 50)

    def test_docker_can_partially_match_containerization(self):
        import numpy as np

        class WordModel:
            def encode(self, labels, normalize_embeddings=True):
                vectors = {"containerization": [1, 0], "Docker": [0, 1],
                           "Docker containerization": [0.8, 0.6]}
                return np.asarray([vectors[label] for label in labels])

        jd = embed_items(extract_items("containerization"), WordModel())
        resume = embed_items(extract_items("Docker", source="resume"), WordModel())
        result = score(jd, resume)
        self.assertEqual(result["score"], 50)
        self.assertEqual(result["matched"][0]["jd"], "containerization")

    def test_identical_vectors_earn_full_score(self):
        result = score([skill("React.js", [1, 0])], [skill("React", [1, 0])])
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["matched"][0]["similarity"], 1)

    def test_similarity_is_calibrated_before_it_becomes_points(self):
        result = score([skill("React.js", [1, 0])], [skill("React", [0.8, 0.6])])
        self.assertEqual(result["score"], 50)
        self.assertEqual(result["matched"][0]["credit"], 0.5)

    def test_score_uses_unrounded_similarity(self):
        cosine = 0.812345
        result = score([skill("a", [1, 0])], [skill("b", [cosine, math.sqrt(1 - cosine**2)])])
        self.assertEqual(result["score"], 53.09)

    def test_low_similarity_is_not_counted_as_a_collision(self):
        result = score([skill("React", [1, 0])], [skill("SQL", [0.5, math.sqrt(0.75)])])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["unmatched"], ["React"])

    def test_pairing_maximizes_total_score(self):
        jd = [skill("first", [1, 0]), skill("second", [0.5, math.sqrt(0.75)])]
        resume = [skill("r1", [math.sqrt(0.75), 0.5]), skill("r2", [math.sqrt(0.75), -0.5])]
        result = score(jd, resume)
        self.assertEqual(len(result["matched"]), 2)
        self.assertEqual({(p["jd"], p["resume"]) for p in result["matched"]}, {("first", "r2"), ("second", "r1")})

    def test_duplicate_skills_keep_their_first_index_for_visual_links(self):
        result = score(
            [skill("React", [1, 0]), skill("Python", [0, 1]), skill("React", [1, 0])],
            [skill("Python", [0, 1])],
        )
        self.assertEqual(result["matched"][0]["jd_index"], 1)

    def test_projection_uses_one_shared_space_and_handles_identical_vectors(self):
        points = project_items([skill("a", [1, 0, 0]), skill("b", [0, 1, 0])], [skill("same", [1, 0, 0])])
        self.assertEqual(len(points["jd"]), 2)
        self.assertEqual(len(points["resume"]), 1)
        self.assertEqual(points["jd"][0]["position"], points["resume"][0]["position"])
        self.assertTrue(all(len(p["position"]) == 3 for group in points.values() for p in group))


if __name__ == "__main__":
    unittest.main()
