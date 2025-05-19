import os
import sys
from typing import List, Tuple

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from google.cloud import storage

from storage.gcs_client import GCSStorageClient
from processor.pdf_manager import PDFManager
from db.init_db import init_tables
from db.session import get_db_session
from db.repository import Repository
from db.models import PageStatus
from config import (
    GCS_SOURCE_BUCKET, 
    GCS_PROCESSED_BUCKET,
    LOG_LEVEL,
)
from utils.utils import compute_doc_hash
from utils.logger import get_logger

logger = get_logger(__name__, LOG_LEVEL)


def run_pipeline() -> None:
    """
    전체 파이프라인 실행:
    - GCS에서 PDF 목록 수집
    - DB에 등록되지 않은 PDF 문서를 추가
    - 처리되지 않은 문서만 PDFManager를 통해 처리
    """
    logger.info("[START] INITIALIZE TABLE")
    init_tables()
    logger.info("[DONE] INITIALIZE TABLE")

    # DB 세션 열기
    db_gen = get_db_session()
    session = next(db_gen)
    
    try:
        # Repository, GCS 클라이언트, PDFManager 초기화
        repo = Repository(session)
        gcs_client = storage.Client()
        storage_client = GCSStorageClient(
            source_bucket=GCS_SOURCE_BUCKET,
            target_bucket=GCS_PROCESSED_BUCKET,
            client=gcs_client
        )
        manager = PDFManager(storage_client, repo)


        # ---------------- 1. 신규 문서 탐지 및 처리 ----------------
        logger.info("[START] DETECT NEW DOCUMENTS ...")
        pdf_paths = storage_client.list_pdfs(prefix="")
        logger.info("총 GCS PDF: %d", len(pdf_paths))

        known_hashes = repo.list_all_document_hashes()
        new_docs: List[Tuple[str, str]] = []  # (hash, path)
        for p in pdf_paths:
            try:
                h = compute_doc_hash(storage_client, p)
            except Exception as e:
                logger.error("해시 계산 실패 (skip) (%s): %s", p, e)
                continue
            if h not in known_hashes:
                new_docs.append((h, p))

        if new_docs:
            logger.info("신규 문서: %d건", len(new_docs))
        else:
            logger.info("신규 문서 없음")
        logger.info("[DONE] DETECT NEW DOCUMENTS")

        logger.info("[START] PROCESS NEW DOCUMENTS ...")
        for i, (h, p) in enumerate(new_docs, start=1):
            repo.create_document(h, p, storage_client)           
            manager.process_document(doc_id=h, gcs_pdf_path=p, tag="NEW", index=i, total=len(new_docs))
        logger.info("[DONE] PROCESS NEW DOCUMENTS")


        # ---------------- 2. Document-level 재시도 ----------------
        logger.info("[START] PROCESS FAILED DOCUMENTS ...")
        failed_docs = repo.get_failed_documents()
        if failed_docs:
            logger.info("실패 문서: %d건", len(failed_docs))
        else:
            logger.info("실패 문서 없음")

        for i, f_doc in enumerate(failed_docs, start=1):
            manager.process_document(doc_id=f_doc.doc_id, gcs_pdf_path=f_doc.gcs_path, tag="RETRY", index=i, total=len(failed_docs))
        logger.info("[DONE] PROCESS FAILED DOCUMENTS")

        # ---------------- 3. Page-level 재시도 ----------------
        logger.info("[START] PROCESS FAILED PAGES ...")
        failed_pages = repo.get_failed_pages()
        if failed_pages:
            logger.info("실패 페이지: %d건", len(failed_pages))
        else:
            logger.info("실패 페이지 없음")

        for i, f_page in enumerate(failed_pages, start=1):
            try:
                doc_id = f_page.doc_id
                gcs_context_paths = repo.get_first_n_pages(doc_id, 5)

                text, t_err, summ, s_err = manager.process_page(f_page.gcs_path, gcs_context_paths)

                succ   = (t_err is None and s_err is None)
                status = PageStatus.SUCCESS if succ else PageStatus.FAILED

                repo.update_page_record(
                    page_id=f_page.page_id,
                    extracted_text=text or "",
                    summary=summ or "",
                    status=status,
                    error_message=t_err or s_err,
                )

                log_fn = logger.debug if succ else logger.warning
                log_fn("└── [%s] [%d/%d] page %s - %s - %s",
                        "RETRY", i, len(failed_pages),
                        "OK" if succ else "FAIL",
                        f_page.gcs_path,
                        "" if succ else (t_err or s_err))
            
            except Exception as e:
                logger.error("└── [%s] [%d/%d] page EXCEPT - %s - %s",
                                  "RETRY", i, len(failed_pages), f_page.gcs_path, e)
        logger.info("[DONE] PROCESS FAILED PAGES ...")

    finally:
        session.close()


if __name__ == "__main__":
    run_pipeline()