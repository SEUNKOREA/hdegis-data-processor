import os
import sys
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from storage.gcs_client import GCSStorageClient
from db.repository import Repository
from db.models import PDFDocument, DocumentStatus
from utils.utils import compute_doc_hash, compute_content_hash
from utils.logger import get_logger
from config import LOG_LEVEL

logger = get_logger(__name__, LOG_LEVEL)

@dataclass
class FileInfo:
    path: str
    doc_id: str
    content_hash: str

class ChangeDetector:
    def __init__(self, storage_client: GCSStorageClient, repo: Repository):
        self.storage = storage_client
        self.repo = repo
    
    def scan_current_files(self) -> Dict[str, FileInfo]:
        logger.info("GCS 파일 스캔 중...")
        current_files = {}
        pdf_paths = self.storage.list_pdfs()
        
        for i, path in enumerate(pdf_paths, 1):
            try:
                doc_id = compute_doc_hash(self.storage, path)
                content_hash = compute_content_hash(self.storage, path)  # 추가
                current_files[path] = FileInfo(
                    path=path, 
                    doc_id=doc_id, 
                    content_hash=content_hash  # 추가
                )
                if i % 10 == 0:
                    logger.info(f"  스캔 진행: {i}/{len(pdf_paths)}")
            except Exception as e:
                logger.warning(f"파일 해시 계산 실패: {path} - {e}")
        
        logger.info(f"GCS 스캔 완료: {len(current_files)}개 파일")
        return current_files

    def get_db_files(self) -> Dict[str, FileInfo]:
        logger.info("DB 상태 조회 중...")
        db_files = {}
        
        docs = self.repo.session.query(PDFDocument).filter(
            PDFDocument.status == DocumentStatus.ACTIVE  # 수정
        ).all()
        
        for doc in docs:
            db_files[doc.gcs_path] = FileInfo(
                path=doc.gcs_path, 
                doc_id=doc.doc_id,
                content_hash=doc.content_hash or ""  # 추가 (None 처리)
            )
        
        logger.info(f"DB 조회 완료: {len(db_files)}개 파일")
        return db_files

    def detect_changes(self) -> Dict[str, List]:
        current_files = self.scan_current_files()
        db_files = self.get_db_files()
        
        current_paths = set(current_files.keys())
        db_paths = set(db_files.keys())
        
        # content_hash 기준 비교 (이동 감지용)
        current_content_hashes = {f.content_hash: f.path for f in current_files.values()}
        db_content_hashes = {f.content_hash: f.path for f in db_files.values() if f.content_hash}
        
        changes = {
            'new': [],
            'deleted': [],
            'moved': [],
            'unchanged': []
        }
        
        # 새 파일 감지
        new_paths = current_paths - db_paths
        for path in new_paths:
            file_info = current_files[path]
            if file_info.content_hash not in db_content_hashes:
                changes['new'].append(file_info)
            else:
                # 같은 content_hash가 이미 DB에 있다면 이동된 것
                old_path = db_content_hashes[file_info.content_hash]
                changes['moved'].append((old_path, path, file_info.content_hash))
        
        # 삭제된 파일 감지
        deleted_paths = db_paths - current_paths
        for path in deleted_paths:
            file_info = db_files[path]
            if file_info.content_hash and file_info.content_hash not in current_content_hashes:
                changes['deleted'].append(file_info)
        
        # 변경 없는 파일들
        common_paths = current_paths & db_paths
        for path in common_paths:
            changes['unchanged'].append(current_files[path])
        
        return changes

if __name__ == "__main__":
    # 테스트용
    from google.cloud import storage
    from db.session import get_db_session
    from config import GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET
    
    gcs_client = storage.Client()
    storage_client = GCSStorageClient(GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET, gcs_client)
    
    db_gen = get_db_session()
    session = next(db_gen)
    repo = Repository(session)
    
    detector = ChangeDetector(storage_client, repo)
    changes = detector.detect_changes()
    
    print("\n=== 변경사항 감지 결과 ===")
    print(f"새 파일: {len(changes['new'])}개")
    print(f"삭제된 파일: {len(changes['deleted'])}개")
    print(f"이동된 파일: {len(changes['moved'])}개")
    print(f"변경 없는 파일: {len(changes['unchanged'])}개")
    
    if changes['new']:
        print("\n새 파일들:")
        for f in changes['new'][:5]:  # 처음 5개만
            print(f"  {f.path}")
    
    if changes['deleted']:
        print("\n삭제된 파일들:")
        for f in changes['deleted']:  # 처음 5개만
            print(f"  {f.path}")
    
    if changes['moved']:
        print("\n이동된 파일들:")
        for f in changes['moved'][:5]:  # 처음 5개만
            print(f"  {f}")
    
    
    session.close()    