# hdegis-data-processor

## Prerequisites

1. GCS에 처리하고자 하는 파일 업로드
2. .env 파일 작성
3. 가상환경
   ```
   conda create --name <가상환경 이름> python=3.12
   conda activate <가상환경 이름>
   ```

## Run

```
python main.py
```

## Structure

```
hdegis-data-processor/
├── main.py                        # 진입점
├── config.py                      # 환경변수 설정
├── README.md                      # README
├── requirements.txt               # 의존성 목록
├── .gitignore                     # gitignore
│
├── scheduler                      # 처리 orchestration
│   └── orchestrator.py            # 문서 전처리 전체 파이프라인
│
├── storage                        # storage 관련코드 (* 추후 MinIO 확장가능)
│   └── gcs_client.py              # GCSStorageClient 클래스 (GCS 관련코드)
│
├── db                             # DB 모델 및 연결 관련
│   ├── init_db.py                 # DB Table 초기화
│   ├── models.py                  # ORM 모델 (SQLAlchemy) == 스키마 정의
│   ├── repository.py              # DB에 insert/update/select 로직
│   └── session.py                 # DB 세션 초기화
│
├── processor                      # 문서 전처리 로직
│   ├── pdf_manager.py             # PDFManager 클래스
│   ├── extractor.py               # Gemini 기반 텍스트 추출 및 요약
│   ├── prompts.py                 # extractor.py에서 활용되는 프롬프트
│   └── splitter.py                # PDF → 개별 이미지(png)
│
├── utils                          # 유틸 함수
│   └── utils.py
│
└── key
   └── pjt-dev-hdegis-app-454401-bd4fac2d452b.json
```
