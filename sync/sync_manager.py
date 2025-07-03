# sync/sync_manager.py
import os
import sys
from typing import Dict, List

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from sync.change_detector import ChangeDetector
from sync.file_sync import FileSyncManager
from storage.gcs_client import GCSStorageClient
from db.repository import Repository
from db.models import DocumentStatus
from processor.pdf_manager import PDFManager
from utils.logger import get_logger
from utils.utils import compute_doc_hash
from config import LOG_LEVEL

logger = get_logger(__name__, LOG_LEVEL)

class SyncManager:
    def __init__(self, storage_client: GCSStorageClient, repo: Repository, manager: PDFManager = None):
        self.storage = storage_client
        self.repo = repo
        self.manager = manager  # 인덱싱 시에만 필요
        self.detector = ChangeDetector(storage_client, repo)
        self.file_sync = FileSyncManager()
    
    def sync_with_gcs(self) -> Dict:
        """전체 동기화 프로세스"""
        logger.info("=== GCS 동기화 시작 ===")
        
        try:
            # 1. 로컬 → GCS 파일 동기화
            logger.info("Step 1: 로컬 → GCS 파일 동기화")
            if not self.file_sync.sync_to_gcs():
                raise Exception("파일 동기화 실패")
            
            # 2. 변경사항 감지
            logger.info("Step 2: 변경사항 감지")
            changes = self.detector.detect_changes()
            
            logger.info(f"변경사항 감지 결과:")
            logger.info(f"  새 파일: {len(changes['new'])}개")
            logger.info(f"  삭제된 파일: {len(changes['deleted'])}개") 
            logger.info(f"  이동된 파일: {len(changes['moved'])}개")
            logger.info(f"  변경 없는 파일: {len(changes['unchanged'])}개")
            
            # 3. Document 상태 변경
            logger.info("Step 3: Document 상태 변경")
            self._handle_deleted_files(changes['deleted'])
            self._handle_moved_files(changes['moved'])
            self._handle_new_files(changes['new'])
            
            # 4. Document ↔ Page 상태 동기화 (핵심!)
            logger.info("Step 4: Document ↔ Page 상태 동기화")
            self.repo.sync_page_status_with_documents()
            
            # 5. 처리 현황 로깅
            stats = self.repo.get_processing_stats()
            logger.info(f"현재 처리 현황:")
            logger.info(f"  전체 ACTIVE 페이지: {stats['total_active_pages']}개")
            logger.info(f"  처리 완료 페이지: {stats['completed_pages']}개")
            logger.info(f"  처리 대기 페이지: {stats['remaining_pages']}개")
            logger.info(f"  완료율: {stats['completion_rate']:.1f}%")
            
            logger.info("=== GCS 동기화 완료 ===")
            return changes
            
        except Exception as e:
            logger.error(f"동기화 중 오류 발생: {e}")
            raise
    
    def _handle_deleted_files(self, deleted_files):
        """삭제된 파일들 처리 - Document 상태만 변경"""
        if not deleted_files:
            return
            
        logger.info(f"삭제된 파일 {len(deleted_files)}개 처리 중...")
        
        for file_info in deleted_files:
            try:
                # Document 상태만 INACTIVE로 변경 (Page는 나중에 동기화에서 처리)
                self.repo.update_document_status(file_info.doc_id, DocumentStatus.INACTIVE)
                logger.info(f"삭제 처리 완료: {file_info.path}")
                
            except Exception as e:
                logger.error(f"삭제 처리 실패: {file_info.path} - {e}")
    
    def _handle_moved_files(self, moved_files):
        """이동된 파일들 처리"""
        if not moved_files:
            return
            
        logger.info(f"이동된 파일 {len(moved_files)}개 처리 중...")
        
        for old_path, new_path, content_hash in moved_files:
            try:
                # 1. 기존 문서 INACTIVE 처리
                old_doc_id = self.repo.get_doc_id_by_content_hash(content_hash)
                if old_doc_id:
                    self.repo.update_document_status(old_doc_id, DocumentStatus.INACTIVE)
                    logger.info(f"기존 문서 INACTIVE 처리: {old_path}")
                
                # 2. 새 문서로 등록 (ACTIVE 상태로 자동 등록됨)
                new_doc_id = compute_doc_hash(self.storage, new_path)
                if not self.repo.exists_document(new_doc_id):
                    self.repo.create_document(new_doc_id, new_path)
                    self.repo.update_content_hash(new_doc_id, content_hash)
                    logger.info(f"새 문서 등록: {new_path}")
                
                logger.info(f"이동 처리 완료: {old_path} -> {new_path}")
                
            except Exception as e:
                logger.error(f"이동 처리 실패: {old_path} -> {new_path} - {e}")
    
    def _handle_new_files(self, new_files):
        """새 파일들 DB 등록"""
        if not new_files:
            return
            
        logger.info(f"새 파일 {len(new_files)}개 DB 등록 중...")
        
        for file_info in new_files:
            try:
                # DB에 문서 등록 (ACTIVE 상태로 자동 등록됨)
                if not self.repo.exists_document(file_info.doc_id):
                    self.repo.create_document(file_info.doc_id, file_info.path)
                    self.repo.update_content_hash(file_info.doc_id, file_info.content_hash)
                    logger.info(f"새 문서 등록: {file_info.path}")
                
            except Exception as e:
                logger.error(f"새 문서 등록 실패: {file_info.path} - {e}")

if __name__ == "__main__":
    # 테스트용
    from google.cloud import storage
    from db.session import get_db_session
    from config import *
    
    gcs_client = storage.Client()
    storage_client = GCSStorageClient(GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET, gcs_client)
    
    db_gen = get_db_session()
    session = next(db_gen)
    repo = Repository(session)
    
    # manager는 일단 None으로 (동기화 단계에서는 불필요)
    sync_manager = SyncManager(storage_client, repo, None)
    changes = sync_manager.sync_with_gcs()
    
    print(f"\n=== 최종 결과 ===")
    print(f"새 파일: {len(changes['new'])}개")
    print(f"삭제된 파일: {len(changes['deleted'])}개")
    print(f"이동된 파일: {len(changes['moved'])}개")
    
    session.close()