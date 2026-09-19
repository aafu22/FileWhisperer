"""The FileWhisperer assistant: add documents, then ask questions about them.

Talks to a free model on OpenRouter (https://openrouter.ai) through its
OpenAI-compatible API, so no paid API key is required.

Usage:
    from filewhisperer import FileWhisperer

    dm = FileWhisperer()
    dm.add_document("quarterly_report.pdf")
    dm.add_document("meeting_notes.docx")
    print(dm.ask("What were the Q3 revenue numbers?"))
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from .chunking import Chunk, chunk_document
from .loaders import load_pages
from .retriever import TfidfRetriever

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# openrouter/free is OpenRouter's own router: it automatically picks whatever
# free model is currently available, so this keeps working even as specific
# free models (Llama, Gemini, etc.) get rotated in and out. If you want a
# specific model instead, set OPENROUTER_MODEL or change DEFAULT_MODEL below
# — see https://openrouter.ai/models?max_price=0 for the current list.
DEFAULT_MODEL = "openrouter/free"
TOP_K_CHUNKS = 6

SYSTEM_PROMPT_WITH_DOCS = """You are FileWhisperer, a helpful assistant with access to documents the person has \
shared. Follow these rules when answering:

- Prefer the document excerpts below when they're relevant to the question. When you use \
something from an excerpt, say which document it came from by name.
- If the excerpts don't cover the question, it's fine to answer from your own general \
knowledge instead — just don't imply it came from their documents.
- If excerpts from different documents disagree, point that out rather than picking one \
silently.
- Use markdown formatting where it genuinely helps readability: a table for comparing \
multiple items or numbers side by side, a numbered or bulleted list for steps or \
multiple related points, fenced code blocks (with a language tag) for any code, commands, \
or config. Don't force formatting onto a simple one-line answer that doesn't need it.
- Keep answers concise and directly responsive to the question.

Document excerpts:

{context}
"""

SYSTEM_PROMPT_NO_DOCS = """You are FileWhisperer, a helpful, friendly AI assistant. No documents have been \
added yet, so just have a normal conversation and answer from your own general knowledge, \
the same way any helpful assistant would. Keep replies natural and conversational rather \
than mentioning documents unless the person brings it up themselves. Use markdown formatting \
(tables, lists, fenced code blocks with a language tag) where it genuinely helps readability, \
but don't force it onto a simple answer that doesn't need it."""


@dataclass
class Document:
    name: str
    text: str
    chunks: list[Chunk] = field(default_factory=list)


def _looks_retryable(message: str) -> bool:
    """True for errors that are specific to *which* free model got picked,
    not to the request itself — so trying again (openrouter/free routes to
    a different model each time) has a real chance of succeeding."""
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
    """Some free-model endpoints hand back their own internal moderation
    status line — e.g. "User Safety: safe Response Safety: safe" — instead
    of an actual answer. It's non-empty, so it would otherwise look like a
    successful response; this catches that pattern so it gets retried like
    any other model-specific failure instead of being shown as the answer."""
    if len(text) > 200:
        return False  # a real answer this long is not a moderation stub
    lowered = text.lower()
    return any(
        s in lowered
        for s in ("user safety", "response safety", "safety categories")
    )


def _friendly_error(raw: str) -> str:
    """Turn a raw API error into something a non-developer can act on."""
    lowered = raw.lower()
    if "safety" in lowered and ("pii" in lowered or "privacy" in lowered):
        return (
            "The free model that handled this request refused to process the document "
            "because it looks like it contains personal information (a name, contact "
            "details, etc.) — this is common with resumes, and some free providers "
            "auto-block anything that looks like PII. FileWhisperer already retried with a "
            "different free model, but kept hitting the same kind of block. Try asking "
            "again in a moment."
        )
    if "moderation status instead of an answer" in lowered:
        return (
            "The free model that handled this request returned its internal moderation "
            "status instead of a real answer, and retrying kept landing on models doing "
            "the same thing. This is a quirk of some free providers, not a problem with "
            "your documents. Try asking again in a moment."
        )
    if "unavailable for free" in lowered or "no endpoints found" in lowered:
        return (
            "That model isn't available for free anymore. Set OPENROUTER_MODEL=openrouter/free "
            "in your .env file, or check https://openrouter.ai/models?max_price=0 for a "
            "model that's currently free."
        )
    if "429" in raw or "rate limit" in lowered:
        return "You've hit the free-tier rate limit. Wait a minute or two and try again."
    return raw


class FileWhisperer:
    """Holds a small library of documents and answers questions about them
    using retrieval-augmented generation against the Claude API."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.documents: dict[str, Document] = {}
        self._client = None  # lazily created so import/tests don't need an API key

    # -- document management -------------------------------------------------

    def add_document(self, path: str, display_name: str | None = None) -> Document:
        """Load, chunk, and index a document. `display_name` overrides the
        name shown/cited (useful when `path` is a temp file, e.g. when
        documents arrive as uploads rather than real files on disk).
        Raises UnsupportedFileType, EmptyDocument, or FileNotFoundError
        (from filewhisperer.loaders) if the file can't be read."""
        name = display_name or os.path.basename(path)
        pages = load_pages(path, display_name=name)
        chunks = chunk_document(name, pages)
        text = "\n\n".join(p.text for p in pages)
        doc = Document(name=name, text=text, chunks=chunks)
        self.documents[name] = doc
        return doc

    def remove_document(self, name: str) -> None:
        self.documents.pop(name, None)

    def list_documents(self) -> list[str]:
        return list(self.documents.keys())

    # -- retrieval -------------------------------------------------------------

    def _all_chunks(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for doc in self.documents.values():
            chunks.extend(doc.chunks)
        return chunks

    def retrieve(self, question: str, k: int = TOP_K_CHUNKS) -> list[Chunk]:
        """The top-k chunks (across all documents) most relevant to the
        question, best match first. Used both to build the prompt context
        and to show citations for what actually informed an answer."""
        chunks = self._all_chunks()
        if not chunks:
            return []
        retriever = TfidfRetriever(chunks)
        return [chunk for chunk, _score in retriever.top_k(question, k=k)]

    def relevant_context(self, question: str, k: int = TOP_K_CHUNKS) -> str:
        top = self.retrieve(question, k=k)
        parts = [
            f'[From "{chunk.doc_name}"{f", {chunk.page}" if chunk.page else ""}]\n{chunk.text}'
            for chunk in top
        ]
        return "\n\n---\n\n".join(parts)

    # -- asking questions --------------------------------------------------

    def set_credentials(self, api_key: str | None = None, model: str | None = None) -> None:
        """Update the API key and/or model after construction — e.g. from a
        UI form — and force the next call to rebuild the API client."""
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
                    "No OpenRouter API key found. Set the OPENROUTER_API_KEY environment "
                    "variable (get a free key at https://openrouter.ai/keys) or pass "
                    "api_key=... when creating FileWhisperer()."
                )
            from openai import OpenAI

            self._client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=self._api_key)
        return self._client

    def ask(self, question: str, history: list[dict] | None = None) -> str:
        """Answer a question. See ask_with_sources() for the same thing plus
        which document excerpts (if any) were used to ground the answer."""
        answer, _sources = self.ask_with_sources(question, history)
        return answer

    def ask_with_sources(
        self, question: str, history: list[dict] | None = None
    ) -> tuple[str, list[Chunk]]:
        """Answer a question, and also return the document excerpts (if
        any) that were retrieved and handed to the model as context - so a
        caller can show "sources" under the answer. If no documents have
        been added, has a normal conversation and returns an empty source
        list. `history` is an optional list of prior {"role":
        "user"|"assistant", "content": str} turns for follow-up questions."""
        if self.documents:
            sources = self.retrieve(question)
            parts = [
                f'[From "{c.doc_name}"{f", {c.page}" if c.page else ""}]\n{c.text}'
                for c in sources
            ]
            context = "\n\n---\n\n".join(parts)
            system_prompt = SYSTEM_PROMPT_WITH_DOCS.format(context=context)
        else:
            sources = []
            system_prompt = SYSTEM_PROMPT_NO_DOCS

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": question})

        client = self._get_client()

        # openrouter/free picks a different free model on each call, so a
        # model-specific failure (retired model, an over-eager moderation
        # filter) is often worth one or two retries rather than a single
        # try. A model the user picked explicitly gets no such benefit, so
        # we don't bother retrying it.
        attempts = 3 if self.model == "openrouter/free" else 1
        last_error_text = ""

        for attempt in range(attempts):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=messages,
                    extra_headers={
                        # Optional, but OpenRouter uses these for its public leaderboards.
                        "HTTP-Referer": "https://github.com/",
                        "X-Title": "FileWhisperer",
                    },
                )
                choice = response.choices[0]
                content = choice.message.content
                if content and not _looks_like_moderation_stub(content):
                    return content, sources
                if content:
                    last_error_text = (
                        "the model returned a moderation status instead of an answer: "
                        f"{content!r}"
                    )
                else:
                    last_error_text = (
                        f"The model returned no text (finish_reason="
                        f"{getattr(choice, 'finish_reason', 'unknown')})."
                    )
            except Exception as e:
                last_error_text = str(e)

            if attempt < attempts - 1 and _looks_retryable(last_error_text):
                time.sleep(1)
                continue
            break

        raise RuntimeError(_friendly_error(last_error_text))
