# hdegis-data-processor

이 프로젝트는 GCS에 업로드된 PDF 문서를 자동으로 감지하고,
해당문서를 페이지 단위로 이미지(png)로 분리한 후 텍스트 추출, 요약 및 임베딩을 수행하며,
결과를 MySQL DB에 저장하고 Elastic에 Indexing 하는 PDF 처리 자동 파이프라인입니다.

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

```
# 백그라운드 실행시
nohup python -u main.py > nohup-main.out 2>&1 &
```

## Structure

```
├── README.md
├── main.py                   # 진입점
├── config.py                 # 설정값
├── requirements.txt          # 의존성 목록
│
├── scheduler
│   └── orchestrator.py       # 전체 파이프라인
│
├── db
│   ├── initialize.py         # DB 초기화
│   ├── models.py             # ORM 모델 (SQLAlchemy) == 스키마 정의
│   ├── repository.py         # DB에 insert/update/select 로직
│   └── session.py            # DB 세션 초기화
│
├── processor                 # 문서 전처리 로직
│   ├── pdf_manager.py        # PDFManager 클래스
│   ├── extractor.py          # Gemini 기반 텍스트 추출 및 요약
│   ├── prompts.py            # extractor.py에서 활용되는 프롬프트
│   ├── embedder.py           # 임베딩 추출
│   └── elastic.py            # Elastic
│
├── storage                   # storage 관련코드 (* 추후 MinIO 확장가능)
│   └── gcs_client.py         # GCSStorageClient 클래스 (GCS 관련코드)
│
├── utils                     # 유틸 함수
│   ├── logger.py
│   └── utils.py
│
└── key
    └── pjt-dev-hdegis-app-454401-bd4fac2d452b.json
```

## Pipeline

1. 신규 문서 감지

   - GCS에서 PDF 목록을 가져와 로컬에서 해시를 계산.
   - DB에 이미 존재하는 문서인지 판단 (PDFDocument Table `doc_id` 기준으로 판단).
   - 새로운 문서만 2단계로 이동.

2. 문서 Split

   - PDF → 이미지(.png)로 분리.
   - 각 페이지는 PDFPage 테이블에 등록.

3. 텍스트 추출 (OCR)

   - Gemini API를 사용해 각 페이지 이미지에서 텍스트 추출.
   - extracted_text 컬럼에 저장, 상태는 extracted로 관리.

4. 요약 추출

   - 해당 페이지 + 앞선 5페이지를 컨텍스트로 사용.
   - Gemini로 요약 수행 → summary, summarized 상태 저장.

5. 임베딩 생성

   - 추출된 텍스트와 요약을 결합하여 임베딩 모델(Gemini Embedding)로 벡터 생성.
   - embedding, embedded 상태 관리.

6. Elasticsearch 인덱싱
   - 위에서 생성된 텍스트, 요약, 임베딩 벡터를 Elasticsearch에 저장.
   - indexed 상태 관리.

## Database Table Schema

### 1. `PDFDocument`

| 컬럼명     | 설명                  |
| ---------- | --------------------- |
| `doc_id`   | SHA256 해시 (Primary) |
| `gcs_path` | GCS 상 PDF 경로       |

### 2. `PDFPages`

| 컬럼명           | 타입                                   | 설명                                    |
| ---------------- | -------------------------------------- | --------------------------------------- |
| `page_id`        | `VARCHAR(128)` (PK)                    | 페이지 고유 ID (`doc_id + page_number`) |
| `doc_id`         | `VARCHAR(128)` (FK)                    | PDF 문서 ID                             |
| `page_number`    | `VARCHAR(32)`                          | 페이지 번호                             |
| `gcs_path`       | `VARCHAR(1000)`                        | GCS에 업로드된 이미지 경로              |
| `gcs_pdf_path`   | `VARCHAR(1000)`                        | 원본 PDF GCS 경로                       |
| `extracted_text` | `LONGTEXT`                             | Gemini 기반 OCR 결과                    |
| `summary`        | `TEXT`                                 | Gemini 기반 페이지 요약                 |
| `embedding`      | `LONGTEXT`                             | 임베딩 벡터                             |
| `extracted`      | `ENUM`(`PENDING`, `SUCCESS`, `FAILED`) | 추출 상태 (`default=PENDING`)           |
| `summarized`     | `ENUM`(`PENDING`, `SUCCESS`, `FAILED`) | 요약 상태 (`default=PENDING`)           |
| `embedded`       | `ENUM`(`PENDING`, `SUCCESS`, `FAILED`) | 임베딩 상태 (`default=PENDING`)         |
| `indexed`        | `ENUM`(`PENDING`, `SUCCESS`, `FAILED`) | 인덱싱 상태 (`default=PENDING`)         |
| `error_message`  | `TEXT`                                 | 에러 발생 시 메시지                     |
| `created_at`     | `DATETIME`                             | 레코드 생성(페이지 등록) 시각           |
| `updated_at`     | `DATETIME`                             | 레코드 마지막 업데이트 시각             |
