import os
import sys
from typing import List, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, select

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from db.models import PDFDocument, PDFPage, PageStatus
from storage.gcs_client import GCSStorageClient
from utils.logger import get_logger
from config import LOG_LEVEL

class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.logger = get_logger(self.__class__.__name__, LOG_LEVEL)

    # ── 문서 관련 ─────────────────────────────────────────────
    def list_all_document_hashes(self) -> set[str]:
        return {row.doc_id for row in self.session.query(PDFDocument.doc_id).all()}

    def create_document(self, doc_id: str, gcs_path: str, storage_client: GCSStorageClient) -> PDFDocument:
        doc = PDFDocument(doc_id=doc_id, gcs_path=gcs_path)
        self.session.add(doc)
        self.session.commit()
        return doc

    def mark_document_split(self, doc_id: str, success: bool):
        doc = self.session.get(PDFDocument, doc_id)
        if doc:
            doc.processed = 1 if success else 0
            doc.processed_at = datetime.utcnow()
            self.session.commit()

    def get_failed_documents(self) -> List[PDFDocument]:
        return (self.session.query(PDFDocument)
                .filter(PDFDocument.processed == 0,
                        PDFDocument.processed_at.is_not(None))
                .all())

    # ── 페이지 관련 ─────────────────────────────────────────────
    def create_page_record(self, *, doc_id: str, page_number:int, gcs_path: str, gcs_pdf_path: str) -> PDFPage:
        page = PDFPage(
            page_id=f"{doc_id}_{page_number:05d}",
            doc_id=doc_id,
            page_number=f"{page_number:05d}",
            gcs_path=gcs_path,
            gcs_pdf_path=gcs_pdf_path
        )
        self.session.add(page)
        self.session.commit()
        return page

    def get_first_n_pages(self, doc_id: str, n: int = 5) -> List[str]:
        stmt = (
            select(PDFPage.gcs_path)
            .where(PDFPage.doc_id == doc_id)
            .order_by(PDFPage.page_number.asc())
            .limit(n)
        )
        return self.session.scalars(stmt).all()


    def update_page_record(self, page_id: str, **kwargs):
        page = self.session.get(PDFPage, page_id)
        if page:
            for k, v in kwargs.items():
                if v is not None:
                    setattr(page, k, v)
            self.session.commit()


    def get_failed_pages(self) -> List[PDFPage]:
        """
        처리 실패한(extracted=FAILED 인) 페이지 목록 가져오기 (재처리용)
        """
        return (self.session.query(PDFPage)
                .filter_by(extracted=PageStatus.FAILED)
                .all())