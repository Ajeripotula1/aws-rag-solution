"""FAQ retrieval. Stand-in for a Bedrock Knowledge Base until one exists.

retrieve() mirrors the shape of bedrock-agent-runtime `retrieve`: a text query in, a ranked list of
passages out. To switch to the Knowledge Base, replace the body of retrieve() with something like:

    response = boto3.client("bedrock-agent-runtime", region_name=config.AWS_REGION).retrieve(
        knowledgeBaseId=config.FAQ_KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
    )
    return [
        {"text": r["content"]["text"], "source": r.get("location", {}), "score": r.get("score")}
        for r in response["retrievalResults"]
    ]

and the agents using it don't need to change.
"""

from test_data import TEST_FAQS
import re


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "why",
    "you",
    "your",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS}


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    """Return up to top_k FAQ passages ranked by keyword overlap with the query."""
    query_tokens = _tokens(query)
    scored = []
    for faq in TEST_FAQS:
        text = f"Q: {faq['question']}\nA: {faq['answer']}"
        score = len(query_tokens & _tokens(f"{faq['category']} {text}"))
        if score:
            scored.append(
                {"text": text, "source": {"category": faq["category"]}, "score": score}
            )
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]
