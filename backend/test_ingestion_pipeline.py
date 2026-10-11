import os
import tempfile
import unittest

from app.rag import rag_engine


class IngestionPipelineTests(unittest.TestCase):
    def test_empty_pdf_raises_clear_error(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"")
            path = tmp.name

        try:
            with self.assertRaises(rag_engine.RAGError) as ctx:
                rag_engine.ingest_pdf(path, user_id=99)
            self.assertIn("OCR required / No extractable text", str(ctx.exception))
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
