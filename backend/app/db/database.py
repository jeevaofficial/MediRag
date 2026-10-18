from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def ensure_schema():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "users" in table_names:
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "full_name" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR NOT NULL DEFAULT ''"))

    if "documents" in table_names:
        columns = {column["name"] for column in inspector.get_columns("documents")}
        if "processing_error" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN processing_error TEXT"))
        if "processing_started_at" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN processing_started_at TIMESTAMP"))
        if "processing_progress" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE documents ADD COLUMN processing_progress INTEGER NOT NULL DEFAULT 0")
                )
                conn.execute(
                    text(
                        "UPDATE documents SET processing_progress = 100 "
                        "WHERE status IN ('completed', 'indexed')"
                    )
                )

ensure_user_schema = ensure_schema

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
