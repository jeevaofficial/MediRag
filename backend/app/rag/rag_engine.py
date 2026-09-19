import os
import time
import json
import logging
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.core.config import settings

logger = logging.getLogger(__name__)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Global variables for singletons
_embeddings = None
_llm = None

class RAGError(RuntimeError):
    pass

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

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        logger.info("Loading HuggingFace embeddings model")
        _embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"local_files_only": True},
        )
        logger.info("HuggingFace embeddings model loaded")
    return _embeddings

def get_llm():
    global _llm
    if _llm is None:
        logger.info("Creating ChatGroq client model=%s", settings.GROQ_MODEL)
        try:
            _llm = ChatGroq(
                temperature=0,
                model_name=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
            )
        except Exception as e:
            logger.error("Failed to initialize Groq LLM: %s", e)
            raise RAGError("Failed to initialize Groq LLM. Check your GROQ_API_KEY.")
    return _llm

def ingest_pdf(filepath: str, user_id: int):
    logger.info("Starting PDF ingestion filepath=%s user_id=%s", filepath, user_id)
    loader = PyPDFLoader(filepath)
    docs = loader.load()
    logger.info("Loaded %s pages from PDF", len(docs))
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = text_splitter.split_documents(docs)
    logger.info("Split PDF into %s chunks", len(splits))
    
    embeddings = get_embeddings()
    user_index_dir = os.path.join(settings.FAISS_INDEX_PATH, str(user_id))
    os.makedirs(user_index_dir, exist_ok=True)
    index_file = os.path.join(user_index_dir, "index.faiss")
    
    if os.path.exists(index_file):
        vectorstore = FAISS.load_local(user_index_dir, embeddings, allow_dangerous_deserialization=True)
        vectorstore.add_documents(splits)
    else:
        vectorstore = FAISS.from_documents(splits, embeddings)
    vectorstore.save_local(user_index_dir)
    logger.info("Saved FAISS vector store after PDF ingestion for user %s", user_id)

def delete_pdf(filepath: str, user_id: int):
    logger.info("Starting PDF deletion from FAISS filepath=%s user_id=%s", filepath, user_id)
    user_index_dir = os.path.join(settings.FAISS_INDEX_PATH, str(user_id))
    index_file = os.path.join(user_index_dir, "index.faiss")
    if not os.path.exists(index_file):
        logger.info("No FAISS index found for user %s, nothing to delete.", user_id)
        return

    try:
        embeddings = get_embeddings()
        vectorstore = FAISS.load_local(user_index_dir, embeddings, allow_dangerous_deserialization=True)
        docstore = vectorstore.docstore._dict
        ids_to_delete = []
        
        for doc_id, doc in docstore.items():
            if doc.metadata.get("source") == filepath:
                ids_to_delete.append(doc_id)
                
        if ids_to_delete:
            logger.info("Deleting %s chunks from FAISS for %s", len(ids_to_delete), filepath)
            vectorstore.delete(ids_to_delete)
            vectorstore.save_local(user_index_dir)
            logger.info("FAISS vector store saved after deletion")
        else:
            logger.info("No chunks found in FAISS for %s", filepath)
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

def generate_answer(query: str, user_id: int):
    started_at = time.perf_counter()
    logger.info("RAG generation started query_length=%s user_id=%s", len(query), user_id)
    
    try:
        user_index_dir = os.path.join(settings.FAISS_INDEX_PATH, str(user_id))
        index_file = os.path.join(user_index_dir, "index.faiss")
        if not os.path.exists(index_file):
            raise RAGError("No indexed documents found. Upload a valid PDF first and wait until its status becomes indexed.")

        embeddings = get_embeddings()
        vectorstore = FAISS.load_local(user_index_dir, embeddings, allow_dangerous_deserialization=True)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

        retrieval_started_at = time.perf_counter()
        docs = usable_docs(retriever.invoke(query))
        retrieval_time = time.perf_counter() - retrieval_started_at
        logger.info("FAISS retrieval completed docs=%s duration=%.2fs", len(docs), retrieval_time)

        if not docs:
            raise RAGError("No usable document content was found. Upload a valid text-based PDF and wait until it is indexed.")

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
        logger.exception("Unexpected RAG answer generation failure")
        raise RAGError(f"Failed to generate answer from Groq API: {exc}") from exc
