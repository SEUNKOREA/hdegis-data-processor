import os
from google.cloud import storage

from storage.gcs_client import GCSStorageClient
from processor.pdf_manager import PDFManager
from db.session import get_db_session
from db.repository import Repository
from config import GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET


def run_pipeline() -> None:
    """
    전체 파이프라인 실행:
    - GCS에서 PDF 목록 수집
    - DB에 등록되지 않은 PDF 문서를 추가
    - 처리되지 않은 문서만 PDFManager를 통해 처리
    """
    # 1. DB 세션 열기
    db_gen = get_db_session()
    session = next(db_gen)
    try:
        # 2. Repository, GCS 클라이언트, PDFManager 생성
        repo = Repository(session)
        gcs_client = storage.Client()
        storage_client = GCSStorageClient(
            source_bucket=GCS_SOURCE_BUCKET,
            target_bucket=GCS_PROCESSED_BUCKET,
            client=gcs_client
        )
        manager = PDFManager(storage_client, repo)

        # 3. GCS에서 PDF 경로 전부 가져오기
        pdf_paths = storage_client.list_pdfs(prefix="")  # 버킷 루트부터 검색

        cnt = 0
        for path in pdf_paths:
            # 4. DB에 등록 안 된 문서면 등록
            if not repo.document_exists(path):
                cnt += 1
                repo.create_document(path)
                print(f"[{cnt:02d}] {path}")

        # 5. 처리되지 않은 문서들만 가져오기
        pending_docs = repo.get_pending_documents()

        for i, doc in enumerate(pending_docs, start=1):
            try:
                print(f"({i:03d}/{len(pending_docs):03d}) 처리 시작: {doc.gcs_path}")
                manager.process(doc.gcs_path)
                print(f"({i:03d}/{len(pending_docs):03d}) 처리 완료: {doc.gcs_path}")
            except Exception as e:
                print(f"({i:03d}/{len(pending_docs):03d}) 문서 처리 실패: {doc.gcs_path} - 에러: {e}")

    finally:
        session.close()
