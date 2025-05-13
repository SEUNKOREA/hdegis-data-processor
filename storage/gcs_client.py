from typing import List
from google.cloud import storage

class GCSStorageClient:
    def __init__(self, source_bucket: str, target_bucket: str, client: storage.Client) -> None:
        self.source_bucket: str = source_bucket
        self.target_bucket: str = target_bucket
        self.client: storage.Client = client
    
    def list_pdfs(self, prefix: str = "") -> List[str]:
        bucket = self.client.bucket(self.source_bucket)
        blobs = bucket.list_blobs(prefix=prefix)
        return [blob.name for blob in blobs if blob.name.lower().endswith(".pdf")]
    
    def download_file(self, gcs_path: str, local_path: str, bucket_name: str) -> str:
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        blob.download_to_filename(local_path)
        return local_path
    
    def upload_file(self, local_image_path: str, gcs_path: str, bucket_name: str) -> str:
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(local_image_path)
        return gcs_path
    
    def make_output_path(self, src_gcs_path: str, page_num: int) -> str:
        parts = src_gcs_path.rsplit("/", 1)
        dirs = parts[0] if len(parts) > 1 else ""
        filename = parts[-1]
        base = filename.rsplit(".", 1)[0]
        folder = f"{dirs}/{base}" if dirs else base
        page_fname = f"{base}-page-{page_num:05d}.png"
        return f"{folder}/{page_fname}"
    
