"""The FileWhisperer assistant: add documents, then ask questions about them.

Talks to a free model on OpenRouter through its OpenAI-compatible API.

Usage:
    from filewhisperer import FileWhisperer

    dm = FileWhisperer()
    dm.add_document("quarterly_report.pdf")
    print(dm.ask("What were the Q3 revenue numbers?"))
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

from .chunking import Chunk, chunk_document
from .loaders import load_pages
from .retriever import TfidfRetriever


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# openrouter/free automatically selects an available free model.
DEFAULT_MODEL = "openrouter/free"

TOP_K_CHUNKS = 6


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_WITH_DOCS = """You are FileWhisperer, a helpful assistant with access to documents the person has shared.

Follow these rules when answering:

- Prefer the document excerpts below when they're relevant to the question.
- When you use something from an excerpt, say which document it came from by name.
- If the excerpts don't cover the question, it's fine to answer from your own general knowledge instead — just don't imply it came from their documents.
- If excerpts from different documents disagree, point that out rather than picking one silently.
- Use markdown formatting where it genuinely helps readability.
- Keep answers concise and directly responsive to the question.

Document excerpts:

{context}
"""


SYSTEM_PROMPT_WITH_DOCUMENT_SCOPE = """You are FileWhisperer, a document-focused AI assistant.

The user has explicitly selected one document as the current source of truth.

Follow these rules strictly:

- Answer ONLY from the selected document excerpts provided below.
- Do not use outside knowledge when answering.
- Do not use information from any other uploaded document.
- If the selected document does not contain enough information to answer the question, clearly say that the selected document does not contain enough information.
- Do not invent or guess facts.
- Keep answers concise and directly responsive.
- Use markdown formatting where it genuinely improves readability.
- When useful, mention the selected document by name.

Selected document:

{document_name}

Document excerpts:

{context}
"""


SYSTEM_PROMPT_NO_DOCS = """You are FileWhisperer, a helpful, friendly AI assistant.

No documents have been added yet, so just have a normal conversation and answer from your own general knowledge, the same way any helpful assistant would.

Keep replies natural and conversational rather than mentioning documents unless the person brings it up themselves.

Use markdown formatting where it genuinely helps readability, but don't force it onto a simple answer that doesn't need it.
"""


# ---------------------------------------------------------------------------
# Document reference helpers
# ---------------------------------------------------------------------------

_DOCUMENT_REFERENCE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "this",
    "these",
    "those",
    "i",
    "you",
    "we",
    "they",
    "what",
    "which",
    "who",
    "how",
    "do",
    "does",
    "did",
    "now",
    "just",
    "answer",
    "only",
    "use",
    "using",
    "my",
    "your",
    "our",
    "their",
    "me",
    "please",
    "tell",
    "give",
    "can",
    "could",
    "would",
    "should",
}


def _normalize_reference_text(text: str) -> str:
    """Normalize text so filenames can be matched naturally."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _reference_tokens(text: str) -> set[str]:
    """Return meaningful words from a filename or question."""
    normalized = _normalize_reference_text(text)

    return {
        token
        for token in normalized.split()
        if token and token not in _DOCUMENT_REFERENCE_STOPWORDS
    }


def _document_reference_score(
    question: str,
    document_name: str,
) -> float:
    """Score how strongly a question refers to a document name."""

    question_normalized = _normalize_reference_text(question)

    # Ignore file extension for natural references such as
    # "my resume" instead of "my resume.docx".
    stem = os.path.splitext(document_name)[0]
    stem_normalized = _normalize_reference_text(stem)

    if not stem_normalized:
        return 0.0

    # Exact filename/stem phrase is the strongest signal.
    if stem_normalized in question_normalized:
        return 100.0

    question_tokens = _reference_tokens(question)
    document_tokens = _reference_tokens(stem)

    if not question_tokens or not document_tokens:
        return 0.0

    overlap = question_tokens & document_tokens

    if not overlap:
        return 0.0

    return len(overlap) / len(document_tokens)


def _is_multi_document_question(question: str) -> bool:
    """Detect questions that explicitly require more than one document."""

    normalized = _normalize_reference_text(question)

    phrases = (
        "compare these documents",
        "compare the documents",
        "compare these files",
        "compare the files",
        "compare these two",
        "compare the two",
        "difference between these documents",
        "difference between the documents",
        "difference between these files",
        "difference between the files",
        "difference between these two",
        "differences between these two",
        "differences between the two",
        "compare both documents",
        "compare both files",
        "compare both pdfs",
        "difference between these two pdfs",
        "differences between these two pdfs",
        "between these two pdfs",
    )

    if any(phrase in normalized for phrase in phrases):
        return True

    # Questions that ask about multiple files without using the word
    # "compare", for example:
    # "what are these two files about?"
    # "tell me about both PDFs"
    # "what do these documents contain?"
    multi_reference = any(
        phrase in normalized
        for phrase in (
            "these two files",
            "these two documents",
            "these two pdfs",
            "these two reports",
            "both files",
            "both documents",
            "both pdfs",
            "both reports",
        )
    )
    if multi_reference:
        return True

    # Natural-language comparison requests such as
    # "what is different between the two PDFs?"
    has_comparison = any(
        word in normalized
        for word in ("compare", "comparison", "difference", "differences", "different")
    )
    has_multi_reference = any(
        phrase in normalized
        for phrase in ("two documents", "two files", "two pdfs", "both documents", "both files", "both pdfs")
    )
    return has_comparison and has_multi_reference


def _is_clear_scope_request(question: str) -> bool:
    """Return True when the user explicitly asks to leave document focus."""

    normalized = _normalize_reference_text(question)

    clear_phrases = (
        "search all documents",
        "search across all documents",
        "use all documents",
        "use all my documents",
        "look across all documents",
        "answer from all documents",
        "answer using all documents",
        "dont limit to this document",
        "do not limit to this document",
        "clear document focus",
        "remove document focus",
        "stop using this document",
        "stop using that document",
    )

    return any(
        phrase in normalized
        for phrase in clear_phrases
    )


# ---------------------------------------------------------------------------
# Document-intent detection
# ---------------------------------------------------------------------------

_DOCUMENT_QUESTION_PATTERNS = (
    # Summaries / overviews
    "summarize",
    "summarise",
    "summary",
    "overview",
    "key points",
    "main points",
    "important points",
    "highlights",
    "main takeaways",
    "takeaways",

    # Document contents
    "what does the document say",
    "what does this document say",
    "what is this document about",
    "what's this document about",
    "tell me about this document",
    "explain this document",
    "explain the document",

    # Information commonly extracted from documents
    "important numbers",
    "important dates",
    "key numbers",
    "key dates",
    "main risks",
    "risks mentioned",
    "key risks",
    "main findings",
    "key findings",
    "findings mentioned",
    "recommendations",
    "key recommendations",

    # Natural references to an uploaded file
    "the document",
    "this document",
    "the file",
    "this file",
    "the report",
    "this report",
    "the resume",
    "my resume",
    "my cv",
    "the cv",

    # Natural references to multiple uploaded files
    "these two files",
    "these two documents",
    "these two pdfs",
    "these two reports",
    "both files",
    "both documents",
    "both pdfs",
    "both reports",
    "these files",
    "these documents",
    "these pdfs",
    "these reports",
)


def _is_document_question(question: str) -> bool:
    """Detect questions that naturally refer to uploaded documents."""

    normalized = _normalize_reference_text(question)

    return any(
        phrase in normalized
        for phrase in _DOCUMENT_QUESTION_PATTERNS
    )


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Document:
    name: str
    text: str
    chunks: list[Chunk] = field(default_factory=list)


# ---------------------------------------------------------------------------
# OpenRouter helpers
# ---------------------------------------------------------------------------

def _looks_retryable(message: str) -> bool:
    """True for errors specific to which free model got picked."""

    lowered = message.lower()

    return any(
        s in lowered
        for s in (
            "unavailable for free",
            "no endpoints found",
            "safety categories",
            "user safety",
            "moderation status instead of an answer",
            "429",
            "rate limit",
        )
    )


def _looks_like_moderation_stub(text: str) -> bool:
    """Detect moderation-status text returned instead of an answer."""

    if len(text) > 200:
        return False

    lowered = text.lower()

    return any(
        s in lowered
        for s in (
            "user safety",
            "response safety",
            "safety categories",
        )
    )


def _friendly_error(raw: str) -> str:
    """Turn a raw API error into something a non-developer can act on."""

    lowered = raw.lower()

    if "safety" in lowered and (
        "pii" in lowered or "privacy" in lowered
    ):
        return (
            "The free model that handled this request refused to process "
            "the document because it looks like it contains personal "
            "information (a name, contact details, etc.) — this is common "
            "with resumes, and some free providers auto-block anything "
            "that looks like PII. FileWhisperer already retried with a "
            "different free model, but kept hitting the same kind of block. "
            "Try asking again in a moment."
        )

    if "moderation status instead of an answer" in lowered:
        return (
            "The free model that handled this request returned its internal "
            "moderation status instead of a real answer, and retrying kept "
            "landing on models doing the same thing. This is a quirk of "
            "some free providers, not a problem with your documents. "
            "Try asking again in a moment."
        )

    if (
        "unavailable for free" in lowered
        or "no endpoints found" in lowered
    ):
        return (
            "That model isn't available for free anymore. Set "
            "OPENROUTER_MODEL=openrouter/free in your .env file, or check "
            "https://openrouter.ai/models?max_price=0 for a model that's "
            "currently free."
        )

    if "429" in raw or "rate limit" in lowered:
        return (
            "You've hit the free-tier rate limit. "
            "Wait a minute or two and try again."
        )

    return raw


# ---------------------------------------------------------------------------
# FileWhisperer
# ---------------------------------------------------------------------------

class FileWhisperer:
    """Holds a small library of documents and answers questions about them."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model or os.environ.get(
            "OPENROUTER_MODEL",
            DEFAULT_MODEL,
        )

        self._api_key = api_key or os.environ.get(
            "OPENROUTER_API_KEY"
        )

        self.documents: dict[str, Document] = {}

        # The currently selected document.
        self.active_document: str | None = None

        self._client = None

    # -----------------------------------------------------------------------
    # Document management
    # -----------------------------------------------------------------------

    def add_document(
        self,
        path: str,
        display_name: str | None = None,
    ) -> Document:
        """Load, chunk, and index a document."""

        name = display_name or os.path.basename(path)

        pages = load_pages(
            path,
            display_name=name,
        )

        chunks = chunk_document(
            name,
            pages,
        )

        text = "\n\n".join(
            page.text
            for page in pages
        )

        doc = Document(
            name=name,
            text=text,
            chunks=chunks,
        )

        self.documents[name] = doc

        return doc

    def remove_document(self, name: str) -> None:
        """Remove a document and clear focus if it was selected."""

        self.documents.pop(
            name,
            None,
        )

        if self.active_document == name:
            self.active_document = None

    def list_documents(self) -> list[str]:
        """Return uploaded document names."""
        return list(self.documents.keys())

    # -----------------------------------------------------------------------
    # Document reference detection
    # -----------------------------------------------------------------------

    def resolve_document_reference(
        self,
        question: str,
    ) -> str | None:
        """Find the uploaded document most clearly referenced by a question."""

        if not self.documents:
            return None

        scored = [
            (
                name,
                _document_reference_score(
                    question,
                    name,
                ),
            )
            for name in self.documents
        ]

        scored = [
            (name, score)
            for name, score in scored
            if score > 0
        ]

        if not scored:
            return None

        scored.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        best_name, best_score = scored[0]

        # Don't guess when two documents are equally plausible.
        if len(scored) > 1:
            second_score = scored[1][1]

            if best_score == second_score:
                return None

        return best_name

    def clear_document_scope(self) -> None:
        """Stop restricting retrieval to a particular document."""
        self.active_document = None

    # -----------------------------------------------------------------------
    # Retrieval
    # -----------------------------------------------------------------------

    def _all_chunks(self) -> list[Chunk]:
        """Return chunks from all uploaded documents."""

        chunks: list[Chunk] = []

        for doc in self.documents.values():
            chunks.extend(doc.chunks)

        return chunks

    def _fallback_document_chunks(
        self,
        document_name: str | None = None,
        k: int = TOP_K_CHUNKS,
    ) -> list[Chunk]:
        """Return chunks for a clear document-oriented question.

        This fallback is intentionally separate from TF-IDF retrieval.

        It is allowed only when the user is clearly asking about a document,
        so we don't repeat the old bug where unrelated questions such as
        "latest cricket news" received arbitrary document sources.
        """

        if document_name:
            document = self.documents.get(
                document_name
            )

            if document is None:
                return []

            return document.chunks[:k]

        # If exactly one document is uploaded, it is the natural target
        # for a generic question such as "What are the key points?"
        if len(self.documents) == 1:
            document = next(
                iter(self.documents.values())
            )

            return document.chunks[:k]

        # With multiple documents and no explicit focus, distribute the
        # fallback context across the documents instead of filling all k
        # slots from the first document. This is important for questions
        # such as "what are these two files about?" where lexical retrieval
        # may not find a useful keyword match.
        documents = list(self.documents.values())
        chunks: list[Chunk] = []

        if not documents:
            return chunks

        index = 0
        while len(chunks) < k:
            added_this_round = False

            for document in documents:
                if index < len(document.chunks) and len(chunks) < k:
                    chunks.append(document.chunks[index])
                    added_this_round = True

            if not added_this_round:
                break

            index += 1

        return chunks

    def retrieve(
        self,
        question: str,
        k: int = TOP_K_CHUNKS,
        document_name: str | None = None,
        document_names: list[str] | None = None,
    ) -> list[Chunk]:
        """Retrieve relevant chunks.

        If document_name is provided, retrieval is restricted to that
        document. Otherwise, all uploaded documents are searched.

        For clear document-oriented questions, a controlled fallback can
        use document chunks when TF-IDF has no lexical match.
        """

        if document_names:
            selected = [
                self.documents[name]
                for name in document_names
                if name in self.documents
            ]

            if not selected:
                return []

            # When a message has attachments, treat those attachments as
            # the primary context for that message, just like a ChatGPT
            # message with files attached. Older files in the same chat
            # remain available for later questions.
            per_document = max(2, k // len(selected))
            balanced_matches: list[Chunk] = []

            for document in selected:
                retriever = TfidfRetriever(document.chunks)
                matches = [
                    chunk
                    for chunk, _score in retriever.top_k(
                        question,
                        k=per_document,
                    )
                ]

                if not matches and _is_document_question(question):
                    matches = document.chunks[:per_document]

                balanced_matches.extend(matches)

            return balanced_matches[:k]

        if document_name:
            document = self.documents.get(
                document_name
            )

            if document is None:
                return []

            chunks = document.chunks

        else:
            # Comparison questions must receive context from EACH document,
            # rather than allowing the global TF-IDF ranking to fill all top-k
            # slots with chunks from whichever document happens to score first.
            # This is what makes questions such as "difference between these
            # two PDFs" genuinely multi-document.
            if _is_multi_document_question(question) and len(self.documents) > 1:
                per_document = max(2, k // len(self.documents))
                balanced_matches: list[Chunk] = []

                for document in self.documents.values():
                    retriever = TfidfRetriever(document.chunks)
                    matches = [
                        chunk
                        for chunk, _score in retriever.top_k(
                            question,
                            k=per_document,
                        )
                    ]

                    if not matches and _is_document_question(question):
                        matches = document.chunks[:per_document]

                    balanced_matches.extend(matches)

                if balanced_matches:
                    return balanced_matches[:k]

            chunks = self._all_chunks()

        if not chunks:
            return []

        retriever = TfidfRetriever(
            chunks
        )

        matches = [
            chunk
            for chunk, _score in retriever.top_k(
                question,
                k=k,
            )
        ]

        # Normal retrieval succeeded.
        if matches:
            return matches

        # Do NOT fall back for arbitrary questions.
        #
        # This is what prevents:
        # "Tell me the latest cricket news"
        #
        # from producing:
        # Sources -> Sample_Quarterly_Report.md
        if not _is_document_question(question):
            return []

        return self._fallback_document_chunks(
            document_name=document_name,
            k=k,
        )

    def relevant_context(
        self,
        question: str,
        k: int = TOP_K_CHUNKS,
        document_name: str | None = None,
        document_names: list[str] | None = None,
    ) -> str:
        """Return formatted context from relevant chunks."""

        top = self.retrieve(
            question,
            k=k,
            document_name=document_name,
            document_names=document_names,
        )

        parts = [
            f'[From "{chunk.doc_name}"'
            f'{f", {chunk.page}" if chunk.page else ""}]\n'
            f'{chunk.text}'
            for chunk in top
        ]

        return "\n\n---\n\n".join(parts)

    # -----------------------------------------------------------------------
    # API credentials
    # -----------------------------------------------------------------------

    def set_credentials(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """Update API key and/or model."""

        if api_key is not None:
            self._api_key = api_key
            self._client = None

        if model is not None:
            self.model = model

    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:

            if not self._api_key:
                raise RuntimeError(
                    "No OpenRouter API key found. Set the "
                    "OPENROUTER_API_KEY environment variable "
                    "(get a free key at https://openrouter.ai/keys) "
                    "or pass api_key=... when creating FileWhisperer()."
                )

            from openai import OpenAI

            self._client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self._api_key,
            )

        return self._client

    # -----------------------------------------------------------------------
    # Asking questions
    # -----------------------------------------------------------------------

    def ask(
        self,
        question: str,
        history: list[dict] | None = None,
    ) -> str:
        """Answer a question."""

        answer, _sources = self.ask_with_sources(
            question,
            history,
        )

        return answer

    def ask_with_sources(
        self,
        question: str,
        history: list[dict] | None = None,
        document_names: list[str] | None = None,
    ) -> tuple[str, list[Chunk]]:
        """Answer a question and return the sources used.

        Document behavior:

        1. If the user explicitly mentions a document, that document
           becomes the active document.

        2. Follow-up questions continue using the active document.

        3. If the user explicitly asks to search all documents, the
           document focus is cleared.

        4. If there is no active document, retrieval searches all
           uploaded documents.

        5. Generic document questions such as "What are the key points?"
           can use the uploaded document when lexical retrieval has no
           direct keyword match.

        6. Unrelated questions do not receive arbitrary document sources.
        """

        # ------------------------------------------------------------------
        # Determine document scope
        # ------------------------------------------------------------------

        if _is_clear_scope_request(question) or _is_multi_document_question(question):

            # A comparison request is explicitly about multiple documents,
            # so a previously selected single-document focus must not leak
            # into this question.
            self.clear_document_scope()

        else:

            referenced_document = (
                self.resolve_document_reference(
                    question
                )
            )

            if referenced_document:
                self.active_document = referenced_document

        # ------------------------------------------------------------------
        # Retrieve relevant document context
        # ------------------------------------------------------------------

        if self.documents:

            if document_names:
                selected_names = [
                    name for name in document_names
                    if name in self.documents
                ]
                sources = self.retrieve(
                    question,
                    document_names=selected_names,
                )
                parts = [
                    f'[From "{chunk.doc_name}"'
                    f'{f", {chunk.page}" if chunk.page else ""}]\n'
                    f'{chunk.text}'
                    for chunk in sources
                ]
                context = "\n\n---\n\n".join(parts)
                selected_label = ", ".join(selected_names)
                system_prompt = (
                    SYSTEM_PROMPT_WITH_DOCS.format(
                        context=context
                    )
                    + "\n\nFor this message, prioritize these attached documents: "
                    + selected_label
                )

            elif self.active_document:

                sources = self.retrieve(
                    question,
                    document_name=self.active_document,
                )

                parts = [
                    f'[From "{chunk.doc_name}"'
                    f'{f", {chunk.page}" if chunk.page else ""}]\n'
                    f'{chunk.text}'
                    for chunk in sources
                ]

                context = "\n\n---\n\n".join(parts)

                system_prompt = (
                    SYSTEM_PROMPT_WITH_DOCUMENT_SCOPE.format(
                        document_name=self.active_document,
                        context=context,
                    )
                )

            else:

                sources = self.retrieve(
                    question
                )

                parts = [
                    f'[From "{chunk.doc_name}"'
                    f'{f", {chunk.page}" if chunk.page else ""}]\n'
                    f'{chunk.text}'
                    for chunk in sources
                ]

                context = "\n\n---\n\n".join(parts)

                system_prompt = (
                    SYSTEM_PROMPT_WITH_DOCS.format(
                        context=context
                    )
                )
        else:

            sources = []

            system_prompt = SYSTEM_PROMPT_NO_DOCS

        # ------------------------------------------------------------------
        # Build model messages
        # ------------------------------------------------------------------

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        messages.extend(
            history or []
        )

        messages.append(
            {
                "role": "user",
                "content": question,
            }
        )

        # ------------------------------------------------------------------
        # Call OpenRouter
        # ------------------------------------------------------------------

        client = self._get_client()

        attempts = (
            3
            if self.model == "openrouter/free"
            else 1
        )

        last_error_text = ""

        for attempt in range(attempts):

            try:

                response = client.chat.completions.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=messages,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/",
                        "X-Title": "FileWhisperer",
                    },
                )

                choice = response.choices[0]

                content = choice.message.content

                if (
                    content
                    and not _looks_like_moderation_stub(
                        content
                    )
                ):
                    return content, sources

                if content:

                    last_error_text = (
                        "the model returned a moderation status "
                        "instead of an answer: "
                        f"{content!r}"
                    )

                else:

                    last_error_text = (
                        "The model returned no text "
                        f"(finish_reason="
                        f"{getattr(choice, 'finish_reason', 'unknown')})."
                    )

            except Exception as e:

                last_error_text = str(e)

            if (
                attempt < attempts - 1
                and _looks_retryable(
                    last_error_text
                )
            ):
                time.sleep(1)
                continue

            break

        raise RuntimeError(
            _friendly_error(
                last_error_text
            )
        )