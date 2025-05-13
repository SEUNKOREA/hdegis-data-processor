import os
import sys
# 프로젝트 폴더를 루트로 가정
PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from typing import List
from pdf2image import convert_from_path
from storage.gcs_client import GCSStorageClient


def split_pdf_to_images_and_upload(
        local_pdf_path: str,
        gcs_pdf_path: str,
        output_folder: str, 
        storage_client: GCSStorageClient,
        dpi: int = 300
    ):
    """
    PDF를 이미지로 분할 → GCS에 업로드 → 업로드된 GCS 경로 리스트 반환

    :param local_pdf_path: 로컬 PDF 경로 (다운로드된 PDF)
    :param gcs_pdf_path: GCS 상 PDF 경로 (GCS 내부 폴더 구조 유지용)
    :param output_folder: 임시 저장 경로
    :param storage_client: GCSStorageClient 인스턴스
    :return: GCS에 업로드된 이미지 경로 리스트
    """
    os.makedirs(output_folder, exist_ok=True)

    images = convert_from_path(local_pdf_path, dpi=dpi)
    gcs_paths: List[str] = []

    for idx, img in enumerate(images, start=1):
        file_name = f"page-{idx:05d}.png"
        local_img_path = os.path.join(output_folder, file_name)

        img.save(local_img_path, "PNG")

        gcs_path = storage_client.make_output_path(gcs_pdf_path, idx)
        uploaded_path = storage_client.upload_file(local_img_path, gcs_path, storage_client.target_bucket)
        gcs_paths.append(uploaded_path)

    return gcs_paths


if __name__ == "__main__":
    import os
    import sys
    # 프로젝트 폴더를 루트로 가정
    PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
    print(PROJECT_PATH)
    sys.path.append(PROJECT_PATH)

    from google.cloud import storage
    # from storage.gcs_client import GCSStorageClient
    from config import GCS_SOURCE_BUCKET, GCS_PROCESSED_BUCKET
    
    gcs_client = storage.Client()
    storage_client = GCSStorageClient(
        source_bucket=GCS_SOURCE_BUCKET,
        target_bucket=GCS_PROCESSED_BUCKET,
        client=gcs_client
    )

    res = split_pdf_to_images_and_upload(
        local_pdf_path = "/home/a543979/hdegis-data-processor/test_ieee.pdf",
        gcs_pdf_path = "1. International/IEEE/test_ieee.pdf",
        output_folder="temp",
        storage_client=storage_client
    )

    print(res)