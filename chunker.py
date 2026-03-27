from fastapi import HTTPException
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
import io

CHUNK_SIZE    = 3200   # ~800 tokens
CHUNK_OVERLAP = 600    # ~150 tokens

def extract_text(file_bytes: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        text = extract_from_pdf(file_bytes)
    else:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=422,
                detail="Could not decode text file. Ensure it is UTF-8 encoded."
            )

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract text. File may be scanned or image-based."
        )

    return text


def chunk_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    return splitter.split_text(text)


def extract_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted
    return text