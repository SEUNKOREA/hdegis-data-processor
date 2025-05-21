import os
import sys
import json
from typing import List, Tuple

from google.cloud import storage
from google import genai

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from db.initialize import initialize_tables
from db.models import PageStatus
from db.session import get_db_session
from db.repository import Repository
from storage.gcs_client import GCSStorageClient
from processor.pdf_manager import PDFManager
from processor.elastic import ESConnector
from utils.logger import get_logger
from utils.utils import compute_doc_hash
from config import (
    GCS_SOURCE_BUCKET,
    GCS_PROCESSED_BUCKET,
    PROJECT_ID, 
    GENAI_LOCATION,
    ES_HOST,
    ES_USER,
    ES_PWD,
    INDEX_NAME,
    LOG_LEVEL
)

logger = get_logger(__name__, LOG_LEVEL)

def run_pipeline() -> None:

    logger.info("[Step 0] Initializing database tables")
    initialize_tables()


    db_gen = get_db_session()
    session = next(db_gen)

    try:
        # ── 초기화
        gcs_client = storage.Client()
        storage_client = GCSStorageClient(GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET, gcs_client)
        repo = Repository(session)
        genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location=GENAI_LOCATION)
        els = ESConnector(hosts=ES_HOST, credentials=(ES_USER, ES_PWD))

        manager = PDFManager(storage_client, repo, genai_client, els)


        # ─────────────────────────────────────────────────────────
        # 1. 신규문서 Detection
        # ─────────────────────────────────────────────────────────
        logger.info("[Step 1] Scanning GCS for new PDF documents")
        pdf_paths = storage_client.list_pdfs()
        logger.info(" └── Found %d PDF files in GCS", len(pdf_paths))
        
        known_doc_ids = repo.list_all_document_hashes()
        new_docs: List[Tuple[str, str]] = []

        for path in pdf_paths:
            try:
                doc_hash = compute_doc_hash(storage_client, path)
                if doc_hash not in known_doc_ids:
                    new_docs.append((doc_hash, path))
            except Exception as e:
                logger.warning(" └── Hash computation failed for %s (%s)", path, e)

        logger.info(" └── Detected %d new documents", len(new_docs))


        # ─────────────────────────────────────────────────────────
        # 2. 신규문서 Split해서 DB 등록
        # ─────────────────────────────────────────────────────────
        logger.info("[Step 2] Splitting new documents and saving page metadata")
        for i, (doc_id, gcs_pdf_path) in enumerate(new_docs):
            try:
                # PDFDocument Table 등록
                if not repo.exists_document(doc_id):
                    repo.create_document(doc_id, gcs_pdf_path)

                # PDFPage Table 등록
                gcs_page_infos = manager.invoke_split(gcs_pdf_path) # {page_number: gcs_image_path}                
                for page_number, gcs_image_path in gcs_page_infos.items():
                    repo.create_page_record(
                        doc_id=doc_id,
                        page_number=page_number,
                        gcs_path=gcs_image_path,
                        gcs_pdf_path=gcs_pdf_path,
                    )  

                logger.info(" └── [%d/%d] Split and saved %d pages: %s", i + 1, len(new_docs), len(gcs_page_infos), gcs_pdf_path)

            except Exception as e:
                logger.warning(" └── [%d/%d] Failed to split or save: %s (%s)", i + 1, len(new_docs), gcs_pdf_path, e)


        # ─────────────────────────────────────────────────────────
        # 3. 텍스트 추출
        # ─────────────────────────────────────────────────────────
        logger.info("[Step 3] Extracting text from page images")
        extraction_pages = repo.get_pages_for_extraction()
        pending = [p for p in extraction_pages if p.extracted == PageStatus.PENDING]
        retry   = [p for p in extraction_pages if p.extracted == PageStatus.FAILED]
        logger.info("Pages queued for text extraction: %d (new: %d, retry: %d)", len(extraction_pages), len(pending), len(retry))

        for i, page in enumerate(extraction_pages, 1):
            try:
                tag = "new" if page.extracted == PageStatus.PENDING else "retry"
                text, error, status = manager.invoke_extraction(page.gcs_path)

                repo.update_page_record(
                    page_id=page.page_id,
                    extracted_text=text,
                    extracted=status,
                    error_message=error
                )   

                if status == PageStatus.SUCCESS:
                    logger.debug(" └── [%d/%d] Text extraction succeeded (%s): %s", i, len(extraction_pages), tag, page.gcs_path)
                else:
                    logger.warning(" └── [%d/%d] Text extraction failed (%s): %s - %s", i, len(extraction_pages), tag, page.gcs_path, error)

            except Exception as e:
                logger.error(" └── [%d/%d] Text extraction exception (%s): %s - %s", i, len(extraction_pages), tag, page.gcs_path, e)


        # ─────────────────────────────────────────────────────────
        # 4. 요약 추출
        # ─────────────────────────────────────────────────────────
        logger.info("[Step 4] Generating summaries")
        summary_pages = repo.get_pages_for_summary()
        pending = [p for p in summary_pages if p.summarized == PageStatus.PENDING]
        retry   = [p for p in summary_pages if p.summarized == PageStatus.FAILED]
        logger.info("Pages queued for summary generation: %d (new: %d, retry: %d)", len(summary_pages), len(pending), len(retry))

        for i, page in enumerate(summary_pages, 1):
            try:
                tag = "new" if page.summarized == PageStatus.PENDING else "retry"
                summary, error, status = manager.invoke_summary(page.gcs_path)

                repo.update_page_record(
                    page_id=page.page_id,
                    summary=summary,
                    summarized=status,
                    error_message=error
                )

                if status == PageStatus.SUCCESS:
                    logger.debug(" └── [%d/%d] Summary generation succeeded (%s): %s", i, len(summary_pages), tag, page.gcs_path)
                else:
                    logger.warning(" └── [%d/%d] Summary generation failed (%s): %s - %s", i, len(summary_pages), tag, page.gcs_path, error)

            except Exception as e:
                logger.error(" └── [%d/%d] Summary generation exception (%s): %s - %s", i, len(summary_pages), tag, page.gcs_path, e)



        # ─────────────────────────────────────────────────────────
        # 5. 임베딩 벡터 생성
        # ─────────────────────────────────────────────────────────
        logger.info("[Step 5] Generating embeddings")
        embedding_pages = repo.get_pages_for_embedding()
        pending = [p for p in embedding_pages if p.embedded == PageStatus.PENDING]
        retry   = [p for p in embedding_pages if p.embedded == PageStatus.FAILED]
        logger.info("Pages queued for embedding: %d (new: %d, retry: %d)", len(embedding_pages), len(pending), len(retry))

        for i, page in enumerate(embedding_pages, 1):
            try:
                tag = "new" if page.embedded == PageStatus.PENDING else "retry"
                embedding, error, status = manager.invoke_embedding(page.gcs_path)

                repo.update_page_record(
                    page_id=page.page_id,
                    embedding=json.dumps(embedding), # 리스트를 문자열로 변환
                    embedded=status,
                    error_message=error
                )

                if status == PageStatus.SUCCESS:
                    logger.debug(" └── [%d/%d] Embedding succeeded (%s): %s", i, len(embedding_pages), tag, page.gcs_path)
                else:
                    logger.warning(" └── [%d/%d] Embedding failed (%s): %s - %s", i, len(embedding_pages), tag, page.gcs_path, error)

            except Exception as e:
                logger.error(" └── [%d/%d] Embedding exception (%s): %s - %s", i, len(embedding_pages), tag, page.gcs_path, e)



        # ─────────────────────────────────────────────────────────
        # 6. 인덱싱
        # ─────────────────────────────────────────────────────────
        logger.info("[Step 6] Indexing")
        indexing_pages = repo.get_pages_for_indexing()
        pending = [p for p in embedding_pages if p.indexed == PageStatus.PENDING]
        retry   = [p for p in embedding_pages if p.indexed == PageStatus.FAILED]
        logger.info("Pages queued for indexing: %d (new: %d, retry: %d)", len(embedding_pages), len(pending), len(retry))

        for i, page in enumerate(indexing_pages, 1):
            try:
                tag = "new" if page.indexed == PageStatus.PENDING else "retry"
                page_id, gcs_page_path, status, error = manager.invoke_indexing(page)

                repo.update_page_record(
                    page_id=page_id,
                    indexed=status,
                    error_message=error
                )

                if status == PageStatus.SUCCESS:
                    logger.debug(" └── [%d/%d] Indexing succeeded (%s): %s", i, len(indexing_pages), tag, page.gcs_path)
                else:
                    logger.warning(" └── [%d/%d] Indexing failed (%s): %s - %s", i, len(indexing_pages), tag, page.gcs_path, error)

            except Exception as e:
                logger.error(" └── [%d/%d] Indexing exception (%s): %s - %s", i, len(indexing_pages), tag, page.gcs_path, e)


    finally:
        session.close()
        logger.info("\nPipeline execution finished")