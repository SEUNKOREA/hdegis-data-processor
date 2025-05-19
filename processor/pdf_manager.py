import os
import sys
import tempfile
from typing import List, Optional, Tuple

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from storage.gcs_client import GCSStorageClient
from processor.splitter import split_pdf_to_images_and_upload
from processor.extractor import extract_text, extract_summary
from db.repository import Repository
from db.models import PDFDocument, PageStatus
from utils.logger import get_logger
from config import LOG_LEVEL



class PDFManager:
    def __init__(self, storage_client: GCSStorageClient, repository: Repository) -> None:
        self.storage = storage_client
        self.repo = repository
        self.logger = get_logger(self.__class__.__name__, LOG_LEVEL)


    # ── 문서 처리 ───────────────────────────
    def process_document(self, doc_id: str, gcs_pdf_path: str, *, 
                         tag: str = "NEW", index: int = 0, total: int = 0):
        doc: Optional[PDFDocument] = self.repo.session.get(PDFDocument, doc_id)
        if not doc:
            self.logger.error("[%s] [%d/%d] PDFDocument Table DB (hash) 없음 - %s", tag, index, total, doc_id)
            return

        # 1. split
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_pdf = os.path.join(tmpdir, "doc.pdf")
                self.storage.download_file(gcs_pdf_path, local_pdf, self.storage.source_bucket)
                gcs_image_paths = split_pdf_to_images_and_upload(local_pdf, gcs_pdf_path, tmpdir, self.storage)

                page_pairs: List[Tuple[str, str]] = []
                for pn, gcs_image_path in enumerate(gcs_image_paths, 1):
                    page = self.repo.create_page_record(
                        doc_id=doc.doc_id,
                        page_number=pn,
                        gcs_path=gcs_image_path,
                        gcs_pdf_path=doc.gcs_path
                    )
                    page_pairs.append((page.page_id, gcs_image_path))

            self.repo.mark_document_split(doc.doc_id, True)
            self.logger.info("[%s] [%d/%d] split OK - %s", tag, index, total, gcs_pdf_path)

        except Exception as e:
            self.logger.warning("[%s] [%d/%d] split FAIL - %s - %s", tag, index, total, gcs_pdf_path, e)
            return
        
        # 2. OCR + Summary
        gcs_context_paths = self.repo.get_first_n_pages(doc.doc_id, 5) # 첫 n페이지의 GCS path
        for pi, (page_id, gcs_image_path) in enumerate(page_pairs, 1):
            try:
                text, t_err, summ, s_err = self.process_page(gcs_image_path, gcs_context_paths)

                succ   = (t_err is None and s_err is None)
                status = PageStatus.SUCCESS if succ else PageStatus.FAILED

                self.repo.update_page_record(
                    page_id,
                    extracted_text=text or "",
                    summary=summ or "",
                    status=status,
                    error_message=t_err or s_err,
                )

                log_fn = self.logger.debug if succ else self.logger.warning
                log_fn("└── [%s] [%d/%d] page %s %d/%d - %s - %s",
                       tag, index, total,
                       "OK" if succ else "FAIL",
                       pi, len(page_pairs), gcs_image_path,
                       "" if succ else (t_err or s_err))

            except Exception as e:
                self.logger.error("└── [%s] [%d/%d] page EXCEPT %d/%d - %s - %s",
                                  tag, index, total, pi, len(page_pairs), gcs_image_path, e) 


    # ── 페이지 처리 ────────────────────────
    def process_page(self, gcs_image_path: str, gcs_context_paths: List[str]):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 로컬에 임시 다운로드
            local_image_path = os.path.join(tmpdir, os.path.basename(gcs_image_path))
            self.storage.download_file(gcs_image_path, local_image_path, self.storage.target_bucket)

            local_context_paths = []
            for ctx_gcs_path in gcs_context_paths:
                local_ctx_path = os.path.join(tmpdir, os.path.basename(ctx_gcs_path))
                self.storage.download_file(ctx_gcs_path, local_ctx_path, self.storage.target_bucket)
                local_context_paths.append(local_ctx_path)

            # 2. 추출
            text, t_err = extract_text(local_image_path)
            summ, s_err = extract_summary(local_image_path, local_context_paths)
        
        return text or "", t_err, summ or "", s_err