# FileWhisperer — Case Study

**A document Q&A assistant with real OCR, multi-column PDF handling, and
per-user accounts — built on a deliberately lightweight retrieval stack
instead of a vector database.**

[Live demo](#) · [Source](#) — *(fill in your deployed URL and repo link)*

---

## The problem

Most "chat with your documents" demos handle one case well — a clean,
single-column, digitally-generated PDF — and fall over on everything else:
scanned admit cards, two-column academic papers, spreadsheets, sideways
phone-scanned pages. FileWhisperer was built to handle the messy, realistic
version of that problem: whatever file someone actually has, not the ideal
case.

It also needed to run affordably. Rather than assume a paid OpenAI/Claude
API budget, it's built against **OpenRouter's free model tier**, which
introduces its own reliability problems (models get deprecated with no
notice, some free providers return moderation stubs instead of real
answers) that had to be engineered around directly.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| UI | Streamlit, custom CSS theme | Fast to build a real UI in pure Python; default theme overridden with a custom type system and color palette so it doesn't read as a template |
| LLM | OpenRouter (`openrouter/free` auto-router) | Free-tier access without hard-coupling to one model; auto-router avoids manual re-work when a specific free model gets deprecated |
| Retrieval | Custom TF-IDF ranker (pure Python) | No embedding API call needed, no vector DB to run — see "Why not LangChain/a vector store" below |
| PDF text | `pdfplumber` with a custom column-detection pass, `pypdf` fallback | Off-the-shelf extraction silently interleaves multi-column text; needed a real fix, not just a library swap |
| OCR | `pypdfium2` + `pytesseract`, parallelized | Scanned/photographed documents have no text layer at all |
| Spreadsheets | `openpyxl` → markdown tables | Sheets become citable, chunkable text instead of being unsupported |
| Accounts | SQLite + PBKDF2 (stdlib `hashlib`) | Self-contained, zero-dependency auth — see "Why not bcrypt" below |

## Architecture

```
 file (.pdf/.docx/.xlsx/.txt/...)
        │
        ▼
 ┌───────────────┐   digital text found?
 │   loaders.py   │───── yes ──► column-aware extraction (pdfplumber)
 │ (page-aware)   │
 │                │───── no ───► per-page OCR (parallel, confidence-scored
 └───────────────┘                rotation correction, contrast fallback)
        │
        ▼  list[Page]  (page/sheet boundaries preserved)
 ┌───────────────┐
 │  chunking.py   │  ~1400-char chunks, 200-char overlap, never spans a page
 └───────────────┘
        │
        ▼  list[Chunk]
 ┌───────────────┐
 │ retriever.py   │  TF-IDF cosine similarity — top-k chunks for the question
 └───────────────┘
        │
        ▼
 ┌───────────────┐
 │ assistant.py   │  builds a grounded prompt, calls OpenRouter, retries
 │                │  past model-specific failures (see below)
 └───────────────┘
        │
        ▼
      answer
```

## Key engineering decisions

### Chunk size: 1,400 characters, 200-character overlap

Chosen empirically rather than by default/guesswork: large enough that a
chunk usually contains a complete thought (most sentences/short paragraphs
fit whole), small enough that the TF-IDF ranker can discriminate between
chunks on a specific topic rather than every chunk scoring similarly
because it contains half the document. The 200-character overlap exists
specifically so a fact stated right at a chunk boundary doesn't get split
across two chunks and lost to both.

### Chunks never span a page boundary

This sounds like a minor implementation detail but it's what makes
accurate citation possible at all — chunking is done *per page* (or per
spreadsheet sheet/row-range), so every chunk can be traced back to exactly
one page number. Chunking the whole document as one flat string first,
then splitting, would blur that boundary.

### Multi-column PDF handling

Naive extraction (`pypdf`'s default, and even `pdfplumber`'s default mode)
reads left-to-right across the whole page width, which interleaves two
columns' lines into nonsense. The fix: detect the single largest
horizontal gap between word start-positions on a page; if it's wide
enough (>8% of page width — normal word/sentence spacing never gets close
to this), treat it as a column boundary, crop the page there, and read
the left column fully before the right. Verified against a real two-column
test PDF (interleaved before the fix, correct reading order after) and a
normal single-column PDF (confirmed the heuristic doesn't false-positive
on ordinary spacing).

### OCR: confidence-scored rotation correction, not just "try OCR"

The first version of the OCR pipeline had a real bug worth naming: a
sideways-scanned page doesn't fail OCR cleanly, it produces *garbled but
non-empty* text, which a naive "did OCR return anything" check accepts as
a valid answer. The fix checks Tesseract's own mean word-confidence score
first; only if that's low does it test the other three rotations and
keep whichever one Tesseract is actually confident about — rather than
whichever one happened to produce output first. Pages are also OCR'd in
parallel (thread pool, since each page's OCR is an independent subprocess
call), and a page that's part of an otherwise-digital PDF falls back to
OCR individually, rather than OCR'ing the whole document just because one
page is a scanned insert.

### Reliability against free-tier LLM quirks

Free models on OpenRouter get deprecated without notice and occasionally
return their own internal moderation status (`"User Safety: safe..."`)
as if it were the answer. Both are detected and trigger an automatic
retry — since `openrouter/free` routes to a different underlying model
each call, a retry has a real chance of landing somewhere that works. If
retries are exhausted, the raw API error is translated into a plain-English
explanation instead of surfacing JSON in the chat.

### Password storage without a compiled dependency

Accounts use PBKDF2-HMAC-SHA256 (260,000 iterations, random salt per
user) from Python's standard `hashlib`, not `bcrypt`. Functionally similar
security properties, but no C-extension compile step — which matters for
a project that specifically needs to `pip install` reliably on a variety
of machines, including Windows, without a native build toolchain.

### Why not LangChain / a vector database

For a single-user or small-team tool with a modest number of documents,
TF-IDF retrieval is fast, has zero infrastructure to run, and is easy to
reason about and debug — you can print the exact term weights that caused
a chunk to rank highly. A vector DB and embedding calls add real value at
larger scale or when queries are phrased very differently from the source
text's own wording, neither of which was the actual constraint here. This
was a deliberate scope decision, not an oversight — the retrieval layer
(`retriever.py`) is intentionally isolated behind one class so it could be
swapped for an embedding-based approach later without touching anything
else in the pipeline.

## Testing approach

Every feature above was verified with real inputs and assertions before
being considered done, run directly in a Python sandbox rather than
eyeballed: a synthetic two-column PDF to prove the column-detection fix
against the actual bug it was written to fix, a real 1×1 transparent PNG
decoded and verified before using it as a UI element, a simulated
sideways scan proving the pre-confidence-scoring version returned
garbage and the fixed version doesn't, cross-account database queries
proving one user's chat can't be loaded or deleted by another user's ID
even when directly attempted.

## What this demonstrates

- End-to-end RAG pipeline design (chunking, retrieval, prompting) built
  from primitives rather than a framework, with a clear rationale for
  that choice
- Debugging and fixing subtle correctness bugs (the OCR confidence issue)
  rather than just wiring libraries together
- Practical security fundamentals: salted password hashing, per-user data
  isolation enforced at the query level, secrets kept out of source
  control
- Working within real constraints — free-tier LLM quotas, no paid
  infrastructure, cross-platform installation reliability (Windows file
  locking, avoiding compiled dependencies)

## What I'd do differently at larger scale

- Swap SQLite for a hosted database so accounts survive a redeploy
- Add an embeddings-based retriever option alongside TF-IDF for semantic
  (not just keyword) matching
- Add usage/rate-limit tracking per account rather than relying solely on
  OpenRouter's own free-tier limits
