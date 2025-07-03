import enum
from datetime import datetime

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey, BigInteger, Integer
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from config import TABLENAME_PDFPAGES, TABLENAME_PDFDOCUMENTS, TABLENAME_PIPELINE


# 모든 ORM 모델의 기본이 되는 클래스를 정의
# 아래의 테이블 클래스들이 이 Base를 상속해서 만들어야 실제 테이블로 인식됨
Base = declarative_base()


class PipelineStatusEnum(enum.Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class DocumentStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class PageStatus(enum.Enum):
    PENDING = "PENDING"  # 아직 시도 안 함
    SUCCESS = "SUCCESS"  # 처리 완료
    FAILED = "FAILED"  # 처리 실패


class PipelineStatus(Base):
    __tablename__ = TABLENAME_PIPELINE

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    status: str = Column(Enum(PipelineStatusEnum), default=PipelineStatusEnum.IDLE)
    stage: str = Column(String(50), nullable=True)
    started_at: datetime = Column(DateTime, nullable=True)
    completed_at: datetime = Column(DateTime, nullable=True)
    total_documents: int = Column(Integer, default=0)
    processed_documents: int = Column(Integer, default=0)
    error_message: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)


class PDFDocument(Base):
    __tablename__ = TABLENAME_PDFDOCUMENTS

    doc_id: str = Column(String(128), primary_key=True)
    gcs_path: str = Column(String(1000), nullable=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    file_size: int = Column(BigInteger)
    last_modified: datetime = Column(DateTime, nullable=True)
    status: str = Column(Enum(DocumentStatus), default=DocumentStatus.ACTIVE)
    updated_at: datetime = Column(DateTime, default=func.now(), onupdate=func.now())
    content_hash: str = Column(String(128), nullable=False)

    pages = relationship("PDFPage", back_populates="document", cascade="all, delete-orphan")
    # back_populates="document"     : document.pages로 페이지 접근 가능, page.document로 해당 페이지가 속한 문서 확인가능
    # cascade="all, delete-orphan"  : 부모(PDFDocument)가 삭제되었을때 자식(PDFPage)도 자동으로 처리되도록


class PDFPage(Base):
    __tablename__ = TABLENAME_PDFPAGES

    page_id: int = Column(String(128), primary_key=True)
    doc_id: str = Column(String(128), ForeignKey(f"{TABLENAME_PDFDOCUMENTS}.doc_id"), nullable=False)
    page_number: str = Column(String(32), nullable=False)
    gcs_path: str = Column(String(1000), nullable=False)
    gcs_pdf_path: str = Column(String(1000), nullable=False)
    extracted_text: str = Column(LONGTEXT, nullable=True)
    summary: str = Column(LONGTEXT, nullable=True)
    embedding: str = Column(LONGTEXT, nullable=True)
    extracted: PageStatus = Column(Enum(PageStatus), default=PageStatus.PENDING)
    summarized: PageStatus = Column(Enum(PageStatus), default=PageStatus.PENDING)
    embedded: PageStatus = Column(Enum(PageStatus), default=PageStatus.PENDING)
    indexed: PageStatus = Column(Enum(PageStatus), default=PageStatus.PENDING)
    error_message: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=func.now(), onupdate=func.now())
    status: str = Column(Enum(DocumentStatus), default=DocumentStatus.ACTIVE)
    
    document = relationship("PDFDocument", back_populates="pages")