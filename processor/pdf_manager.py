import os
import sys
# 프로젝트 폴더를 루트로 가정
PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

import tempfile
from typing import List, Optional

from storage.gcs_client import GCSStorageClient
from processor.splitter import split_pdf_to_images_and_upload
from processor.extractor import extract_text, extract_summary
from db.repository import Repository
from db.models import PDFDocument, PageStatus


class PDFManager:
    def __init__(self, storage_client: GCSStorageClient, repository: Repository) -> None:
        """
        :param storage_client: GCS 업로드/다운로드를 위한 클라이언트
        :param repository: DB에 접근하는 레포지토리 클래스
        """
        self.storage = storage_client
        self.repo = repository

    def process(self, gcs_pdf_path: str, doc_index: int = 0, total_docs: int = 0) -> None:
        # 1) DB에서 문서 레코드 조회
        doc: Optional[PDFDocument] = (
            self.repo.session.query(PDFDocument)
            .filter_by(gcs_path=gcs_pdf_path)
            .first()
        )
        if not doc:
            print(f"[{doc_index}/{total_docs}] 문서 정보를 DB에서 찾을 수 없습니다: {gcs_pdf_path}")
            return


        # 2) PDF 다운로드 → 이미지 → GCS 업로드
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_pdf = os.path.join(tmpdir, "document.pdf")
                self.storage.download_file(gcs_pdf_path, local_pdf, self.storage.source_bucket)

                gcs_image_paths = split_pdf_to_images_and_upload(
                    local_pdf_path=local_pdf,
                    gcs_pdf_path=gcs_pdf_path,
                    output_folder=tmpdir,
                    storage_client=self.storage
                )

                page_ids = []
                for idx, gcs_image_path in enumerate(gcs_image_paths, start=1):
                    page_rec = self.repo.create_page_record(
                        doc_id=doc.doc_id,
                        page_number=idx,
                        gcs_path=gcs_image_path,
                        gcs_pdf_path=gcs_pdf_path,
                    )
                    page_ids.append((page_rec.page_id, gcs_image_path))

            # 업로드 성공 → 문서 상태 업데이트
            self.repo.mark_document_split(doc.doc_id, success=True)
            print(f"[{doc_index}/{total_docs}] split + GCS 업로드 + Page DB 등록 성공: {gcs_pdf_path}")

        except Exception as e:
            self.repo.mark_document_split(doc.doc_id, success=False)
            print(f"[{doc_index}/{total_docs}] split, GCS 업로드 또는 Page DB 등록 실패: {e}")
            return

        # 3) 개별 페이지 처리에서 활용할 문서의 첫 5페이지 GCS 경로
        context_paths = self.repo.get_first_n_pages(document_id=doc.doc_id, n=5)

        # 4) 개별 페이지 처리
        for idx, (page_id, gcs_image_path) in enumerate(page_ids, start=1):
            text, text_err, summary, summary_err = self.process_page(gcs_image_path, context_paths)

            success = text_err is None and summary_err is None
            status = PageStatus.SUCCESS if success else PageStatus.FAILED
            err_msg = text_err or summary_err

            self.repo.update_page_record(
                page_id=page_id,
                extracted_text=text,
                summary=summary,
                status=status,
                error_message=err_msg
            )

            if success:
                print(f"    [page {idx}/{len(page_ids)}] (문서 {doc_index}/{total_docs}) 처리성공")
            else:
                print(f"    [page {idx}/{len(page_ids)}] (문서 {doc_index}/{total_docs}) 처리실패: {err_msg}")


    def process_page(self, gcs_image_path: str, context_paths: List[str]) -> tuple[str, str | None, str, str | None]:
        """
        GCS에 저장된 이미지 경로를 이용해 OCR 및 설명 추출 후 DB 업데이트
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 현재 페이지 다운로드
            local_image_path = os.path.join(tmpdir, os.path.basename(gcs_image_path))
            self.storage.download_file(gcs_image_path, local_image_path, self.storage.target_bucket)

            # 2. Context 이미지들 다운로드
            context_local_paths = []
            for gcs_path in context_paths:
                local_path = os.path.join(tmpdir, os.path.basename(gcs_path))
                self.storage.download_file(gcs_path, local_path, self.storage.target_bucket)
                context_local_paths.append(local_path)

            # 3. OCR & 요약 추출
            text, text_err = extract_text(local_image_path)
            summ, summ_err = extract_summary(local_image_path, context_local_paths)

            return text or "", text_err, summ or "", summ_err

if __name__ == "__main__":
    pass