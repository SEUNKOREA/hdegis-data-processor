# hdegis-data-processor

이 프로젝트는 GCS에 업로드된 PDF 문서를 자동으로 감지하고,
해당문서를 페이지 단위로 이미지(png)로 분리한 후 텍스트 추출 및 요약을 수행하여
결과를 MySQL DB에 저장하는 PDF 처리 파이프라인입니다.

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
│   ├── utils.py
│   └── logger.py
│
└── key
   └── pjt-dev-hdegis-app-454401-bd4fac2d452b.json
```

## Pipeline

1. 데이터베이스 테이블이 존재하는지 확인하고 없으면 사전에 정의한 스키마의 형태로 생성

2. GCS 버킷에서 전체 PDF 파일 목록을 수집

3. 각 PDF 파일에 대해 해서(SHA-256)을 계산하여 이미 처리된 문서인지 확인

   - 처음 처리되는 문서라면 `pdf_documents` 테이블에 등록하고 처리 대상에 포함

4. 3에서 탐지된 신규문서에 대해서는 다음과 같은 처리를 수행:

   - GCS에서 PDF 파일을 임시로 다운로드 후 이미지로 분할
   - 분할된 이미지를 `GCS_PROCESSED_BUCKET`에 업로드
   - 업로드된 GCS 이미지 경로를 기반으로 초기 페이지 정보를 `pdf_pages` 테이블에 저장
   - 분할해서 GCS에 업로드 및 초기정보 테이블에 저장 성공 시, `pdf_documents` 테이블에 `processed=1`, 실패 시 `processed=0`으로 상태 업데이트
   - 각 페이지의 이미지에 대해:
     - Gemini 모델을 사용하여 텍스트 추출 및 요약 생성
     - 추출 결과를 `pdf_pages` 테이블에 업데이트
     - 추출 성공 시 `pdf_pages` 테이블에 `status='SUCCESS'`, 실패 시 `status='FAILED'`로 저장

5. 이전 실행에서 실패했던 문서(예: 이미지 분할 실패)는 다시 전체 문서 단위로 재처리

   - `pdf_documents` 테이블에 `processed=0 AND processed_at != NONE`

6. 이전 실행에서 실패했던 페이지(예: OCR 또는 요약 실패)는 해당 페이지 단위로 다시 처리
   - `pdf_pages` 테이블에 status='FAILED

## Database Table Schema

### 1. `pdf_documents`

| 컬럼명         | 타입                | 설명                                                              |
| -------------- | ------------------- | ----------------------------------------------------------------- |
| `doc_id`       | `VARCHAR(128)` (PK) | 문서 고유 ID (해시 기반 생성)                                     |
| `gcs_path`     | `VARCHAR(1000)`     | GCS 내 PDF 경로                                                   |
| `processed`    | `TINYINT`           | 이미지 분할 및 업로드 성공 여부 (`1=성공`, `0=실패`, `default=0`) |
| `processed_at` | `DATETIME`          | 마지막 분할 시도 시각                                             |
| `created_at`   | `DATETIME`          | 문서가 등록된 시각                                                |

### 2. `pdf_pages`

| 컬럼명           | 타입                                   | 설명                                    |
| ---------------- | -------------------------------------- | --------------------------------------- |
| `page_id`        | `VARCHAR(128)` (PK)                    | 페이지 고유 ID (`doc_id + page_number`) |
| `doc_id`         | `VARCHAR(128)` (FK)                    | PDF 문서 ID                             |
| `page_number`    | `VARCHAR(32)`                          | 페이지 번호                             |
| `gcs_path`       | `VARCHAR(1000)`                        | GCS에 업로드된 이미지 경로              |
| `gcs_pdf_path`   | `VARCHAR(1000)`                        | 원본 PDF GCS 경로                       |
| `extracted_text` | `LONGTEXT`                             | Gemini 기반 OCR 결과                    |
| `summary`        | `TEXT`                                 | Gemini 기반 페이지 요약                 |
| `status`         | `ENUM`(`PENDING`, `SUCCESS`, `FAILED`) | 페이지 처리 상태 (`default=PENDING`)    |
| `error_message`  | `TEXT`                                 | 에러 발생 시 메시지                     |
| `created_at`     | `DATETIME`                             | 레코드 생성(페이지 등록) 시각           |
