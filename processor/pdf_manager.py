import os
import sys
import json
import tempfile
from typing import List, Optional, Tuple, Dict

from pdf2image import convert_from_path
from google import genai
from google.genai import types

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from storage.gcs_client import GCSStorageClient
from processor.extractor import extract_text, extract_summary
from processor.embedder import get_text_embedding
from processor.elastic import ESConnector
from db.repository import Repository
from db.models import PDFPage, PageStatus
from utils.utils import split_file_path
from utils.logger import get_logger
from config import LOG_LEVEL, INDEX_NAME



class PDFManager:
    def __init__(self, 
                 storage_client: GCSStorageClient, 
                 repository: Repository, 
                 genai_client: genai.Client,
                 els_client: ESConnector) -> None:
        self.storage = storage_client
        self.repo = repository
        self.genai = genai_client
        self.els =  els_client
        self.logger = get_logger(self.__class__.__name__, LOG_LEVEL)


    def invoke_split(self, gcs_pdf_path: str) -> Dict[str, str]:
        """
        GCS에 있는 PDF를 이미지로 분할한 후 GCS에 업로드
        {page_number: gcs_image_path} 딕셔너리 형태로 반환
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # PDF 임시 다운로드
            local_pdf_path = os.path.join(tmpdir, "doc.pdf")
            self.storage.download_file(gcs_pdf_path, local_pdf_path, self.storage.source_bucket)

            # PDF → 이미지 변환
            images = convert_from_path(local_pdf_path, dpi=300)

            # 이미지 GCS 업로드 경로 설정
            parent_dir, pdf_filename = split_file_path(gcs_pdf_path)
            pdf_basename = os.path.splitext(pdf_filename)[0]
            gcs_image_dir = f"{parent_dir}/{pdf_basename}" if parent_dir else pdf_basename
            
            page_infos: Dict[int, str] = {}  # {page_number: gcs_image_path}

            # 이미지 저장 및 GCS 업로드
            for i, image in enumerate(images, start=1):
                local_image_path = os.path.join(tmpdir, f"page-{i:05d}.png")
                image.save(local_image_path, "PNG")

                gcs_image_path = f"{gcs_image_dir}/{pdf_basename}-page-{i:05}.png"
                uploaded_path = self.storage.upload_file(local_image_path, gcs_image_path, self.storage.target_bucket)

                page_infos[i] = uploaded_path
        
            return page_infos


    def invoke_extraction(self, gcs_image_path: str) -> Tuple[str, str | None, PageStatus]:
        """
        Gemini를 이용해서 텍스트 추출 수행
        반환: (추출된 텍스트, 오류메시지, 상태)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 이미지 임시 다운로드
            local_image_path = os.path.join(tmpdir, os.path.basename(gcs_image_path))
            self.storage.download_file(gcs_image_path, local_image_path, self.storage.target_bucket)

            # 텍스트 추출
            text, error = extract_text(local_image_path, self.genai)
            status = PageStatus.SUCCESS if error is None else PageStatus.FAILED

            return text or "", error, status


    def invoke_summary(self, gcs_image_path: str) -> Tuple[str, str | None, PageStatus]:
        """
        Gemini를 이용해서 해당 이미지의 문서의 첫 5페이지를 참고해서 해당 페이지의 요약 수행
        반환: (요약된 텍스트, 오류메시지, 상태)
        """
        # doc_id 조회
        page = self.repo.session.query(PDFPage).filter_by(gcs_path=gcs_image_path).first()
        if not page:
            return "", f"DB에 해당 페이지 정보 없음: {gcs_image_path}", PageStatus.FAILED

        # 첫 5페이지 GCS Path 조회
        doc_id = page.doc_id
        gcs_context_paths = self.repo.get_first_n_pages(doc_id, 5)

        with tempfile.TemporaryDirectory() as tmpdir:
            # 현재 페이지 다운로드
            local_image_path = os.path.join(tmpdir, os.path.basename(gcs_image_path))
            self.storage.download_file(gcs_image_path, local_image_path, self.storage.target_bucket)

            # 컨텍스트 페이지 다운로드
            local_context_paths = []
            for gcs_path in gcs_context_paths:
                local_path = os.path.join(tmpdir, os.path.basename(gcs_path))
                self.storage.download_file(gcs_path, local_path, self.storage.target_bucket)
                local_context_paths.append(local_path)

            # 요약 추출
            summary, error = extract_summary(local_image_path, local_context_paths, self.genai)
            status = PageStatus.SUCCESS if error is None else PageStatus.FAILED
            return summary or "", error, status


    def invoke_embedding(self, gcs_image_path: str) -> Tuple[List[float] | None, str | None, PageStatus]:
        """
        텍스트 임베딩 벡터 생성
        반환: (embedding_vector, error_message, 상태)
        """
        # 페이지 정보 가져오기
        page = self.repo.session.query(PDFPage).filter_by(gcs_path=gcs_image_path).first()
        if not page:
            return None, f"DB에 해당 페이지 정보 없음: {gcs_image_path}", PageStatus.FAILED

        # 추출한 텍스트 확인
        combined_text = (page.summary or "") + "\n\n" + (page.extracted_text or "")
        if not combined_text.strip():
            return None, "임베딩 대상 텍스트가 비어있음", PageStatus.FAILED

        # 임베딩 수행
        try:
            embedding = get_text_embedding(combined_text, self.genai)
            return embedding, None, PageStatus.SUCCESS
        except Exception as e:
            return None, f"임베딩 오류: {e}", PageStatus.FAILED
    

    def invoke_indexing(self, page: PDFPage) -> Tuple[str, str, PageStatus, Optional[str]]:
        """
        ELS에 페이지 인덱싱 수행
        """
        try:
            data = {
                "page_id": page.page_id,
                "doc_id": page.doc_id,
                "page_number": page.page_number,
                "gcs_path": page.gcs_path,
                "gcs_pdf_path": page.gcs_pdf_path,
                "extracted_text": page.extracted_text,
                "summary": page.summary,
                "embedding": json.loads(page.embedding),
            }

            self.els.conn.index(index=INDEX_NAME, id=page.page_id, document=data)
            return page.page_id, page.gcs_path, PageStatus.SUCCESS, None

        except Exception as e:
            return page.page_id, page.gcs_path, PageStatus.FAILED, f"Indexing Error: {e}"