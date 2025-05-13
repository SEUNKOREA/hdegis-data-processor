import os
import sys
# 프로젝트 폴더를 루트로 가정
PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, select
from datetime import datetime

from db.models import PDFDocument, PDFPage, PageStatus

import tempfile
import os
from storage.gcs_client import GCSStorageClient
from utils.utils import get_file_hash
from config import GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET

class Repository:
    def __init__(self, session: Session) -> None:
        """
        생성 시 SQLAlchemy 세션 주입
        """
        self.session = session

    # ────────────────────────────────
    # 문서 관련 (PDFDocument)
    # ────────────────────────────────

    def document_exists(self, gcs_path: str) -> bool:
        """
        이미 해당 GCS 경로가 등록되어 있는지 확인
        PDFDocument 테이블에서 gcs_path가 주어진 경로와 같은 row가 있는지 확인
        있으면 True, 없으면 False를 반환
        """
        return self.session.query(PDFDocument).filter_by(gcs_path=gcs_path).first() is not None

    def create_document(self, gcs_path: str, storage_client: GCSStorageClient) -> PDFDocument:
        """
        새로운 문서를 DB에 등록
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            local_pdf = os.path.join(tmpdir, "doc.pdf")
            storage_client.download_file(gcs_path, local_pdf, storage_client.source_bucket)

            doc_id = get_file_hash(local_pdf)

        document = PDFDocument(doc_id=doc_id, gcs_path=gcs_path)
        self.session.add(document)
        self.session.commit()
        return document

    def get_pending_documents(self) -> List[PDFDocument]:
        """
        processed=0 문서 목록 반환 (split 아직 안 했거나 split 실패한 문서)
        """
        return self.session.query(PDFDocument).filter_by(processed=0).all()

    def mark_document_split(self, document_id: int, success: bool) -> None:
        """
        split_pdf_to_images 단계 결과에 따라 processed와 processed_at 업데이트
        """
        doc = self.session.query(PDFDocument).get(document_id)
        if not doc:
            return
        doc.processed = 1 if success else 0
        doc.processed_at = datetime.utcnow()
        self.session.commit()


    # ────────────────────────────────
    # 페이지 관련 (PDFPage)
    # ────────────────────────────────

    def create_page_record(
        self,
        doc_id: int,
        page_number: int,
        gcs_path: str,
        gcs_pdf_path: str,
    ) -> PDFPage:
        """
        새 페이지 레코드 생성 (처리 전)
        """
        page = PDFPage(
            page_id=f"{doc_id}{page_number}",
            doc_id=doc_id,
            page_number=page_number,
            gcs_path=gcs_path,
            gcs_pdf_path=gcs_pdf_path,
            extracted_text=None,
            summary=None,
            status=PageStatus.PENDING,
            error_message=None
        )
        self.session.add(page)
        self.session.commit()
        return page

    def update_page_record(
        self,
        page_id: int,
        *,
        extracted_text: Optional[str] = None,
        summary: Optional[str] = None,
        status: Optional[PageStatus] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        페이지 OCR 및 설명 결과 업데이트
        """
        page = self.session.query(PDFPage).get(page_id)
        if not page:
            return
        if extracted_text is not None:
            page.extracted_text = extracted_text
        if summary is not None:
            page.summary = summary
        if status is not None:
            page.status = status
        if error_message is not None:
            page.error_message = error_message
        self.session.commit()

    # def get_failed_pages(self) -> List[PDFPage]:
    #     """
    #     처리 실패한(status=FAILED 인) 페이지 목록 가져오기 (재처리용)
    #     """
    #     return self.session.query(PDFPage).filter_by(status=PageStatus.FAILED).all()

    def get_failed_pages(self) -> List[PDFPage]:
        """
        처리 실패한(status=FAILED) 또는 미처리(status=PENDING) 페이지 목록 가져오기 (재처리용)
        """
        return (
            self.session.query(PDFPage)
            .filter(or_(
                PDFPage.status == PageStatus.FAILED,
                PDFPage.status == PageStatus.PENDING
            ))
            .all()
        )
    
    def get_first_n_pages(self, document_id: str, n: int = 5) -> List[str]:
        stmt = (
            select(PDFPage.gcs_path)
            .where(PDFPage.doc_id == document_id)
            .order_by(PDFPage.page_number.asc())
            .limit(n)
        )
        return self.session.scalars(stmt).all()
# if __name__ == "__main__":
    