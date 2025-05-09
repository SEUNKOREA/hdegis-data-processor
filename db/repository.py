from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

from db.models import PDFDocument, PDFPage, PageStatus


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

    def create_document(self, gcs_path: str) -> PDFDocument:
        """
        새로운 문서를 DB에 등록
        """
        document = PDFDocument(gcs_path=gcs_path)
        self.session.add(document)
        self.session.commit()
        return document

    def get_pending_documents(self) -> List[PDFDocument]:
        """
        아직 처리되지 않은 문서(processed=0) 목록 반환
        """
        return self.session.query(PDFDocument).filter_by(processed=0).all()

    def mark_document_processed(self, gcs_path: str) -> None:
        """
        문서 처리 완료 표시
        processed = 1로 바꾸고, 시간도 기록
        """
        doc = self.session.query(PDFDocument).filter_by(gcs_path=gcs_path).first()
        if doc:
            doc.processed = 1
            doc.processed_at = datetime.utcnow()
            self.session.commit()

    # ────────────────────────────────
    # 페이지 관련 (PDFPage)
    # ────────────────────────────────

    def create_page_record(
        self,
        document_id: int,
        page_number: int,
        gcs_path: str
    ) -> PDFPage:
        """
        새 페이지 레코드 생성 (처리 전)
        """
        page = PDFPage(
            document_id=document_id,
            page_number=page_number,
            gcs_path=gcs_path,
            extracted_text=None,
            description=None,
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
        description: Optional[str] = None,
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
        if description is not None:
            page.description = description
        if status is not None:
            page.status = status
        if error_message is not None:
            page.error_message = error_message

        self.session.commit()

    def get_failed_pages(self) -> List[PDFPage]:
        """
        처리 실패한 페이지 목록 가져오기 (재처리용)
        """
        return self.session.query(PDFPage).filter_by(status=PageStatus.FAILED).all()