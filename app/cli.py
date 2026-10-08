"""Command line entry point.

Usage:
    python -m app.cli <file> --out <folder>

Saves the result as <name>.md, <name>.json and <name>.html in the folder.
"""
import argparse
import sys
from pathlib import Path

from .router import parse_file
from .models import DocumentResult
from .utils import sha256_file
from .writers import write_outputs


def main(argv=None):
    parser = argparse.ArgumentParser(prog='parse', description='Parse one document into Markdown, JSON and HTML.')
    parser.add_argument('file', help='the file to read')
    parser.add_argument('--out', default='outputs', help='folder for the results (default: outputs)')
    args = parser.parse_args(argv)

    src = Path(args.file)
    if not src.exists():
        print(f'Error: file not found: {src}', file=sys.stderr)
        return 1
    try:
        fmt, (pages, blocks, markdown, errors, status) = parse_file(str(src))
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2

    result = DocumentResult(filename=src.name, format=fmt, pages=pages, status=status,
                            errors=errors, blocks=blocks, markdown=markdown)
    payload = result.model_dump(mode='json')
    payload['metadata'] = {'sha256': sha256_file(str(src))}
    write_outputs(src.stem, args.out, payload, markdown, blocks, title=src.name)
    print(f'Parsed {src.name}: {len(blocks)} pieces, status {status}. Saved to {args.out}/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
