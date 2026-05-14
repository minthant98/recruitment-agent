"""
parser.py — Extract raw text from a .docx JD file.
"""
from pathlib import Path
from docx import Document


def extract_text_from_docx(file_path: str) -> str:
    """
    Extract all paragraph text from a Word document.
    Returns a single string with newlines between paragraphs.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"JD file not found: {file_path}")
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Expected .docx file, got: {path.suffix}")

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)