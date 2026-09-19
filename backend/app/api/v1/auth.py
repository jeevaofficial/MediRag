from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel, Field

from app.api import deps
from app.core.config import settings
from app.db.database import get_db
from app.db.models import User

router = APIRouter()

class UserCreate(BaseModel):
    full_name: str = Field(..., max_length=100)
    username: str = Field(..., max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    full_name = user_in.full_name.strip()
    username = user_in.username.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    user = db.query(User).filter(User.username == username).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    user = User(
        full_name=full_name,
        username=username,
        hashed_password=deps.get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = deps.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not deps.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = deps.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str

@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(deps.get_current_user)):
    return {"id": current_user.id, "username": current_user.username, "full_name": current_user.full_name}
