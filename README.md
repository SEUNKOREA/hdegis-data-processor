# hdegis-data-processor

이 프로젝트는 GCS에 업로드된 PDF 문서를 자동으로 감지하고, 해당문서를 페이지 단위로 이미지(png)로 분리한 후 텍스트 추출 및 요약을 수행하여 데이터베이스에 저장하는 파이프라인입니다.

## Pipeline

1. **GCS 문서 감지**

   - `GCS_SOURCE_BUCKET` 내의 `.pdf` 파일 목록을 수집
   - DB에 없는 PDF 문서를 경로기반으로 탐지하여 `pdf_documents` 테이블에 등록

2. **PDF 분할 및 업로드**

   - 신규 문서는 GCS에서 다운로드 후 이미지로 분할
   - 분할된 이미지를 `GCS_PROCESSED_BUCKET`에 업로드
   - 각 페이지의 초기정보를 `pdf_pages` 테이블에 저장
   - 분할해서 GCS에 업로드 및 초기정보 테이블에 저장 성공 시, `processed=1`, 실패 시 `processed=0`으로 상태 업데이트

3. **페이지 단위 처리**

   - 각 이미지에 대해 OCR 및 설명 추출
   - 추출 결과를 `pdf_pages` 테이블에 저장
   - 추출 성공 시 `status='SUCCESS'`, 실패 시 `status='FAILED'`로 저장

4. **실패한 페이지 재처리**

   - `status='FAILED'` 또는 `'PENDING'`인 페이지를 재처리 시도
   - 각 페이지에 대해 앞선 5페이지 이미지를 context로 사용하여 다시 처리

---

## 🗂️ 데이터베이스 테이블 구조

### 1. `pdf_documents`

| 컬럼명         | 타입                | 설명                                                 |
| -------------- | ------------------- | ---------------------------------------------------- |
| `doc_id`       | `VARCHAR(128)` (PK) | 문서 고유 ID (해시 기반 생성)                        |
| `gcs_path`     | `VARCHAR(1000)`     | GCS 내 PDF 경로                                      |
| `processed`    | `TINYINT`           | 이미지 분할 및 업로드 성공 여부 (`1=성공`, `0=실패`) |
| `processed_at` | `DATETIME`          | 마지막 분할 시도 시각                                |
| `created_at`   | `DATETIME`          | 등록 시각                                            |

### 2. `pdf_pages`

| 컬럼명           | 타입                                   | 설명                                    |
| ---------------- | -------------------------------------- | --------------------------------------- |
| `page_id`        | `VARCHAR(128)` (PK)                    | 페이지 고유 ID (`doc_id + page_number`) |
| `doc_id`         | `VARCHAR(128)` (FK)                    | 연관 문서 ID                            |
| `page_number`    | `INTEGER`                              | 페이지 번호                             |
| `gcs_path`       | `VARCHAR(1000)`                        | GCS에 업로드된 이미지 경로              |
| `gcs_pdf_path`   | `VARCHAR(1000)`                        | 원본 PDF 경로                           |
| `extracted_text` | `LONGTEXT`                             | OCR 결과 (Markdown 형식)                |
| `summary`        | `TEXT`                                 | Gemini 기반 페이지 요약                 |
| `status`         | `ENUM`(`PENDING`, `SUCCESS`, `FAILED`) | 페이지 처리 상태                        |
| `error_message`  | `TEXT`                                 | 에러 발생 시 메시지                     |
| `created_at`     | `DATETIME`                             | 레코드 생성 시각                        |

---

## ✅ 처리 상태 기준

- `pdf_documents.processed`:

  - `1`: 이미지 분할 및 업로드 성공
  - `0`: 실패 (또는 아직 시도 전)

- `pdf_pages.status`:

  - `'PENDING'`: 아직 처리되지 않은 상태
  - `'SUCCESS'`: OCR 및 요약 완료
  - `'FAILED'`: 처리 실패

---

## 🔁 재처리 기준 및 방식

- `pdf_pages.status`가 `FAILED` 또는 `PENDING`인 경우 재처리 대상으로 분류
- 재처리 시, 같은 문서의 앞 5페이지 이미지들을 함께 context로 전달하여 Gemini 요약 성능 향상

---

## 🔧 추가 기능

- PDF 파일의 고유 ID는 SHA256 해시 기반으로 생성되어 중복 방지
- GCS 업로드/다운로드, OCR, 요약 처리 실패 등은 모두 로그 및 에러 메시지로 DB에 기록됨

---

이 구조는 확장 가능하며, 향후 문서 분류, 태깅, 고급 검색 기능 등도 쉽게 붙일 수 있는 아키텍처입니다. 추가로 그림도 넣고 싶다면, 전체 흐름을 도식화해도 좋습니다. 필요하시면 도식도도 만들어드릴 수 있어요.

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
