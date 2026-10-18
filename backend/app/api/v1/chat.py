import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api import deps
from app.db.database import get_db
from app.db.models import User, ChatMessage, Document
from app.rag import rag_engine

router = APIRouter()
logger = logging.getLogger(__name__)

class QueryRequest(BaseModel):
    query: str = Field(..., max_length=2000)

@router.post("/query")
async def query_documents(
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    started_at = time.perf_counter()
    logger.info("Chat query received user_id=%s query_length=%s", current_user.id, len(request.query))
    try:
        indexed_documents = db.query(Document).filter(
            Document.owner_id == current_user.id,
            Document.status.in_(("completed", "indexed")),
        ).all()
        if not indexed_documents:
            processing_documents = db.query(Document.id).filter(
                Document.owner_id == current_user.id,
                Document.status.in_(("uploaded", "processing")),
            ).first()
            if processing_documents:
                detail = "Your PDF is still being indexed. Please wait until its status is indexed before asking a question."
            else:
                detail = "No indexed PDFs are available. Upload a valid PDF and wait until indexing is complete."
            raise HTTPException(status_code=409, detail=detail)

        try:
            answer_text, sources = rag_engine.generate_answer(
                request.query,
                current_user.id,
                indexed_document_ids=[document.id for document in indexed_documents],
                indexed_document_sources=[document.filepath for document in indexed_documents],
            )
        except rag_engine.RAGError as re:
            raise HTTPException(status_code=503, detail=str(re)) from re

        user_msg = ChatMessage(user_id=current_user.id, role="user", content=request.query)
        asst_msg = ChatMessage(
            user_id=current_user.id,
            role="assistant",
            content=answer_text,
            sources=json.dumps(sources)
        )
        db.add_all([user_msg, asst_msg])
        db.commit()
        logger.info("Chat query completed user_id=%s duration=%.2fs", current_user.id, time.perf_counter() - started_at)

        return {"answer": answer_text, "sources": sources}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Chat query failed unexpectedly user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat request failed before a response could be generated.",
        ) from exc

@router.get("/history")
def get_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    logger.info("Loading chat history user_id=%s", current_user.id)
    messages = db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).order_by(ChatMessage.created_at.asc()).all()
    history = []
    for msg in messages:
        history.append({
            "role": msg.role,
            "content": msg.content,
            "sources": json.loads(msg.sources) if msg.sources else []
        })
    return history
