# DocuMind

A small Python, AI-powered document Q&A assistant. Add your own documents,
ask questions, and get answers grounded in what's actually in them — powered
by the Claude API.

## How it works

1. **Load** — `.txt`, `.md`, `.csv`, `.json`, `.pdf`, and `.docx` files are
   read into plain text (`documind/loaders.py`).
2. **Chunk** — long documents are split into overlapping ~1400-character
   pieces so retrieval can be precise (`documind/chunking.py`).
3. **Retrieve** — for each question, a lightweight TF-IDF ranker (pure
   Python, no embedding API needed) picks the most relevant chunks across
   all loaded documents (`documind/retriever.py`).
4. **Answer** — those chunks are handed to Claude with instructions to
   answer only from what's given and to name its sources
   (`documind/assistant.py`).

This is retrieval-augmented generation (RAG) in miniature: enough structure
to stay accurate on documents too large to fit in one prompt, without
pulling in a vector database.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # get one at console.anthropic.com
```

## Use it as a library

```python
from documind import DocuMind

dm = DocuMind()
dm.add_document("quarterly_report.pdf")
dm.add_document("meeting_notes.docx")

print(dm.ask("What were the Q3 revenue numbers?"))
print(dm.ask("Did the meeting notes mention any risks?"))
```

## Use it from the command line

```bash
python -m documind.cli
```

```
DocuMind — ask questions about your own documents
---------------------------------------------------
/add <path>       add a .txt .md .csv .json .pdf or .docx file
/list             show loaded documents
/remove <name>    drop a document
/quit             exit

> /add quarterly_report.pdf
  added "quarterly_report.pdf" (14 chunk(s))

> What was the biggest driver of Q3 growth?
According to "quarterly_report.pdf", ...
```

## Notes and limitations

- Scanned PDFs (images with no text layer) can't be read — DocuMind doesn't
  do OCR. It'll tell you clearly when that's the problem instead of
  returning an empty answer.
- The TF-IDF retriever is keyword-based, not semantic — great for names,
  numbers, and specific terms, weaker on questions phrased very differently
  from the document's own wording. Swap in an embedding-based retriever in
  `retriever.py` if you need that.
- `DEFAULT_MODEL` in `documind/assistant.py` is set to `claude-sonnet-5`.
  Change it to a faster/cheaper or more capable model ID as needed — see
  the [model overview docs](https://docs.claude.com/en/docs/about-claude/models/overview).
