import os
import sys
# 프로젝트 폴더를 루트로 가정
PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)
from google.cloud import storage

from storage.gcs_client import GCSStorageClient
from processor.pdf_manager import PDFManager
from db.init_db import init_tables
from db.session import get_db_session
from db.repository import Repository
from db.models import PDFDocument, PageStatus
from config import GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET


def run_pipeline() -> None:
    """
    전체 파이프라인 실행:
    - GCS에서 PDF 목록 수집
    - DB에 등록되지 않은 PDF 문서를 추가
    - 처리되지 않은 문서만 PDFManager를 통해 처리
    """
    init_tables()

    # 1. DB 세션 열기
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


        # 1. GCS에서 PDF 목록 수집
        pdf_paths = storage_client.list_pdfs(prefix="")  # 버킷 루트부터 검색
        print(f"\n전체 GCS PDF: {len(pdf_paths)}개")


        # 2. 신규문서(DB에 없는 문서) 필터링 및 등록
        new_pdf_paths = [p for p in pdf_paths if not repo.document_exists(p)]
        if new_pdf_paths:
            print(f"신규 문서 발견: {len(new_pdf_paths)}건")
            for idx, path in enumerate(new_pdf_paths, 1):
                repo.create_document(path, storage_client)    
                print(f"---  [{idx}/{len(new_pdf_paths)}] 신규문서 등록 완료: {path}")
        else:
            print("신규 문서 없음")
        

        # 3. 처리되지 않은(processed=0) 문서 처리
        pending_docs = repo.get_pending_documents()
        print(f"\n처리되지 않은 문서: {len(pending_docs)}건")
        total_docs = len(pending_docs)
        for doc_idx, doc in enumerate(pending_docs, start=1):
            try:
                manager.process(doc.gcs_path, doc_index=doc_idx, total_docs=total_docs)
                print(f"[{doc_idx}/{total_docs}] 문서 처리 성공: {doc.gcs_path}")
            except Exception as e:
                print(f"[{doc_idx}/{total_docs}] 문서 처리 실패: {doc.gcs_path} - 에러: {e}")


        # 4. 실패한 페이지 처리
        failed_pages = repo.get_failed_pages()
        print(f"\n실패한 페이지: {len(failed_pages)}건")
        
        for idx, page in enumerate(failed_pages, 1):
            try:
                # 1. context 이미지 경로
                context_paths = repo.get_first_n_pages(document_id=page.doc_id, n=5)
                
                # 2. OCR 및 요약 추출
                text, text_err, summary, summary_err = manager.process_page(gcs_image_path=page.gcs_path, context_paths=context_paths)
                
                # 3. 상태 판단 및 DB 업데이트
                success = text_err is None and summary_err is None
                status = PageStatus.SUCCESS if success else PageStatus.FAILED
                error_msg = text_err or summary_err

                repo.update_page_record(
                    page_id=page.page_id,
                    extracted_text=text,
                    summary=summary,
                    status=status,
                    error_message=error_msg
                )
    
                # 4. 출력
                if success:
                    # print(f"[{idx}/{len(failed_pages)}] 재처리 성공: {page.document.gcs_path}")
                    print(f"[{idx}/{len(failed_pages)}] 재처리 성공: {page.gcs_path}")
                else:
                    # print(f"[{idx}/{len(failed_pages)}] 재처리 실패: {page.document.gcs_path} - 오류: {error_msg}")
                    print(f"[{idx}/{len(failed_pages)}] 재처리 실패: {page.gcs_path} - 오류: {error_msg}")

            except Exception as e:
                print(f"[{idx}/{len(failed_pages)}] 재처리 실패: {page.document.gcs_path} - 예외발생: {e}")

    finally:
        session.close()

if __name__ == "__main__":
    run_pipeline()