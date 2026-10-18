import logging
import os
import re
import threading
import time
from collections.abc import Callable

# Disable HuggingFace symlinks warning which causes a blocking prompt on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic.v1 import SecretStr

from app.core.config import settings

logger = logging.getLogger(__name__)

_embeddings = None
_llm = None
_embeddings_lock = threading.Lock()
_llm_lock = threading.Lock()
_vectorstore_lock = threading.RLock()
MIN_RETRIEVAL_COSINE_SIMILARITY = 0.3


class RAGError(RuntimeError):
    pass


def _indexed_documents(vectorstore: FAISS) -> list[tuple[str, Document]]:
    documents = []
    for stored_id in vectorstore.index_to_docstore_id.values():
        stored_document = vectorstore.docstore.search(stored_id)
        if isinstance(stored_document, Document):
            documents.append((stored_id, stored_document))
    return documents


SYSTEM_PROMPT = """You are MediRAG AI, a highly accurate medical reference assistant.
Your answers must be grounded strictly in the provided medical context.
Do NOT use outside knowledge to answer the question.

IMPORTANT: If the user asks for specific patient details like Age, Name, Diagnosis, Blood Pressure, Temperature, HbA1c, Medicines, or Follow-up advice, and it exists in the context, extract it and provide it directly. Do not refuse to answer if the context contains the information.
If the context does not contain the answer, say "I cannot answer this based on the provided documents."

DISCLAIMER: This is a document-retrieval tool, not a medical device. It does not diagnose, prescribe, or replace professional medical judgment.

Context:
{context}

Question:
{question}
"""


def _clean_text(raw_text: str) -> str:
    if raw_text is None:
        return ""
    cleaned = raw_text.replace("\x00", "").replace("\ufeff", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"[ \t\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\n +", "\n", cleaned)
    cleaned = re.sub(r" +\n", "\n", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _safe_metadata(metadata: dict, filepath: str, document_id: str | None = None):
    safe_metadata = dict(metadata or {})
    safe_metadata["source"] = filepath
    safe_metadata["filename"] = os.path.basename(filepath)
    if document_id is not None:
        safe_metadata["document_id"] = str(document_id)
    page_number = safe_metadata.get("page")
    if isinstance(page_number, int):
        safe_metadata["page_number"] = page_number + 1
    return safe_metadata


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        with _embeddings_lock:
            if _embeddings is None:
                try:
                    import torch
                    torch.set_num_threads(1)
                    try:
                        torch.set_num_interop_threads(1)
                    except Exception:
                        pass
                except Exception:
                    pass

                logger.info("[EMBEDDING] Loading HuggingFace embeddings model (single-thread low-memory)")
                _embeddings = HuggingFaceEmbeddings(
                    model_name="all-MiniLM-L6-v2",
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": False},
                )
                logger.info("[EMBEDDING] HuggingFace embeddings model loaded")
    return _embeddings


def get_llm():
    global _llm
    if _llm is None:
        with _llm_lock:
            if _llm is None:
                logger.info("[LLM] Creating ChatGroq client model=%s", settings.GROQ_MODEL)
                try:
                    _llm = ChatGroq(
                        temperature=0,
                        model=settings.GROQ_MODEL,
                        stop_sequences=None,
                        api_key=SecretStr(settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None,
                    )
                except Exception:
                    logger.exception("Failed to initialize Groq LLM")
                    raise RAGError("Answer generation is not configured. Contact the administrator.")
    return _llm


def _extract_pdf_pages(filepath: str):
    logger.info("[EXTRACT] Starting PDF extraction filepath=%s", filepath)
    if os.path.getsize(filepath) == 0:
        raise RAGError("OCR required / No extractable text")
    try:
        loader = PyPDFLoader(filepath)
        pages = loader.load()
    except Exception as exc:
        logger.exception("[ERROR] PDF extraction failed for %s", filepath)
        raise RAGError("The PDF could not be read during text extraction. Check that it is not corrupted or password-protected.") from exc

    logger.info("[EXTRACT] Pages extracted: %s", len(pages))
    cleaned_pages = []
    for page_index, page in enumerate(pages):
        page_text = _clean_text(page.page_content or "")
        if not page_text:
            logger.warning("[EXTRACT] Page %s contains no extractable text", page_index + 1)
            continue
        cleaned_pages.append(
            Document(
                page_content=page_text,
                metadata=_safe_metadata(page.metadata or {}, filepath),
            )
        )

    if not cleaned_pages:
        logger.error("[ERROR] PDF contains no extractable text filepath=%s", filepath)
        raise RAGError("OCR required / No extractable text")

    return cleaned_pages


def _chunk_pages(pages, filepath: str, document_id: str | None = None):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80)
    chunks = []
    for page_index, page in enumerate(pages):
        page_text = _clean_text(page.page_content or "")
        if not page_text:
            continue
        split_docs = text_splitter.split_documents([page])
        for chunk_index, chunk in enumerate(split_docs):
            chunk_text = _clean_text(chunk.page_content or "")
            if not chunk_text or len(chunk_text) < 25:
                continue
            metadata = _safe_metadata(chunk.metadata or {}, filepath, document_id)
            metadata["page_number"] = (int(metadata.get("page", 0)) + 1) if isinstance(metadata.get("page"), int) else (page_index + 1)
            metadata["chunk_index"] = chunk_index
            chunks.append(Document(page_content=chunk_text, metadata=metadata))

    if not chunks:
        raise RAGError("No valid chunks could be created from the extracted PDF text.")

    logger.info("[CHUNK] Created %s chunks for document_id=%s", len(chunks), document_id)
    return chunks


def ingest_pdf(
    filepath: str,
    user_id: int,
    document_id: int | str | None = None,
    progress_callback: Callable[[int], None] | None = None,
):
    logger.info("[UPLOAD] PDF ingestion started filepath=%s user_id=%s document_id=%s", filepath, user_id, document_id)

    try:
        if progress_callback:
            progress_callback(5)
        pages = _extract_pdf_pages(filepath)
        if progress_callback:
            progress_callback(20)
        chunks = _chunk_pages(pages, filepath, document_id=str(document_id) if document_id is not None else None)
        if progress_callback:
            progress_callback(30)

        logger.info("[EMBEDDING] Generating embeddings for %s chunks", len(chunks))
        try:
            embeddings = get_embeddings()
            embedding_vectors = embeddings.embed_documents([chunk.page_content for chunk in chunks])
        except Exception as exc:
            logger.exception("Embedding generation failed document_id=%s", document_id)
            raise RAGError("Embedding generation failed. Check the configured embedding model and retry the PDF.") from exc
        if (
            len(embedding_vectors) != len(chunks)
            or not embedding_vectors
            or any(not vector for vector in embedding_vectors)
            or len({len(vector) for vector in embedding_vectors}) != 1
        ):
            raise RAGError("Embedding generation failed: invalid or empty vectors returned by the embedding model.")
        if progress_callback:
            progress_callback(65)

        user_index_dir = os.path.join(settings.FAISS_INDEX_PATH, str(user_id))
        os.makedirs(user_index_dir, exist_ok=True)
        index_file = os.path.join(user_index_dir, "index.faiss")
        text_embeddings = list(zip(
            [chunk.page_content for chunk in chunks],
            embedding_vectors,
        ))
        chunk_metadata = [chunk.metadata for chunk in chunks]

        try:
            with _vectorstore_lock:
                if os.path.exists(index_file):
                    try:
                        existing_vectorstore = FAISS.load_local(
                            user_index_dir,
                            embeddings,
                            allow_dangerous_deserialization=True,
                        )
                    except Exception as exc:
                        logger.exception("Could not load existing FAISS index for user_id=%s", user_id)
                        raise RAGError("The existing search index could not be loaded. No indexed documents were changed; contact the administrator.") from exc

                    ids_to_delete = [
                        stored_id
                        for stored_id, stored_doc in _indexed_documents(existing_vectorstore)
                        if (
                            document_id is not None
                            and stored_doc.metadata.get("document_id") == str(document_id)
                        ) or stored_doc.metadata.get("source") == filepath
                    ]
                    if ids_to_delete:
                        logger.info("Removing %s stale chunks before re-indexing document_id=%s", len(ids_to_delete), document_id)
                        existing_vectorstore.delete(ids_to_delete)
                    existing_vectorstore.add_embeddings(text_embeddings, metadatas=chunk_metadata)
                    vectorstore = existing_vectorstore
                else:
                    vectorstore = FAISS.from_embeddings(
                        text_embeddings,
                        embeddings,
                        metadatas=chunk_metadata,
                    )

                if progress_callback:
                    progress_callback(80)
                vectorstore.save_local(user_index_dir)
                if progress_callback:
                    progress_callback(90)
                document_chunks = [
                    stored_doc
                    for _, stored_doc in _indexed_documents(vectorstore)
                    if (
                        document_id is not None
                        and stored_doc.metadata.get("document_id") == str(document_id)
                    ) or stored_doc.metadata.get("source") == filepath
                ]
                if len(document_chunks) < len(chunks):
                    raise RAGError("Index verification failed: not all document chunks were saved.")
                retrieval_hits = vectorstore.similarity_search(
                    chunks[0].page_content[:200],
                    k=min(3, len(chunks)),
                    filter=lambda metadata: (
                        metadata.get("document_id") == str(document_id)
                        if document_id is not None
                        else metadata.get("source") == filepath
                    ),
                )
                if not retrieval_hits:
                    raise RAGError("Index verification failed: this document's chunks could not be retrieved after saving.")
                if progress_callback:
                    progress_callback(98)
        except RAGError:
            raise
        except Exception as exc:
            logger.exception("Vector storage failed document_id=%s user_id=%s", document_id, user_id)
            raise RAGError("Vector storage failed while saving the PDF chunks. Please retry; technical details were logged.") from exc
        logger.info("[VECTOR DB] Insert successful for %s vectors into user %s", len(chunks), user_id)

        logger.info("[INDEX] Document indexing completed filepath=%s user_id=%s chunks=%s", filepath, user_id, len(chunks))
        return {"chunks_created": len(chunks), "retrieval_hits": len(retrieval_hits)}

    except RAGError:
        raise
    except Exception as exc:
        logger.exception("[ERROR] Unexpected ingestion failure filepath=%s user_id=%s", filepath, user_id)
        raise RAGError("PDF indexing failed unexpectedly. Please retry the upload; technical details were logged.") from exc

def delete_pdf(filepath: str, user_id: int):
    logger.info("Starting PDF deletion from FAISS filepath=%s user_id=%s", filepath, user_id)
    user_index_dir = os.path.join(settings.FAISS_INDEX_PATH, str(user_id))
    index_file = os.path.join(user_index_dir, "index.faiss")
    if not os.path.exists(index_file):
        logger.info("No FAISS index found for user %s, nothing to delete.", user_id)
        return

    try:
        embeddings = get_embeddings()
        with _vectorstore_lock:
            vectorstore = FAISS.load_local(user_index_dir, embeddings, allow_dangerous_deserialization=True)
            ids_to_delete = [
                doc_id
                for doc_id, doc in _indexed_documents(vectorstore)
                if doc.metadata.get("source") == filepath
            ]

            if ids_to_delete:
                logger.info("Deleting %s chunks for a removed document", len(ids_to_delete))
                vectorstore.delete(ids_to_delete)
                vectorstore.save_local(user_index_dir)
                logger.info("FAISS vector store saved after deletion")
            else:
                logger.info("No chunks found for the removed document")
    except Exception as e:
        logger.error("Failed to delete from FAISS: %s", e)

def format_docs(docs):
    seen = set()
    unique_docs = []
    for doc in docs:
        if doc.page_content not in seen:
            seen.add(doc.page_content)
            unique_docs.append(doc)
    
    formatted = []
    for doc in unique_docs:
        page_val = doc.metadata.get("page")
        # PyPDFLoader pages are 0-indexed. Convert to 1-indexed.
        if isinstance(page_val, int):
            page_val = page_val + 1
        formatted.append(f"Source (Page {page_val if page_val is not None else 'unknown'}): {doc.page_content}")
        
    return "\n\n".join(formatted)

def usable_docs(docs):
    return [
        doc for doc in docs
        if doc.page_content.strip() and doc.page_content.strip().lower() != "init"
    ]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return dot_product / (left_norm * right_norm)


def generate_answer(
    query: str,
    user_id: int,
    indexed_document_ids: list[int] | None = None,
    indexed_document_sources: list[str] | None = None,
):
    started_at = time.perf_counter()
    logger.info("RAG generation started query_length=%s user_id=%s", len(query), user_id)
    
    try:
        user_index_dir = os.path.join(settings.FAISS_INDEX_PATH, str(user_id))
        index_file = os.path.join(user_index_dir, "index.faiss")
        if not os.path.exists(index_file):
            raise RAGError("Your documents are marked indexed, but their search index is unavailable. Retry indexing or upload the PDFs again.")
        if not indexed_document_ids:
            raise RAGError("No indexed PDFs are available. Upload a valid PDF and wait until indexing is complete.")

        embeddings = get_embeddings()
        allowed_document_ids = {str(document_id) for document_id in indexed_document_ids}
        allowed_sources = set(indexed_document_sources or [])
        retrieval_started_at = time.perf_counter()
        with _vectorstore_lock:
            vectorstore = FAISS.load_local(user_index_dir, embeddings, allow_dangerous_deserialization=True)
            docs = usable_docs(vectorstore.similarity_search(
                query,
                k=10,
                filter=lambda metadata: (
                    metadata.get("document_id") in allowed_document_ids
                    or metadata.get("source") in allowed_sources
                ),
            ))
        if docs:
            query_embedding = embeddings.embed_query(query)
            document_embeddings = embeddings.embed_documents([doc.page_content for doc in docs])
            if len(document_embeddings) != len(docs):
                raise RAGError("Could not verify the relevance of retrieved PDF passages. Please try again.")
            docs = [
                doc
                for doc, embedding in zip(docs, document_embeddings)
                if _cosine_similarity(query_embedding, embedding) >= MIN_RETRIEVAL_COSINE_SIMILARITY
            ]
        retrieval_time = time.perf_counter() - retrieval_started_at
        logger.info("FAISS retrieval completed docs=%s duration=%.2fs", len(docs), retrieval_time)

        if not docs:
            return "I could not find relevant information in your indexed PDFs for this question.", []

        context = format_docs(docs)
        
        # Sources for frontend
        sources = []
        for doc in docs:
            p = doc.metadata.get("page")
            sources.append({
                "page": (p + 1) if isinstance(p, int) else "N/A", 
                "content": doc.page_content[:200] + "..."
            })

        llm = get_llm()
        prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)
        chain = prompt | llm | StrOutputParser()

        llm_started_at = time.perf_counter()
        answer = chain.invoke({"context": context, "question": query})
        generation_time = time.perf_counter() - llm_started_at
        total_time = time.perf_counter() - started_at
        
        logger.info("RAG performance: retrieval=%.2fs generation=%.2fs total=%.2fs", retrieval_time, generation_time, total_time)
        return answer, sources

    except RAGError:
        logger.exception("RAG error")
        raise
    except Exception as exc:
        logger.exception("Unexpected RAG answer generation failure user_id=%s", user_id)
        raise RAGError("Answer generation failed. Please try again shortly; the technical error was logged.") from exc
