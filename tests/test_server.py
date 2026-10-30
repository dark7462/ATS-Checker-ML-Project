import unittest
from io import BytesIO

import numpy as np
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from server import InputError, analyze_upload, parse_multipart_upload


def resume_pdf(text="React and Python"):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class FakeModel:
    def encode(self, labels, normalize_embeddings=True):
        vectors = {"React.js": [1, 0], "React": [0.8, 0.6], "Python": [0, 1]}
        return np.asarray([vectors[label] for label in labels])


class ServerTests(unittest.TestCase):
    def test_analysis_returns_vector_score_and_shared_3d_points(self):
        result = analyze_upload(
            "job.txt", b"Required Qualifications:\nReact.js\nPython",
            "resume.pdf", resume_pdf(), FakeModel(),
        )
        self.assertEqual(result["score"], 75)
        self.assertEqual(len(result["matched"]), 2)
        self.assertEqual(len(result["points_3d"]["jd"]), 2)
        self.assertEqual(len(result["points_3d"]["resume"]), 2)
        self.assertNotIn("vector", result["points_3d"]["jd"][0])

    def test_rejects_wrong_file_types_and_empty_inputs(self):
        with self.assertRaisesRegex(InputError, "JD.*txt"):
            analyze_upload("job.pdf", b"React", "resume.pdf", resume_pdf(), FakeModel())
        with self.assertRaisesRegex(InputError, "PDF"):
            analyze_upload("job.txt", b"React", "resume.txt", b"React", FakeModel())
        with self.assertRaisesRegex(InputError, "empty"):
            analyze_upload("job.txt", b"  ", "resume.pdf", resume_pdf(), FakeModel())

    def test_rejects_image_only_resume(self):
        with self.assertRaisesRegex(InputError, "selectable text"):
            analyze_upload("job.txt", b"React", "resume.pdf", resume_pdf(""), FakeModel())

    def test_resume_without_recognized_skills_gets_zero_score(self):
        result = analyze_upload("job.txt", b"React.js", "resume.pdf", resume_pdf("Experience in art"), FakeModel())
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["unmatched"], ["React.js"])
        self.assertEqual(result["points_3d"]["resume"], [])

    def test_model_loads_only_after_upload_is_validated(self):
        calls = []
        def load_model():
            calls.append("loaded")
            return FakeModel()
        with self.assertRaisesRegex(InputError, "JD.*txt"):
            analyze_upload("job.pdf", b"React", "resume.pdf", resume_pdf(), load_model)
        self.assertEqual(calls, [])
        result = analyze_upload("job.txt", b"React.js", "resume.pdf", resume_pdf("React"), load_model)
        self.assertEqual(result["score"], 50)
        self.assertEqual(calls, ["loaded"])

    def test_callable_model_object_is_not_invoked_as_a_loader(self):
        class CallableModel(FakeModel):
            def __call__(self):
                raise AssertionError("model object must not be called")

        result = analyze_upload("job.txt", b"React.js", "resume.pdf", resume_pdf("React"), CallableModel())
        self.assertEqual(result["score"], 50)

    def test_multipart_upload_preserves_pdf_bytes(self):
        body = b"".join([
            b"--boundary-test\r\nContent-Disposition: form-data; name=\"jd\"; filename=\"job.txt\"\r\nContent-Type: text/plain\r\n\r\n",
            b"React.js and Python\r\n",
            b"--boundary-test\r\nContent-Disposition: form-data; name=\"resume\"; filename=\"resume.pdf\"\r\nContent-Type: application/pdf\r\n\r\n",
            resume_pdf(), b"\r\n--boundary-test--\r\n",
        ])
        files = parse_multipart_upload("multipart/form-data; boundary=boundary-test", body)
        result = analyze_upload(*files["jd"], *files["resume"], FakeModel())
        self.assertEqual(result["score"], 75)

    def test_multipart_upload_requires_both_files(self):
        body = b"--boundary-test\r\nContent-Disposition: form-data; name=\"jd\"; filename=\"job.txt\"\r\n\r\nReact\r\n--boundary-test--\r\n"
        with self.assertRaisesRegex(InputError, "both"):
            parse_multipart_upload("multipart/form-data; boundary=boundary-test", body)


if __name__ == "__main__":
    unittest.main()
