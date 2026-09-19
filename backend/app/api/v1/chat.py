import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api import deps
from app.db.database import get_db
from app.db.models import User, ChatMessage
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
        user_msg = ChatMessage(user_id=current_user.id, role="user", content=request.query)
        db.add(user_msg)
        db.commit()
        logger.info("User chat message staged user_id=%s", current_user.id)

        try:
            answer_text, sources = rag_engine.generate_answer(request.query, current_user.id)
        except rag_engine.RAGError as re:
            raise HTTPException(status_code=400, detail=str(re))
            
        asst_msg = ChatMessage(
            user_id=current_user.id,
            role="assistant",
            content=answer_text,
            sources=json.dumps(sources)
        )
        db.add(asst_msg)
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
