# eval.py
import os
from dotenv import load_dotenv
load_dotenv()   # must run before any local module imports that read env vars

from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from datasets import Dataset

from embedder import search_chunks
from generator import generate_answer

# your test dataset — question + ground truth pairs
# you run this AFTER uploading your test document
TEST_CASES = [
    {
        "question":     "What is the total amount due?",
        "ground_truth": "30798.89"
    },
    {
        "question":     "Who is the vendor?",
        "ground_truth": "CloudStack Solutions Pvt Ltd"
    },
    {
        "question":     "What is the invoice number?",
        "ground_truth": "INV-2025-0042"
    },
    {
        "question":     "How many line items are there?",
        "ground_truth": "5"
    },
    {
        "question":     "What is the GST rate applied?",
        "ground_truth": "18%"
    },
]


def run_eval(tenant_id: str):
    questions     = []
    answers       = []
    contexts      = []
    ground_truths = []

    for case in TEST_CASES:
        chunks = search_chunks(case["question"], tenant_id)
        result = generate_answer(case["question"], chunks)

        questions.append(case["question"])
        answers.append(result["answer"])
        contexts.append([chunk["text"] for chunk in chunks])   # RAGAS wants list[list[str]]
        ground_truths.append(case["ground_truth"])

    dataset = Dataset.from_dict({
        "question":     questions,
        "answer":       answers,
        "contexts":     contexts,
        "ground_truth": ground_truths,
    })

    llm        = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", temperature=0))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model="text-embedding-3-small"))

    faithfulness.llm        = llm
    answer_relevancy.llm        = llm
    answer_relevancy.embeddings = embeddings

    scores = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
    return scores


if __name__ == "__main__":
    import sys
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else input("tenant_id: ")
    results = run_eval(tenant_id)
    print(results)