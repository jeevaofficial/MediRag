import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db, SessionLocal
from app.db.models import User, Document
from app.core.config import settings
from app.rag import rag_engine

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


def _update_document_state(doc_id: int, status: str, error_message: Optional[str] = None):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return
        doc.status = status
        doc.processing_error = error_message
        db.commit()
        logger.info("[STATUS] Document %s status=%s error=%s", doc_id, status, error_message)
    except Exception as exc:
        logger.exception("[ERROR] Failed to update document %s status to %s: %s", doc_id, status, exc)
    finally:
        db.close()


def process_document_background(doc_id: int, filepath: str, user_id: int):
    logger.info("[UPLOAD] Starting background processing for document_id=%s filepath=%s user_id=%s", doc_id, filepath, user_id)
    try:
        _update_document_state(doc_id, "processing", None)
        rag_engine.ingest_pdf(filepath, user_id, document_id=doc_id)
        _update_document_state(doc_id, "completed", None)
        logger.info("[INDEX] Document indexing completed document_id=%s", doc_id)
    except Exception as exc:
        error_message = str(exc)
        logger.exception("[ERROR] Background indexing failed for document_id=%s filepath=%s: %s", doc_id, filepath, error_message)
        _update_document_state(doc_id, "failed", error_message)


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    if file is None or file.filename is None or file.filename == "":
        raise HTTPException(status_code=400, detail="No file uploaded.")

    filename = os.path.basename(file.filename)
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f}MB.")

    logger.info("[UPLOAD] File received filename=%s size_bytes=%s user_id=%s", filename, file_size, current_user.id)

    user_upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_upload_dir, exist_ok=True)
    filepath = os.path.join(user_upload_dir, filename)

    counter = 1
    original_filepath = filepath
    while os.path.exists(filepath):
        name, ext = os.path.splitext(original_filepath)
        filepath = f"{name}_{counter}{ext}"
        counter += 1

    file_bytes = await file.read()
    if len(file_bytes) <= 0:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    doc = Document(
        filename=os.path.basename(filepath),
        filepath=filepath,
        owner_id=current_user.id,
        status="processing",
        processing_error=None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    logger.info("[UPLOAD] Document saved to database document_id=%s filepath=%s", doc.id, filepath)
    background_tasks.add_task(process_document_background, doc.id, filepath, current_user.id)

    return {"id": doc.id, "filename": doc.filename, "status": doc.status, "processing_error": doc.processing_error}

@router.get("/")
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    docs = db.query(Document).filter(Document.owner_id == current_user.id).all()

    valid_docs = []
    for d in docs:
        if os.path.exists(d.filepath):
            valid_docs.append(d)
        else:
            db.delete(d)

    if len(valid_docs) != len(docs):
        db.commit()

    return [{
        "id": d.id,
        "filename": d.filename,
        "status": d.status,
        "processing_error": d.processing_error,
        "owner_id": d.owner_id,
    } for d in valid_docs]


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

    doc.status = "processing"
    doc.processing_error = None
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

