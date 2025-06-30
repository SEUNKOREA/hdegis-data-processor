import os
import sys
import hashlib
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

from storage.gcs_client import GCSStorageClient


PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)


def get_file_hash(file_path: str, extra_data: str = "", hash_type="sha256"):
    # 사용할 해시 알고리즘 선택
    hash_func = getattr(hashlib, hash_type)()

    # 파일을 바이너리 모드로 읽으면서 해시 업데이트
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)

    # extra_data (경로 등)도 바이트로 변환하여 해시에 추가
    if extra_data:
        hash_func.update(extra_data.encode("utf-8"))

    return hash_func.hexdigest()


def compute_doc_hash(storage_client: GCSStorageClient, gcs_pdf_path: str) -> str:
    """Download a PDF to a tmp file and return its sha-256 hash."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        storage_client.download_file(
            gcs_pdf_path, tmp.name, storage_client.source_bucket
        )
        return get_file_hash(tmp.name, extra_data=gcs_pdf_path)


def split_file_path(path: str):
    """
    경로 분리: "folder/subfolder/doc.pdf" → "folder/subfolder", "doc.pdf"
    """
    if "/" in path:
        parent_dir, filename = path.rsplit("/", 1)
    else:
        parent_dir, filename = "", path
    return parent_dir, filename


# --- Git Utils


def load_gitignore(path=".gitignore"):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        patterns = f.read().splitlines()
    return PathSpec.from_lines(GitWildMatchPattern, patterns)


def generate_tree(dir_path, prefix="", spec=None, base_path=""):
    tree_str = ""
    entries = sorted(os.listdir(dir_path))
    entries = [e for e in entries if not e.startswith(".")]  # 숨김 파일 기본 제거

    for index, entry in enumerate(entries):
        full_path = os.path.join(dir_path, entry)
        relative_path = os.path.relpath(full_path, base_path)

        if spec and spec.match_file(relative_path):
            continue  # .gitignore에 해당되면 스킵

        connector = "└── " if index == len(entries) - 1 else "├── "
        tree_str += f"{prefix}{connector}{entry}\n"

        if os.path.isdir(full_path):
            extension = "    " if index == len(entries) - 1 else "│   "
            tree_str += generate_tree(full_path, prefix + extension, spec, base_path)
    return tree_str


def save_to_readme(tree_str, readme_path="README.md"):
    with open(readme_path, "a", encoding="utf-8") as f:
        f.write("\n```\n")
        f.write(tree_str)
        f.write("```\n")


if __name__ == "__main__":
    base_dir = "."
    gitignore_spec = load_gitignore()
    tree_output = generate_tree(base_dir, spec=gitignore_spec, base_path=base_dir)
    save_to_readme(tree_output)
    print("📁 .gitignore 제외하고 README.md에 구조를 추가했습니다.")
