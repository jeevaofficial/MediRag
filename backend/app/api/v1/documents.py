import os
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.db.models import User, Document
from app.core.config import settings
from app.rag import rag_engine

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    # Enforce a 10MB file size limit
    MAX_FILE_SIZE = 10 * 1024 * 1024
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    filename = os.path.basename(file.filename)
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    user_upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_upload_dir, exist_ok=True)
    filepath = os.path.join(user_upload_dir, filename)
    
    # Check if already exists to avoid overwriting blindly
    counter = 1
    original_filepath = filepath
    while os.path.exists(filepath):
        name, ext = os.path.splitext(original_filepath)
        filepath = f"{name}_{counter}{ext}"
        counter += 1

    with open(filepath, "wb") as f:
        f.write(await file.read())
        
    doc = Document(
        filename=os.path.basename(filepath),
        filepath=filepath,
        owner_id=current_user.id,
        status="processing"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    try:
        # In a real production app, this should be a background task (e.g. Celery or BackgroundTasks)
        rag_engine.ingest_pdf(filepath, current_user.id)
        doc.status = "indexed"
    except Exception as e:
        doc.status = "error"
        print(f"Error indexing {filepath}: {e}")
    
    db.commit()
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}

@router.get("/")
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    # Only show user's docs
    docs = db.query(Document).filter(Document.owner_id == current_user.id).all()
    return [{"id": d.id, "filename": d.filename, "status": d.status, "owner_id": d.owner_id} for d in docs]

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

