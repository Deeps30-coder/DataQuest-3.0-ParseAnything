from email.message import EmailMessage

from app.text_parsers import (parse_csv, parse_email, parse_markdown, parse_rtf,
                              parse_txt, html_blocks)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return str(path)


def test_txt_splits_paragraphs(tmp_path):
    blocks, errors = parse_txt(_write(tmp_path, 'a.txt', 'First part.\n\nSecond part.'))
    assert errors == []
    assert [b.text for b in blocks] == ['First part.', 'Second part.']


def test_markdown_headings_tables_equations_and_lists(tmp_path):
    text = '# Title\n\nSome text.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n$$E = mc^2$$\n\n- item one\n'
    blocks, _ = parse_markdown(_write(tmp_path, 'a.md', text))
    assert [b.type for b in blocks] == ['heading', 'paragraph', 'table', 'equation', 'list']
    assert blocks[2].metadata['rows'] == [['A', 'B'], ['1', '2']]
    assert blocks[3].text == 'E = mc^2'


def test_csv_becomes_a_spreadsheet(tmp_path):
    blocks, errors = parse_csv(_write(tmp_path, 'sales.csv', 'Region,Revenue\nNorth,41.2\n'))
    assert errors == []
    assert blocks[0].type == 'spreadsheet'
    assert blocks[0].metadata['rows'][1] == ['North', '41.2']


def test_empty_csv_gives_a_clear_error(tmp_path):
    blocks, errors = parse_csv(_write(tmp_path, 'empty.csv', ''))
    assert blocks == []
    assert errors[0]['code'] == 'EMPTY_FILE'


def test_html_keeps_rowspan_colspan_figures_and_order():
    html = ('<h1>Income</h1><table>'
            '<tr><th colspan="2">FY2025</th></tr>'
            '<tr><td rowspan="2">Revenue</td><td>48.9</td></tr>'
            '<tr><td>Costs</td></tr></table>'
            '<img alt="Revenue chart"><p>Done</p>')
    blocks = html_blocks(html)
    assert [b.type for b in blocks] == ['heading', 'table', 'figure', 'paragraph']
    cells = blocks[1].metadata['cells']
    assert cells[0][0]['colspan'] == 2
    assert cells[1][0]['rowspan'] == 2
    assert blocks[2].text == 'Revenue chart'


def test_html_skips_scripts_and_styles():
    blocks = html_blocks('<style>p{}</style><p>Hello</p><script>var x=1;</script>')
    assert [b.text for b in blocks] == ['Hello']


def test_rtf_keeps_words_and_paragraphs(tmp_path):
    path = tmp_path / 'a.rtf'
    path.write_text(r'{\rtf1\ansi{\fonttbl{\f0 Arial;}}Hello\par World\par}', encoding='ascii')
    blocks, _ = parse_rtf(str(path))
    assert [b.text for b in blocks] == ['Hello', 'World']


def test_email_body_and_csv_attachment(tmp_path):
    msg = EmailMessage()
    msg['Subject'] = 'Q3 numbers'
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg.set_content('Hi, the numbers are attached.')
    msg.add_attachment(b'region,revenue\nNorth,41.2\n', maintype='text', subtype='csv',
                       filename='numbers.csv')
    path = tmp_path / 'mail.eml'
    path.write_bytes(msg.as_bytes())

    def child(file_path):
        blocks, errors = parse_csv(file_path)
        return 'csv', (1, blocks, '', errors, 'success')

    blocks, errors = parse_email(str(path), child)
    texts = [b.text for b in blocks]
    assert 'Q3 numbers' in texts
    assert any('numbers are attached' in t for t in texts)
    attached = [b for b in blocks if b.metadata.get('attachment') == 'numbers.csv']
    assert attached and attached[0].type == 'spreadsheet'
    assert errors == []


def test_email_attachment_that_fails_is_reported_not_crashed(tmp_path):
    msg = EmailMessage()
    msg['Subject'] = 'Broken attachment'
    msg.set_content('See the file.')
    msg.add_attachment(b'\x00\x01', maintype='application', subtype='octet-stream',
                       filename='bad.bin')
    path = tmp_path / 'mail.eml'
    path.write_bytes(msg.as_bytes())

    def child(file_path):
        raise ValueError('not supported')

    blocks, errors = parse_email(str(path), child)
    assert errors[0]['code'] == 'ATTACHMENT_FAILED'
    assert any(b.type == 'footnote' for b in blocks)
