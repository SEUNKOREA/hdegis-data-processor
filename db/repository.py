import os
import sys
from typing import List

from sqlalchemy import distinct
from sqlalchemy.orm import Session
from sqlalchemy import select

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


    def list_all_document_hashes(self) -> set[str]:
        result = (
            self.session.query(PDFDocument.doc_id)
            .all()
        )
        return {row[0] for row in result}


    def exists_document(self, doc_id: str) -> bool:
        return self.session.query(PDFDocument).filter_by(doc_id=doc_id).first() is not None


    def create_document(self, doc_id: str, gcs_path: str) -> PDFDocument:
        doc = PDFDocument(doc_id=doc_id, gcs_path=gcs_path)
        self.session.add(doc)
        self.session.commit()
        return doc


    def create_page_record(self, doc_id: str, page_number:int, gcs_path: str, gcs_pdf_path: str) -> PDFPage:
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


    def update_page_record(self, page_id: str, **kwargs):
        page = self.session.get(PDFPage, page_id)
        if page:
            for k, v in kwargs.items():
                if v is not None:
                    setattr(page, k, v)
            self.session.commit()


    def get_first_n_pages(self, doc_id: str, n: int = 5) -> List[str]:
        stmt = (
            select(PDFPage.gcs_path)
            .where(PDFPage.doc_id == doc_id)
            .order_by(PDFPage.page_number.asc())
            .limit(n)
        )
        return self.session.scalars(stmt).all()


    def get_pages_for_extraction(self) -> List[PDFPage]:
        return (
            self.session.query(PDFPage)
            .filter(PDFPage.extracted.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )


    def get_pages_for_summary(self) -> List[PDFPage]:
        return (
            self.session.query(PDFPage)
            .filter(PDFPage.summarized.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )

    def get_pages_for_embedding(self) -> List[PDFPage]:
        return (
            self.session.query(PDFPage)
            .filter(PDFPage.extracted == PageStatus.SUCCESS)
            .filter(PDFPage.summarized == PageStatus.SUCCESS)
            .filter(PDFPage.embedded.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )


    def get_pages_for_indexing(self) -> List[PDFPage]:
        return (
            self.session.query(PDFPage)
            .filter(PDFPage.embedded == PageStatus.SUCCESS)
            .filter(PDFPage.indexed.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )