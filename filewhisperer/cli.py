"""Interactive command-line chat for FileWhisperer.

Run with:
    python -m filewhisperer.cli

Commands inside the session:
    /add <path>       add a document (.txt .md .csv .json .pdf .docx .xlsx)
    /list             show loaded documents
    /remove <name>    drop a document
    /quit             exit
Anything else is treated as a question about your documents.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()  # reads a .env file in the current directory, if one exists

from .assistant import FileWhisperer
from .loaders import EmptyDocument, UnsupportedFileType

BANNER = """\
FileWhisperer — ask questions about your own documents
---------------------------------------------------
/add <path>       add a .txt .md .csv .json .pdf .docx or .xlsx file
/list             show loaded documents
/remove <name>    drop a document
/quit             exit
"""


def _add(dm: FileWhisperer, path: str) -> None:
    print("  reading... (scanned PDFs can take a bit longer, OCR runs page by page)")
    try:
        doc = dm.add_document(path)
        print(f"  added \"{doc.name}\" ({len(doc.chunks)} chunk(s))")
    except FileNotFoundError:
        print(f"  couldn't find file: {path}")
    except UnsupportedFileType as e:
        print(f"  {e}")
    except EmptyDocument as e:
        print(f"  {e}")


def main() -> None:
    print(BANNER)
    try:
        dm = FileWhisperer()
    except Exception as e:  # surfaces a missing API key immediately
        print(f"Setup error: {e}")

    history: list[dict] = []

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        if raw in ("/quit", "/exit"):
            break

        if raw.startswith("/add "):
            _add(dm, raw[len("/add "):].strip())
            continue

        if raw == "/list":
            docs = dm.list_documents()
            if not docs:
                print("  no documents loaded yet")
            for name in docs:
                print(f"  - {name}")
            continue

        if raw.startswith("/remove "):
            name = raw[len("/remove "):].strip()
            dm.remove_document(name)
            print(f"  removed \"{name}\" (if it was loaded)")
            continue

        # Otherwise, treat the input as a question.
        try:
            answer = dm.ask(raw, history=history)
        except RuntimeError as e:
            print(f"  {e}")
            continue
        except Exception as e:
            print(f"  something went wrong calling the model: {e}")
            continue

        print(f"\n{answer}")
        history.append({"role": "user", "content": raw})
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    sys.exit(main())
