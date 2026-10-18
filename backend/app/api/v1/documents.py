import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db, SessionLocal
from app.db.models import User, Document
from app.core.config import settings
from app.rag import rag_engine

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
PROCESSING_TIMEOUT = timedelta(minutes=30)
_active_document_ids: set[int] = set()
_active_document_ids_lock = threading.Lock()


def _update_document_state(
    doc_id: int,
    status: str,
    error_message: str | None = None,
    progress: int | None = None,
) -> bool:
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.warning("Cannot update missing document_id=%s status=%s", doc_id, status)
            return False
        previous_status = doc.status
        doc.status = status
        doc.processing_error = error_message
        if status == "processing":
            if previous_status != "processing" or doc.processing_started_at is None:
                doc.processing_started_at = datetime.now(timezone.utc)
        else:
            doc.processing_started_at = None
        if status == "completed":
            doc.processing_progress = 100
        elif progress is not None:
            doc.processing_progress = max(0, min(99, progress))
        db.commit()
        logger.info(
            "[STATUS] Document %s status=%s progress=%s",
            doc_id,
            status,
            doc.processing_progress,
        )
        return True
    except Exception:
        db.rollback()
        logger.exception("Failed to update document_id=%s status=%s", doc_id, status)
        raise
    finally:
        db.close()


def process_document_background(doc_id: int, filepath: str, user_id: int):
    with _active_document_ids_lock:
        if doc_id in _active_document_ids:
            logger.warning("Ignoring duplicate indexing task document_id=%s", doc_id)
            return
        _active_document_ids.add(doc_id)

    try:
        if not _update_document_state(doc_id, "processing", progress=1):
            return
        logger.info("Starting indexing document_id=%s user_id=%s", doc_id, user_id)

        def report_progress(progress: int) -> None:
            _update_document_state(doc_id, "processing", progress=progress)

        rag_engine.ingest_pdf(
            filepath,
            user_id,
            document_id=doc_id,
            progress_callback=report_progress,
        )
        if _update_document_state(doc_id, "completed"):
            logger.info("Document indexing completed document_id=%s", doc_id)
    except Exception as exc:
        logger.exception("Document indexing failed document_id=%s user_id=%s", doc_id, user_id)
        error_message = (
            str(exc)
            if isinstance(exc, rag_engine.RAGError)
            else "Indexing failed unexpectedly. Please retry the PDF or upload it again."
        )
        try:
            _update_document_state(doc_id, "failed", error_message[:1000])
        except Exception:
            logger.exception("Could not mark failed document_id=%s as failed", doc_id)
    finally:
        with _active_document_ids_lock:
            _active_document_ids.discard(doc_id)


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    if file is None or file.filename is None or file.filename == "":
        raise HTTPException(status_code=400, detail="No file uploaded.")

    filename = os.path.basename(file.filename.replace("\\", "/"))
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    if file.content_type not in (None, "", "application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="The uploaded file must have PDF content.")

    file_bytes = await file.read(MAX_FILE_SIZE_BYTES + 1)
    await file.close()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f}MB.")
    if b"%PDF-" not in file_bytes[:1024]:
        raise HTTPException(status_code=400, detail="The uploaded file is not a readable PDF.")

    try:
        reader = PdfReader(BytesIO(file_bytes), strict=True)
        if reader.is_encrypted:
            raise HTTPException(status_code=400, detail="Password-protected PDFs are not supported. Remove the password and upload the PDF again.")
        if not reader.pages:
            raise HTTPException(status_code=400, detail="The PDF contains no pages.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.info("Rejected unreadable PDF filename=%s user_id=%s: %s", filename, current_user.id, exc)
        raise HTTPException(status_code=400, detail="The PDF is corrupted or unreadable. Please check the file and upload it again.") from exc

    logger.info("[UPLOAD] File received filename=%s size_bytes=%s user_id=%s", filename, len(file_bytes), current_user.id)

    user_upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_upload_dir, exist_ok=True)
    filepath = os.path.join(user_upload_dir, f"{uuid.uuid4().hex}.pdf")

    doc = Document(
        filename=filename,
        filepath=filepath,
        owner_id=current_user.id,
        status="uploaded",
        processing_progress=0,
        processing_error=None,
    )
    try:
        with open(filepath, "xb") as f:
            f.write(file_bytes)
    except Exception:
        if os.path.exists(filepath):
            os.remove(filepath)
        logger.exception("Failed to write uploaded PDF filename=%s user_id=%s", filename, current_user.id)
        raise HTTPException(status_code=500, detail="The PDF could not be saved. Please try uploading it again.")

    try:
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except Exception:
        db.rollback()
        if os.path.exists(filepath):
            os.remove(filepath)
        logger.exception("Failed to save uploaded document filename=%s user_id=%s", filename, current_user.id)
        raise HTTPException(status_code=500, detail="The PDF could not be saved. Please try uploading it again.")

    logger.info("[UPLOAD] Document saved document_id=%s user_id=%s", doc.id, current_user.id)
    background_tasks.add_task(process_document_background, doc.id, filepath, current_user.id)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "processing_progress": doc.processing_progress,
        "processing_error": doc.processing_error,
    }

@router.get("/")
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    docs = db.query(Document).filter(Document.owner_id == current_user.id).all()
    now = datetime.now(timezone.utc)
    changed = False
    for doc in docs:
        if doc.status in ("uploaded", "processing", "completed", "indexed") and not os.path.exists(doc.filepath):
            doc.status = "failed"
            doc.processing_error = "The uploaded PDF is missing from server storage. Re-upload it to restore access."
            doc.processing_started_at = None
            changed = True
        elif doc.status in ("uploaded", "processing"):
            started_at = doc.processing_started_at or doc.created_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if now - started_at > PROCESSING_TIMEOUT:
                doc.status = "failed"
                doc.processing_error = "Indexing took too long and was marked as failed. Retry the document or upload it again."
                doc.processing_started_at = None
                changed = True
    if changed:
        db.commit()

    return [{
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "processing_progress": doc.processing_progress,
        "processing_error": doc.processing_error,
        "owner_id": doc.owner_id,
    } for doc in docs]


@router.post("/{document_id}/retry")
async def retry_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id, Document.owner_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")
    if not os.path.exists(doc.filepath):
        raise HTTPException(status_code=404, detail="File not found on disk. Please re-upload the PDF.")
    with _active_document_ids_lock:
        if document_id in _active_document_ids:
            raise HTTPException(status_code=409, detail="This document is already being indexed.")
    if doc.status == "processing":
        raise HTTPException(status_code=409, detail="This document is already being indexed.")

    doc.status = "uploaded"
    doc.processing_progress = 0
    doc.processing_error = None
    doc.processing_started_at = datetime.now(timezone.utc)
    db.commit()

    background_tasks.add_task(process_document_background, doc.id, doc.filepath, current_user.id)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}

@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id, Document.owner_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    with _active_document_ids_lock:
        if document_id in _active_document_ids:
            raise HTTPException(status_code=409, detail="This document cannot be deleted while it is being indexed.")

    filepath = doc.filepath
    
    # 1. Delete from FAISS
    try:
        rag_engine.delete_pdf(filepath, current_user.id)
    except Exception as e:
        print(f"Error deleting {filepath} from FAISS: {e}")
        
    # 2. Delete local file
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")
            
    # 3. Delete from PostgreSQL
    db.delete(doc)
    db.commit()
    
    return {"status": "success", "message": f"Deleted document {document_id}"}
