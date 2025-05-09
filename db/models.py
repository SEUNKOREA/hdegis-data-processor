import enum
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, ForeignKey
)

# 모든 ORM 모델의 기본이 되는 클래스를 정의
# 아래의 테이블 클래스들이 이 Base를 상속해서 만들어야 실제 테이블로 인식됨
Base = declarative_base()


class PageStatus(enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class PDFDocument(Base):
    __tablename__ = "pdf_documents"

    id: int = Column(Integer, primary_key=True)
    gcs_path: str = Column(String(1000), unique=True, nullable=False)
    uploaded_at: datetime = Column(DateTime, default=datetime.utcnow)
    processed: int = Column(Integer, default=0)
    processed_at: datetime = Column(DateTime, nullable=True)
    error_message: str = Column(Text, nullable=True)


class PDFPage(Base):
    __tablename__ = "pdf_pages"

    id: int = Column(Integer, primary_key=True)
    document_id: int = Column(Integer, ForeignKey("pdf_documents.id"), nullable=False)
    page_number: int = Column(Integer, nullable=False)
    gcs_path: str = Column(String(1000), nullable=False)
    extracted_text: str = Column(Text, nullable=True)
    description: str = Column(Text, nullable=True)
    status: PageStatus = Column(Enum(PageStatus), default=PageStatus.PENDING)
    error_message: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
