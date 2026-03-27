# generator.py
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks):
        parts.append(
            f"[Source {i+1} — {chunk['filename']}, "
            f"chunk {chunk['chunk_index']}]\n{chunk['text']}"
        )
    return "\n\n".join(parts)

def generate_answer(question: str, chunks: list[dict]) -> dict:

    # no chunks retrieved — tell user immediately, don't call LLM
    if not chunks:
        return {
            "answer":  "I couldn't find this information in your documents.",
            "sources": [],
        }

    context = build_context(chunks)

    system_prompt = (
        "You are a precise document assistant. "
        "Answer the user's question using ONLY the context provided. "
        "If the answer is not in the context, say exactly: "
        "'I couldn't find this information in your documents.' "
        "Never guess or use outside knowledge. "
        "Cite which source number you used."
    )

    user_prompt = (
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION:\n{question}"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,
    )

    answer = response.choices[0].message.content

    # build sources list — what the user can click to verify
    sources = [
        {
            "filename":    chunk["filename"],
            "chunk_index": chunk["chunk_index"],
        }
        for chunk in chunks
    ]

    return {
        "answer":  answer,
        "sources": sources,
    }