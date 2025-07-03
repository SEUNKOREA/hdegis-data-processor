# sync/file_sync.py
import os
import sys
import subprocess

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from utils.logger import get_logger
from config import LOG_LEVEL, GCS_SOURCE_BUCKET

logger = get_logger(__name__, LOG_LEVEL)

class FileSyncManager:
    def __init__(self, local_path: str = "data/", gcs_bucket: str = None):
        self.local_path = local_path.rstrip('/') + '/'
        self.gcs_bucket = gcs_bucket or GCS_SOURCE_BUCKET
    
    def sync_to_gcs(self) -> bool:
        """로컬 데이터를 GCS에 동기화"""
        try:
            logger.info(f"파일 동기화 시작: {self.local_path} -> gs://{self.gcs_bucket}/")
            
            # 1. 동기화 미리보기 (dry-run)
            preview_cmd = [
                "gcloud", "storage", "rsync", 
                "--recursive", 
                "--delete-unmatched-destination-objects",
                "--dry-run",
                self.local_path, f"gs://{self.gcs_bucket}/"
            ]
            
            preview_result = subprocess.run(
                preview_cmd, 
                capture_output=True, 
                text=True
            )
            
            if preview_result.returncode != 0:
                logger.error(f"동기화 미리보기 실패: {preview_result.stderr}")
                return False
            
            # 2. 변경사항 확인 (stdout + stderr 모두 확인)
            stdout_changes = preview_result.stdout.strip()
            stderr_output = preview_result.stderr.strip()
            
            # "Would copy", "Would delete" 등이 있으면 변경사항 있음
            has_changes = (
                "Would copy" in stderr_output or 
                "Would delete" in stderr_output or
                "Would remove" in stderr_output or
                stdout_changes
            )
            
            if has_changes:
                logger.info(f"동기화 예정 변경사항 감지됨")
                if stdout_changes:
                    logger.info(f"상세 변경사항:\n{stdout_changes}")
                if "Would copy" in stderr_output:
                    copy_count = stderr_output.count("Would copy")
                    logger.info(f"복사될 파일: 약 {copy_count}개")
            else:
                logger.info("동기화할 변경사항 없음")
                return True
            
            # 3. 실제 동기화 실행
            logger.info("실제 동기화 시작...")
            sync_cmd = [
                "gcloud", "storage", "rsync",
                "--recursive",
                "--delete-unmatched-destination-objects",
                self.local_path, f"gs://{self.gcs_bucket}/"
            ]
            
            sync_result = subprocess.run(
                sync_cmd,
                capture_output=True,
                text=True
            )
            
            if sync_result.returncode == 0:
                logger.info("파일 동기화 성공!")
                if sync_result.stdout:
                    logger.info(f"동기화 결과:\n{sync_result.stdout}")
                return True
            else:
                logger.error(f"파일 동기화 실패: {sync_result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"파일 동기화 중 예외 발생: {e}")
            return False

if __name__ == "__main__":
    sync_manager = FileSyncManager()
    result = sync_manager.sync_to_gcs()
    print(f"동기화 결과: {'성공' if result else '실패'}")