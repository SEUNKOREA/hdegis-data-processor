import os
import sys
# 프로젝트 폴더를 루트로 가정
PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from db.models import Base
from db.session import engine

if __name__ == "__main__":
    print("📦 DB 테이블 생성 중...")
    Base.metadata.create_all(bind=engine)
    print("✅ 모든 테이블 생성 완료!")