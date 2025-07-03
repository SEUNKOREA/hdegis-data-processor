import os
import sys
import datetime
from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import select

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from db.models import PDFDocument, PDFPage, PageStatus, DocumentStatus, PipelineStatus, PipelineStatusEnum
from storage.gcs_client import GCSStorageClient
from utils.logger import get_logger
from config import LOG_LEVEL, TABLENAME_PDFDOCUMENTS, TABLENAME_PDFPAGES, TABLENAME_PIPELINE

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
            .filter(PDFPage.status == DocumentStatus.ACTIVE) # ACTIVE 문서에 대해서
            .filter(PDFPage.extracted.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )


    def get_pages_for_summary(self) -> List[PDFPage]:
        return (
            self.session.query(PDFPage)
            .filter(PDFPage.status == DocumentStatus.ACTIVE) # ACTIVE 문서에 대해서
            .filter(PDFPage.summarized.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )

    def get_pages_for_embedding(self) -> List[PDFPage]:
        return (
            self.session.query(PDFPage)
            .filter(PDFPage.status == DocumentStatus.ACTIVE) # ACTIVE 문서에 대해서
            .filter(PDFPage.extracted == PageStatus.SUCCESS)
            .filter(PDFPage.summarized == PageStatus.SUCCESS)
            .filter(PDFPage.embedded.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )


    def get_pages_for_indexing(self) -> List[PDFPage]:
        return (
            self.session.query(PDFPage)
            .filter(PDFPage.status == DocumentStatus.ACTIVE) # ACTIVE 문서에 대해서
            .filter(PDFPage.embedded == PageStatus.SUCCESS)
            .filter(PDFPage.indexed.in_([PageStatus.PENDING, PageStatus.FAILED]))
            .all()
        )


    def update_content_hash(self, doc_id: str, content_hash: str):
        """문서의 content_hash 업데이트"""
        doc = self.session.get(PDFDocument, doc_id)
        if doc:
            doc.content_hash = content_hash
            self.session.commit()
    

    def get_documents_by_content_hash(self, content_hash: str) -> List[PDFDocument]:
        """content_hash로 문서 조회 (이동 감지용)"""
        return self.session.query(PDFDocument).filter(
            PDFDocument.content_hash == content_hash,
            PDFDocument.status == DocumentStatus.ACTIVE
        ).all()


    def get_doc_id_by_content_hash(self, content_hash: str) -> str:
        """content_hash로 doc_id 조회 (ACTIVE 문서만)"""
        doc = self.session.query(PDFDocument).filter(
            PDFDocument.content_hash == content_hash,
            PDFDocument.status == DocumentStatus.ACTIVE
        ).first()
        return doc.doc_id if doc else None
    
    def update_document_status(self, doc_id: str, status: DocumentStatus):
        """문서 상태 업데이트"""
        doc = self.session.get(PDFDocument, doc_id)
        if doc:
            doc.status = status
            self.session.commit()
            self.logger.info(f"문서 상태 변경: {doc_id} -> {status.value}")
    
    def get_active_document_ids(self) -> List[str]:
        """ACTIVE 문서 ID 목록 반환 (검색 필터링용)"""
        return [doc.doc_id for doc in self.session.query(PDFDocument.doc_id)
                .filter(PDFDocument.status == DocumentStatus.ACTIVE).all()]


    # === 파이프라인 상태 관리 메서드들 ===
    def get_current_pipeline_status(self) -> str:
        """현재 파이프라인 상태 조회"""
        latest = self.session.query(PipelineStatus)\
                     .order_by(PipelineStatus.id.desc())\
                     .first()
        return latest.status.value if latest else "IDLE"

    def update_pipeline_status(self, status: PipelineStatusEnum, stage: str = None, **kwargs):
        """파이프라인 상태 업데이트"""
        latest = self.session.query(PipelineStatus)\
                     .order_by(PipelineStatus.id.desc())\
                     .first()
        
        if latest:
            latest.status = status
            if stage:
                latest.stage = stage
            if status == PipelineStatusEnum.RUNNING and not latest.started_at:
                latest.started_at = datetime.utcnow()
            if status in [PipelineStatusEnum.COMPLETED, PipelineStatusEnum.FAILED]:
                latest.completed_at = datetime.utcnow()
            
            for key, value in kwargs.items():
                if hasattr(latest, key):
                    setattr(latest, key, value)
        
        self.session.commit()

    def sync_page_status_with_documents(self):
        """Document 상태에 따라 Page 상태 동기화"""
        try:
            # INACTIVE Document의 모든 Page를 INACTIVE로
            inactive_result = self.session.execute(text(f"""
                UPDATE {TABLENAME_PDFPAGES} p
                JOIN {TABLENAME_PDFDOCUMENTS} d ON p.doc_id = d.doc_id
                SET p.status = 'INACTIVE'
                WHERE d.status = 'INACTIVE' AND p.status = 'ACTIVE'
            """))
            
            # ACTIVE Document의 모든 Page를 ACTIVE로
            active_result = self.session.execute(text(f"""
                UPDATE {TABLENAME_PDFPAGES} p  
                JOIN {TABLENAME_PDFDOCUMENTS} d ON p.doc_id = d.doc_id
                SET p.status = 'ACTIVE'
                WHERE d.status = 'ACTIVE' AND p.status = 'INACTIVE'
            """))
            
            self.session.commit()
            
            # 결과 로깅
            inactive_count = inactive_result.rowcount if hasattr(inactive_result, 'rowcount') else 0
            active_count = active_result.rowcount if hasattr(active_result, 'rowcount') else 0
            
            self.logger.info(f"Document ↔ Page 상태 동기화 완료")
            self.logger.info(f"  INACTIVE로 변경된 페이지: {inactive_count}개")
            self.logger.info(f"  ACTIVE로 변경된 페이지: {active_count}개")
            
        except Exception as e:
            self.logger.error(f"상태 동기화 실패: {e}")
            self.session.rollback()
            raise

    def check_processing_completion(self) -> bool:
        """모든 ACTIVE 페이지가 처리 완료되었는지 확인"""
        pending_count = self.session.query(PDFPage).filter(
            PDFPage.status == DocumentStatus.ACTIVE,  # ACTIVE 페이지만 확인
            (PDFPage.extracted != PageStatus.SUCCESS) |
            (PDFPage.summarized != PageStatus.SUCCESS) |
            (PDFPage.embedded != PageStatus.SUCCESS) |
            (PDFPage.indexed != PageStatus.SUCCESS)
        ).count()
        
        return pending_count == 0
    
    def get_processing_stats(self) -> dict:
        """처리 현황 통계 조회"""
        total_active = self.session.query(PDFPage).filter(
            PDFPage.status == DocumentStatus.ACTIVE
        ).count()
        
        completed = self.session.query(PDFPage).filter(
            PDFPage.status == DocumentStatus.ACTIVE,
            PDFPage.extracted == PageStatus.SUCCESS,
            PDFPage.summarized == PageStatus.SUCCESS,
            PDFPage.embedded == PageStatus.SUCCESS,
            PDFPage.indexed == PageStatus.SUCCESS
        ).count()
        
        return {
            "total_active_pages": total_active,
            "completed_pages": completed,
            "remaining_pages": total_active - completed,
            "completion_rate": (completed / total_active * 100) if total_active > 0 else 0
        }