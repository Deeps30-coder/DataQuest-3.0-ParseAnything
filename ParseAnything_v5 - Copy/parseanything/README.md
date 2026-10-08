# ParseAnything — DataQuest 3.0

ParseAnything reads your documents and turns them into clean, organized results:
text, tables, figures and structure, with a page and a confidence score for each piece.
It runs on your own computer.

## Supported files

| Type | Extensions |
| --- | --- |
| PDF (digital or scanned) | `.pdf` — shown as **Scanned PDF** or **Unscanned PDF** |
| Images (OCR) | `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.heic` |
| Word | `.docx`, `.doc` (old format, needs LibreOffice) |
| Excel | `.xlsx`, `.xls` (old format, needs LibreOffice), `.csv` |
| PowerPoint | `.pptx`, `.ppt` (old format, needs LibreOffice) |
| Web and text | `.html`, `.htm`, `.md`, `.markdown`, `.txt`, `.rtf` |
| Email | `.eml` (attachments are read too, including emails inside emails) |

ParseAnything checks what is inside each file, not only its name. If the contents
don't match the name, you'll see a message asking you to check the file.

Not supported yet: Outlook `.msg` files (save the email as `.eml`), encrypted files.
Unsupported or damaged files give a clear error instead of crashing.

## What you get

For each file:

- **Markdown** for reading.
- **JSON** with every block: its type, page, bounding box (where it's known) and confidence.
- **HTML** with tables that keep their merged cells (`rowspan` and `colspan`).

Block types include heading, paragraph, list, table, figure, caption, equation, footnote,
spreadsheet and slide. Running headers and footers in PDFs are removed from the body
and kept in the JSON.

## Quick start (Windows, cmd)

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

Install **Tesseract OCR** (for scanned pages and images) and add it to your PATH.
Install **LibreOffice** only if you need old `.doc`, `.xls` or `.ppt` files.

### Run the web page

```bat
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**, choose one or more files, and click **Parse all files**.
Each file gets its own result card.

### Run from the command line

```bat
python -m app.cli "C:\path\to\file.pdf" --out results
```

This saves `file.md`, `file.json` and `file.html` in the `results` folder.

### Optional: Streamlit demo

```bat
streamlit run app/ui.py
```

Open **http://127.0.0.1:8501**.

## API

- `POST /parse` with a form field called `file`. Add `?save=false` to skip saving.
- `GET /health` checks that the server is running.
- Full docs at **http://127.0.0.1:8000/docs**.

Uploads over 50 MB are rejected.

## Run with Docker

```bash
docker compose up --build
```

Then open http://localhost:8000.

## Tests

```bat
pip install pytest
pytest
```

## Project layout

```
app/
  main.py            API routes and the web page
  cli.py             Command line entry point
  router.py          Detects each file's type and picks the reader
  pdf_parser.py      PDFs, scanned pages, tables, running headers and footers
  office_parser.py   Word, Excel and PowerPoint files
  image_parser.py    Images (OCR), including HEIC photos
  text_parsers.py    TXT, Markdown, CSV, HTML, RTF and email
  writers.py         Markdown, JSON and HTML output
  models.py          The shape of every result
  ui.py              Streamlit demo screen
  static/            The web page (HTML, CSS, JavaScript)
tests/               Tests for each reader and the writers
```

## Known limits

These are part of the next steps, not finished yet:

- **Math:** equations written as text in Markdown (`$$ ... $$`) are kept as LaTeX. Formulas inside
  PDFs and images are not recognized yet.
- **Charts:** chart images are marked as figures, but their values are not read yet.
- **Tables across pages:** a table that continues onto the next page is still two tables.
- **Word details:** tracked changes, comments, footnotes and speaker notes are not read yet.
- **Rotated or skewed scans:** not corrected yet, so OCR may be weaker on them.
- **Speed:** pages are processed one at a time. Very large scans can take a while.
- **Self-checks:** totals in financial tables are not checked yet.
- **Review viewer:** not built yet.
