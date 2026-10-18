import hashlib
import os
import re
import tempfile
import unittest
from io import BytesIO
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document as RAGDocument
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableLambda
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.api.v1 import chat, documents
from app.core.config import settings
from app.db import database
from app.db.database import Base
from app.db.models import ChatMessage, Document, User
from app.rag import rag_engine


def make_pdf(text: str = "Patient report: follow-up appointment in three months.") -> bytes:
    content = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n".encode("latin-1") + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    return bytes(pdf)


class TestEmbeddings(Embeddings):
    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * 64
        for word in re.findall(r"[a-z]+", text.lower()):
            if word not in {"a", "an", "and", "for", "in", "is", "of", "the", "to", "when"}:
                position = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % len(vector)
                vector[position] += 1
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class DocumentProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.sessions = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.addCleanup(self.engine.dispose)

        db = self.sessions()
        self.user = User(username="test-user", full_name="Test User", hashed_password="unused")
        db.add(self.user)
        db.commit()
        db.refresh(self.user)
        db.close()

        self.app = FastAPI()
        self.app.include_router(documents.router, prefix="/api/v1/documents")
        self.app.include_router(chat.router, prefix="/api/v1/chat")
        self.app.dependency_overrides[deps.get_current_user] = lambda: self.user
        self.app.dependency_overrides[documents.get_db] = self._get_db
        self.app.dependency_overrides[chat.get_db] = self._get_db
        self.addCleanup(self.app.dependency_overrides.clear)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

        self.session_factory_patch = patch.object(documents, "SessionLocal", self.sessions)
        self.session_factory_patch.start()
        self.addCleanup(self.session_factory_patch.stop)
        self.upload_dir_patch = patch.object(settings, "UPLOAD_DIR", os.path.join(self.temp_dir.name, "uploads"))
        self.index_dir_patch = patch.object(settings, "FAISS_INDEX_PATH", os.path.join(self.temp_dir.name, "indexes"))
        self.upload_dir_patch.start()
        self.index_dir_patch.start()
        self.addCleanup(self.upload_dir_patch.stop)
        self.addCleanup(self.index_dir_patch.stop)

    def _get_db(self):
        db = self.sessions()
        try:
            yield db
        finally:
            db.close()

    def _add_document(self, owner_id: int, status: str, filepath: str | None = None) -> Document:
        if filepath is None:
            filepath = os.path.join(self.temp_dir.name, f"{status}.pdf")
            with open(filepath, "wb") as pdf:
                pdf.write(make_pdf())
        db = self.sessions()
        document = Document(
            filename="report.pdf",
            filepath=filepath,
            owner_id=owner_id,
            status=status,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        db.expunge(document)
        db.close()
        return document

    def _upload(self, contents: bytes, name: str = "report.pdf", mime: str = "application/pdf"):
        return self.client.post(
            "/api/v1/documents/upload",
            files={"file": (name, contents, mime)},
        )

    def test_upload_indexes_document_and_retry_is_idempotent(self):
        with patch.object(documents.rag_engine, "ingest_pdf") as ingest:
            response = self._upload(make_pdf())
            self.assertEqual(response.status_code, 200, response.text)
            document_id = response.json()["id"]
            ingest.assert_called_once()

            db = self.sessions()
            stored = db.query(Document).filter(Document.id == document_id).one()
            self.assertEqual(stored.status, "completed")
            self.assertEqual(stored.processing_progress, 100)
            self.assertTrue(os.path.isfile(stored.filepath))
            db.close()

            retry = self.client.post(f"/api/v1/documents/{document_id}/retry")
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(ingest.call_count, 2)

    def test_indexing_progress_is_saved_and_completion_sets_100_percent(self):
        observed_progress = []

        def ingest_with_progress(*args, progress_callback, **kwargs):
            progress_callback(45)
            db = self.sessions()
            document = db.query(Document).one()
            observed_progress.append((document.status, document.processing_progress))
            db.close()
            progress_callback(82)

        with patch.object(documents.rag_engine, "ingest_pdf", side_effect=ingest_with_progress):
            response = self._upload(make_pdf())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(observed_progress, [("processing", 45)])
        document = self.client.get("/api/v1/documents/").json()[0]
        self.assertEqual(document["status"], "completed")
        self.assertEqual(document["processing_progress"], 100)

    def test_upload_rejects_empty_corrupt_misnamed_and_wrong_mime_files(self):
        self.assertEqual(self._upload(b"").status_code, 400)
        self.assertEqual(self._upload(b"not a PDF").status_code, 400)
        self.assertEqual(self._upload(make_pdf(), "report.docx").status_code, 400)
        self.assertEqual(self._upload(make_pdf(), mime="text/plain").status_code, 400)
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("test-password")
        encrypted_pdf = BytesIO()
        writer.write(encrypted_pdf)
        self.assertIn("Password-protected", self._upload(encrypted_pdf.getvalue()).json()["detail"])

    def test_failed_indexing_has_safe_error_and_can_be_retried(self):
        with patch.object(
            documents.rag_engine,
            "ingest_pdf",
            side_effect=[rag_engine.RAGError("Embedding generation failed. Check the configured embedding model and retry the PDF."), None],
        ):
            response = self._upload(make_pdf())
            self.assertEqual(response.status_code, 200, response.text)
            document_id = response.json()["id"]
            failed = self.client.get("/api/v1/documents/").json()[0]
            self.assertEqual(failed["status"], "failed")
            self.assertIn("Embedding generation failed", failed["processing_error"])

            retry = self.client.post(f"/api/v1/documents/{document_id}/retry")
            self.assertEqual(retry.status_code, 200, retry.text)
            completed = self.client.get("/api/v1/documents/").json()[0]
            self.assertEqual(completed["status"], "completed")
            self.assertIsNone(completed["processing_error"])

    def test_stale_processing_document_is_failed_and_kept_for_retry(self):
        document = self._add_document(self.user.id, "processing")
        db = self.sessions()
        stored = db.query(Document).filter(Document.id == document.id).one()
        stored.created_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        db.commit()
        db.close()

        result = self.client.get("/api/v1/documents/").json()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "failed")
        self.assertIn("took too long", result[0]["processing_error"])

    def test_chat_rejects_users_without_indexed_documents(self):
        other_user = User(username="other-user", full_name="Other User", hashed_password="unused")
        db = self.sessions()
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        self._add_document(other_user.id, "completed")
        db.close()

        with patch.object(chat.rag_engine, "generate_answer") as generate:
            response = self.client.post("/api/v1/chat/query", json={"query": "What is the diagnosis?"})
            self.assertEqual(response.status_code, 409)
            self.assertIn("No indexed PDFs", response.json()["detail"])
            generate.assert_not_called()

        self.assertEqual(self.client.get("/api/v1/documents/").json(), [])

    def test_chat_explains_when_a_document_is_still_processing(self):
        self._add_document(self.user.id, "processing")
        response = self.client.post("/api/v1/chat/query", json={"query": "What is in the report?"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("still being indexed", response.json()["detail"])

    def test_chat_retrieval_uses_only_this_users_indexed_document_ids(self):
        document = self._add_document(self.user.id, "completed")
        with patch.object(chat.rag_engine, "generate_answer", return_value=("Grounded answer", [])) as generate:
            response = self.client.post("/api/v1/chat/query", json={"query": "What is in the report?"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["answer"], "Grounded answer")
        self.assertEqual(generate.call_args.kwargs["indexed_document_ids"], [document.id])
        db = self.sessions()
        self.assertEqual(db.query(ChatMessage).count(), 2)
        db.close()

    def test_chat_requires_authentication(self):
        self.app.dependency_overrides.pop(deps.get_current_user)
        response = self.client.get("/api/v1/documents/")
        self.assertEqual(response.status_code, 401)

    def test_pdf_ingestion_persists_retrievable_chunks_without_duplicate_retry(self):
        path = os.path.join(self.temp_dir.name, "ingest.pdf")
        with open(path, "wb") as pdf:
            pdf.write(make_pdf("Patient report describes follow-up care and a three month appointment."))

        with patch.object(rag_engine, "get_embeddings", return_value=TestEmbeddings()):
            progress = []
            first = rag_engine.ingest_pdf(path, user_id=73, document_id=730, progress_callback=progress.append)
            second = rag_engine.ingest_pdf(path, user_id=73, document_id=730)
            vectorstore = FAISS.load_local(
                os.path.join(settings.FAISS_INDEX_PATH, "73"),
                TestEmbeddings(),
                allow_dangerous_deserialization=True,
            )
            matching = vectorstore.similarity_search(
                "What is the follow-up appointment?",
                k=3,
                filter=lambda metadata: metadata.get("document_id") == "730",
            )

        self.assertEqual(first["chunks_created"], second["chunks_created"])
        self.assertEqual(len(vectorstore.index_to_docstore_id), first["chunks_created"])
        self.assertTrue(matching)
        self.assertEqual(progress, [5, 20, 30, 65, 80, 90, 98])

    def test_schema_upgrade_preserves_existing_documents(self):
        legacy_engine = create_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'legacy.db')}",
        )
        self.addCleanup(legacy_engine.dispose)
        metadata = MetaData()
        Table(
            "users",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("full_name", String, nullable=False, default=""),
        )
        Table(
            "documents",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("filename", String, nullable=False),
            Column("filepath", String, nullable=False),
            Column("status", String, nullable=False),
            Column("processing_error", String),
            Column("owner_id", Integer),
            Column("created_at", String),
        )
        metadata.create_all(legacy_engine)
        with legacy_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents (id, filename, filepath, status, owner_id) "
                    "VALUES (1, 'report.pdf', '/persistent/report.pdf', 'processing', 5)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO documents (id, filename, filepath, status, owner_id) "
                    "VALUES (2, 'indexed.pdf', '/persistent/indexed.pdf', 'completed', 5)"
                )
            )

        with patch.object(database, "engine", legacy_engine):
            database.ensure_schema()

        columns = {column["name"] for column in inspect(legacy_engine).get_columns("documents")}
        self.assertIn("processing_started_at", columns)
        with legacy_engine.connect() as connection:
            stored = connection.execute(
                text("SELECT status, filepath, processing_progress FROM documents WHERE id = 1")
            ).one()
            completed = connection.execute(
                text("SELECT status, processing_progress FROM documents WHERE id = 2")
            ).one()
        self.assertEqual(stored.status, "processing")
        self.assertEqual(stored.filepath, "/persistent/report.pdf")
        self.assertEqual(stored.processing_progress, 0)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.processing_progress, 100)

    def test_ingestion_reports_empty_text_and_embedding_or_vector_failures(self):
        empty_path = os.path.join(self.temp_dir.name, "empty-text.pdf")
        with open(empty_path, "wb") as pdf:
            pdf.write(make_pdf(""))
        with self.assertRaises(rag_engine.RAGError):
            rag_engine.ingest_pdf(empty_path, user_id=74, document_id=740)

        with patch.object(rag_engine, "_extract_pdf_pages", return_value=[RAGDocument(page_content="A sufficiently long medical report for a test chunk.")]):
            with patch.object(rag_engine, "get_embeddings", side_effect=RuntimeError("embedding service unavailable")):
                with self.assertRaisesRegex(rag_engine.RAGError, "Embedding generation failed"):
                    rag_engine.ingest_pdf(empty_path, user_id=75, document_id=750)

            with patch.object(rag_engine, "get_embeddings", return_value=TestEmbeddings()):
                with patch.object(FAISS, "from_embeddings", side_effect=RuntimeError("vector store unavailable")):
                    with self.assertRaisesRegex(rag_engine.RAGError, "Vector storage failed"):
                        rag_engine.ingest_pdf(empty_path, user_id=76, document_id=760)

    def test_corrupt_existing_index_is_not_overwritten(self):
        index_dir = os.path.join(settings.FAISS_INDEX_PATH, "78")
        os.makedirs(index_dir)
        index_path = os.path.join(index_dir, "index.faiss")
        pickle_path = os.path.join(index_dir, "index.pkl")
        with open(index_path, "wb") as index_file:
            index_file.write(b"existing index data")
        with open(pickle_path, "wb") as pickle_file:
            pickle_file.write(b"existing metadata")

        with patch.object(
            rag_engine,
            "_extract_pdf_pages",
            return_value=[RAGDocument(page_content="A sufficiently long medical report for a test chunk.")],
        ):
            with patch.object(rag_engine, "get_embeddings", return_value=TestEmbeddings()):
                with self.assertRaisesRegex(rag_engine.RAGError, "existing search index could not be loaded"):
                    rag_engine.ingest_pdf("unused.pdf", user_id=78, document_id=780)

        with open(index_path, "rb") as index_file:
            self.assertEqual(index_file.read(), b"existing index data")
        with open(pickle_path, "rb") as pickle_file:
            self.assertEqual(pickle_file.read(), b"existing metadata")

    def test_rag_answer_uses_retrieved_context_and_no_match_does_not_call_llm(self):
        path = os.path.join(self.temp_dir.name, "answer.pdf")
        with open(path, "wb") as pdf:
            pdf.write(make_pdf("Patient report recommends a follow-up appointment in three months."))
        with patch.object(rag_engine, "get_embeddings", return_value=TestEmbeddings()):
            rag_engine.ingest_pdf(path, user_id=77, document_id=770)

        grounded_llm = RunnableLambda(lambda _: "The report recommends follow-up in three months.")
        with patch.object(rag_engine, "get_embeddings", return_value=TestEmbeddings()):
            with patch.object(rag_engine, "get_llm", return_value=grounded_llm):
                answer, sources = rag_engine.generate_answer(
                    "When is the follow-up?",
                    77,
                    indexed_document_ids=[770],
                )
                no_context, no_sources = rag_engine.generate_answer(
                    "When is the follow-up?",
                    77,
                    indexed_document_ids=[771],
                )
                irrelevant, irrelevant_sources = rag_engine.generate_answer(
                    "Explain the distance between distant galaxies.",
                    77,
                    indexed_document_ids=[770],
                )

        self.assertIn("three months", answer)
        self.assertTrue(sources)
        self.assertIn("could not find relevant information", no_context)
        self.assertEqual(no_sources, [])
        self.assertIn("could not find relevant information", irrelevant)
        self.assertEqual(irrelevant_sources, [])

    def test_groq_client_uses_configured_model_without_network_access(self):
        with patch.object(settings, "GROQ_API_KEY", "test-key"):
            with patch.object(rag_engine, "_llm", None):
                llm = rag_engine.get_llm()
        self.assertEqual(llm.model_name, settings.GROQ_MODEL)


if __name__ == "__main__":
    unittest.main()
