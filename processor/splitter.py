from typing import List
from pdf2image import convert_from_path


def split_pdf_to_images(pdf_path: str, output_folder: str, dpi: int = 300) -> List[str]:
    """
    PDF를 페이지별 이미지로 분리하고,
    생성된 로컬 이미지 파일 경로 리스트를 반환.
    """
    images = convert_from_path(pdf_path, dpi=dpi, output_folder=output_folder)
    return [img.filename for img in images]