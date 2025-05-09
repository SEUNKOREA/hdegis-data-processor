import tempfile
from typing import List, Optional
from storage.gcs_client import GCSStorageClient
from processor.splitter import split_pdf_to_images
from processor.extractor import extract_text, extract_description
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

    def process(self, gcs_pdf_path: str) -> None:
        """
        주어진 GCS 경로의 PDF 파일을 처리:
        1. 다운로드
        2. 이미지 분리
        3. OCR + Description
        4. GCS 이미지 업로드
        5. DB에 결과 저장
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            local_pdf_path = f"{tmpdir}/source.pdf"

            # 1. GCS에서 PDF 다운로드
            self.storage.download_pdf(gcs_pdf_path, local_pdf_path)

            # 2. 이미지 분리 (pdf2image 사용)
            image_paths: List[str] = split_pdf_to_images(local_pdf_path, tmpdir)

            # 3. PDFDocument 레코드 조회
            document: Optional[PDFDocument] = (
                self.repo.session.query(PDFDocument)
                .filter_by(gcs_path=gcs_pdf_path)
                .first()
            )
            if not document:
                raise ValueError(f"문서를 DB에서 찾을 수 없습니다: {gcs_pdf_path}")
            document_id = document.id

            # 4. 페이지별 처리
            for idx, local_img_path in enumerate(image_paths, start=1):
                try:
                    # 4-1. 이미지 GCS에 업로드
                    out_gcs_path = self.storage.make_output_path(gcs_pdf_path, idx)
                    uploaded_gcs_path = self.storage.upload_page_image(local_img_path, out_gcs_path)

                    # 4-2. 페이지 DB 레코드 생성 (초기 상태: PENDING)
                    page = self.repo.create_page_record(
                        document_id=document_id,
                        page_number=idx,
                        gcs_path=uploaded_gcs_path
                    )

                    # 4-3. OCR + 설명 생성 (Gemini API 사용)
                    extracted_text, ocr_err = extract_text(local_img_path)
                    description, desc_err = extract_description(local_img_path)

                    # 4-4. 상태 결정
                    is_success = ocr_err is None and desc_err is None
                    status = PageStatus.SUCCESS if is_success else PageStatus.FAILED
                    error_msg = "\n".join(filter(None, [ocr_err, desc_err])) or None

                    # 4-5. 페이지 레코드 업데이트
                    self.repo.update_page_record(
                        page_id=page.id,
                        extracted_text=extracted_text,
                        description=description,
                        status=status,
                        error_message=error_msg
                    )

                except Exception as e:
                    print(f"페이지 {idx} 처리 중 오류: {e}")

            # 5. 문서 처리 완료로 마크
            self.repo.mark_document_processed(gcs_pdf_path)
