import os
import sys
import enum
from datetime import datetime

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, ForeignKey
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from config import TABLENAME_PDFPAGE, TABLENAME_PDFDOCUMENT


# 모든 ORM 모델의 기본이 되는 클래스를 정의
# 아래의 테이블 클래스들이 이 Base를 상속해서 만들어야 실제 테이블로 인식됨
Base = declarative_base()

class PageStatus(enum.Enum):
    PENDING = "PENDING"     # 아직 시도 안 함
    SUCCESS = "SUCCESS"     # 처리 완료
    FAILED = "FAILED"       # 처리 실패

class PDFPage(Base):
    __tablename__ = TABLENAME_PDFPAGE

    page_id: int = Column(String(128), primary_key=True)
    doc_id: str = Column(String(128), ForeignKey("pdf_documents.doc_id"), nullable=False)
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

    document = relationship("PDFDocument", back_populates="pages")


class PDFDocument(Base):
    __tablename__ = TABLENAME_PDFDOCUMENT

    doc_id: str = Column(String(128), primary_key=True)
    gcs_path: str = Column(String(1000), nullable=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)

    pages = relationship("PDFPage", back_populates="document", cascade="all, delete-orphan")
        # back_populates="document"     : document.pages로 페이지 접근 가능, page.document로 해당 페이지가 속한 문서 확인가능
        # cascade="all, delete-orphan"  : 부모(PDFDocument)가 삭제되었을때 자식(PDFPage)도 자동으로 처리되도록