"""Tool for extracting and inserting Tamayura KAG scenarios from/to Markdown tables."""
import argparse
import os
import re
from pathlib import Path

TAG_RE = re.compile(r'\[(?:[^\]"\']|"[^"]*"|\'[^\']*\')*\]')
NAME_RE = re.compile(r'\[name\s+txt=[\"\']?([^\"\'\]]+)[\"\']?\]')
LINK_RE = re.compile(r'^(\s*\[link\s+[^\]]+\])(.*?)(\[endlink\](?:\[(?:r|s)\]\\?|\\|\s)*)$')
POST_RE = re.compile(r'((?:\[(?:np|l|ll|p|r|label|cm|hr|hide|show|s|sq|endlink)\b[^\]]*\]|\\)+)$')
PRE_RE = re.compile(r'^((?:\[(?:name|vo)\s+[^\]]*\]|\[r\]|\s)+)')

DEFAULT_WRAP_WIDTH = 44
WRAP_TOKEN_RE = re.compile(rf'{TAG_RE.pattern}|[ \t]+|[^ \t\[]+|\[')
LINE_RESET_RE = re.compile(r'\[(?:r|np|cm|ct|er)\b')
LINE_WAIT_RE = re.compile(r'\[(?:l|ll)\b')
NO_LINE_START = frozenset(".,!?:;…)]}—–-")
KEEP_WITH_NEXT = frozenset("а в во до за и из к ко на над не ни но о об от по под при с со у".split())


DEFAULT_NAMES = {
    'かすみ': 'Касуми',
    '那美': 'Нами',
    '真散': 'Мачиру',
    '真咲': 'Масаки',
    '真咲 ': 'Масаки',
    '藍': 'Ай',
    '冬馬': 'Тома',
    '仮面': 'Маска',
    '紅': 'Куренай',
    '先生': 'Учитель',
    'ねこ': 'Кот',
    'ネコ': 'Кот',
    'バイト': 'Подработчик',
    '仁科': 'Нисина',
    '全員': 'Все',
    '声': 'Голос',
    '男の声': 'Голос мужчины',
    '女性': 'Женщина',
    '学生': 'Ученик',
    '学生たち': 'Ученики',
    '学生１': 'Ученик 1',
    '学生２': 'Ученик 2',
    '学生３': 'Ученик 3',
    '裁判長': 'Судья',
    '裁判長の声': 'Голос судьи',
    '金髪の男': 'Блондин',
    'スーツの男': 'Мужчина в костюме',
    '鬼': 'Демон',
    '？？？': '???',
    'ユーくん': 'Ю-кун',
    'ユーコ': 'Юко',
    'ユーレイ': 'Призрак',
    'ユーレイ？': 'Призрак?',
    'Ｚユーレイ': 'Z-Призрак',
    'かすみ＆真咲': 'Касуми и Масаки',
    '冬馬＆藍': 'Тома и Ай',
    '冬馬、藍': 'Тома, Ай',
    '藍＆かすみ': 'Ай и Касуми',
}

EXCLUDED_SCRIPTS = {
    'first.ks', 'title.ks', 'staff.ks', 'snow.ks', 'zoom.ks', 
    'escape.ks', 'ruby.ks', 'sound.ks', 'option.ks'
}

def format_ruby(text):
    """
    Format furigana into double parentheses:
    [ruby2 text="read" ch="word"] -> word((read))
    [ruby text="read"]char -> char((read))
    Emphasis dots (ヽ, ・) are stripped.
    """
    # 1. ruby2: [ruby2 text="..." ch="..."]
    def rep_ruby2(match):
        s = match.group(0)
        m_txt = re.search(r'text=(?:"([^"]*)"|\'([^\']*)\'|([^\s\]]+))', s)
        m_ch = re.search(r'ch=(?:"([^"]*)"|\'([^\']*)\'|([^\s\]]+))', s)
        read = (m_txt.group(1) or m_txt.group(2) or m_txt.group(3) or '').strip() if m_txt else ''
        word = (m_ch.group(1) or m_ch.group(2) or m_ch.group(3) or '').strip() if m_ch else ''
        if read in ('ヽ', '・'):
            return word
        return f"{word}(({read}))"

    text = re.sub(r'\[ruby2\b[^\]]+\]', rep_ruby2, text)

    # 2. ruby: [ruby text="read"]char
    def rep_ruby1(match):
        read = (match.group(1) or match.group(2) or match.group(3) or '').strip()
        char = match.group(4)
        if read in ('ヽ', '・'):
            return char
        return f"{char}(({read}))"

    text = re.sub(
        r'\[ruby\s+text=(?:"([^"]*)"|\'([^\']*)\'|([^\s\]]+))\]([^\s\[\]])',
        rep_ruby1,
        text
    )

    # Strip any remaining ruby tags
    text = re.sub(r'\[ruby\b[^\]]+\]', '', text)
    return text

def parse_line(line):
    stripped = line.strip()
    if not stripped or stripped.startswith((';', '@', '*')):
        return None

    # 1. Choice line: [link ...] text [endlink] ...
    m_link = LINK_RE.match(stripped)
    if m_link:
        pre = m_link.group(1)
        raw_text = m_link.group(2)
        post = m_link.group(3)
        clean_text = format_ruby(raw_text).strip()
        return {
            'type': 'choice',
            'speaker': '<Choice>',
            'pre': pre,
            'text': clean_text,
            'post': post,
            'raw_line': line
        }

    # 2. Skip lines with no readable text (pure script tags)
    text_check = TAG_RE.sub('', stripped).strip().rstrip('\\')
    if not text_check:
        return None

    # 3. Speaker name
    name_m = NAME_RE.search(stripped)
    speaker = name_m.group(1) if name_m else ''

    # 4. Leading tags (pre)
    pre_match = PRE_RE.match(stripped)
    pre = pre_match.group(1) if pre_match else ''
    body = stripped[len(pre):]

    # 5. Trailing tags (post)
    post_match = POST_RE.search(body)
    if post_match:
        post = post_match.group(1)
        body = body[:-len(post)]
    else:
        post = ''

    # 6. Format furigana & clean mid tags
    clean_text = format_ruby(body).strip()

    return {
        'type': 'dialogue' if speaker else 'narration',
        'speaker': speaker,
        'pre': pre,
        'text': clean_text,
        'post': post,
        'raw_line': line
    }

def read_markdown_table(path):
    """Reads Markdown table and returns a list of rows with column dictionary."""
    if not path.exists():
        return []
    lines = path.read_text(encoding='utf-8').splitlines()
    if len(lines) < 2:
        return []

    # Parse header to determine column indexes
    header_cells = [c.strip().lower() for c in re.split(r'(?<!\\)\|', lines[0])[1:-1]]
    col_map = {}
    for idx, name in enumerate(header_cells):
        if name in ('n', '№', '#'):
            col_map['n'] = idx
        elif name in ('character', 'персонаж', 'speaker', 'name'):
            col_map['character'] = idx
        elif name in ('original', 'оригинал', 'jp'):
            col_map['original'] = idx
        elif name in ('tl', 'translate', 'перевод'):
            col_map['tl'] = idx
        elif name in ('tle', 'edit', 'tlc', 'редакт', 'вычитка'):
            col_map['tle'] = idx
        elif name in ('post', 'commands', 'команды', 'tags'):
            col_map['post'] = idx

    # Defaults if standard 6 columns
    if 'original' not in col_map:
        col_map = {'n': 0, 'character': 1, 'original': 2, 'tl': 3, 'tle': 4, 'post': 5}

    rows = []
    for line_idx, line in enumerate(lines[2:], 3):
        s = line.strip()
        if not s:
            continue
        cells = [c.strip() for c in re.split(r'(?<!\\)\|', line)[1:-1]]
        if len(cells) < len(col_map):
            continue

        def get_val(key):
            idx = col_map.get(key)
            if idx is not None and idx < len(cells):
                return cells[idx].replace(r'\|', '|').strip()
            return ''

        rows.append({
            'row_idx': line_idx,
            'n': get_val('n'),
            'character': get_val('character'),
            'original': get_val('original'),
            'tl': get_val('tl'),
            'tle': get_val('tle'),
            'post': get_val('post')
        })
    return rows

def extract_scenario(ks_path, md_path, existing_md=None):
    """Extracts translatable text from .ks to Markdown table."""
    raw = ks_path.read_bytes()
    lines = raw.decode('cp932').splitlines(keepends=True)

    # If updating an existing Markdown file, keep existing translations
    existing_map = {}
    if existing_md and existing_md.exists():
        for r in read_markdown_table(existing_md):
            if r['original']:
                existing_map[r['n']] = (r['character'], r['tl'], r['tle'])

    extracted_rows = []
    in_script = False
    for idx, line in enumerate(lines):
        s = line.strip()
        if s in ('@iscript', '[iscript]'):
            in_script = True
            continue
        if s in ('@endscript', '[endscript]'):
            in_script = False
            continue
        if in_script:
            continue

        parsed = parse_line(line)
        if parsed:
            extracted_rows.append(parsed)

    md_lines = [
        '| N | Character | Original | TL | TLE | Post |',
        '| --- | --- | --- | --- | --- | --- |'
    ]

    for n, item in enumerate(extracted_rows, 1):
        n_str = str(n)
        char_val = item['speaker']
        orig_val = item['text']
        post_val = item['post']
        tl_val = ''
        tle_val = ''

        if n_str in existing_map:
            ex_char, ex_tl, ex_tle = existing_map[n_str]
            if ex_char and ex_char != char_val:
                char_val = ex_char
            tl_val = ex_tl
            tle_val = ex_tle

        char_esc = char_val.replace('|', r'\|')
        orig_esc = orig_val.replace('|', r'\|')
        post_esc = post_val.replace('|', r'\|')
        tl_esc = tl_val.replace('|', r'\|')
        tle_esc = tle_val.replace('|', r'\|')

        md_lines.append(f'| {n} | {char_esc} | {orig_esc} | {tl_esc} | {tle_esc} | {post_esc} |')

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text('\n'.join(md_lines) + '\n', encoding='utf-8')
    return len(extracted_rows)

def wrap_text_kag(text, width, column=0):
    """Insert [r] at word boundaries and return the final visible column."""
    output = []
    word = []
    # An empty separator permits wrapping immediately after a click wait or
    # at the start of a physical line that continues the preceding one.
    gap = '' if column else None

    def flush_word():
        nonlocal column, gap
        if not word:
            return
        chunk = ''.join(word)
        visible = TAG_RE.sub('', chunk)
        separator = gap or ''
        length = len(visible)
        if (
            width and visible and column and gap is not None
            and column + len(separator) + length > width
            and visible[0] not in NO_LINE_START
            and visible not in ('"', "'")
        ):
            output.append('[r]')
            column = 0
        else:
            output.append(separator)
            column += len(separator)
        output.append(chunk)
        column += length
        word.clear()
        gap = None

    for match in WRAP_TOKEN_RE.finditer(text):
        token = match[0]
        if token.isspace():
            visible_words = TAG_RE.sub('', ''.join(word)).split()
            if visible_words and visible_words[-1].casefold() in KEEP_WITH_NEXT:
                word.append(token)
            else:
                flush_word()
                gap = (gap or '') + token
        elif LINE_WAIT_RE.match(token) or LINE_RESET_RE.match(token):
            flush_word()
            output.extend((gap or '', token))
            if LINE_RESET_RE.match(token):
                column, gap = 0, None
            else:
                column += len(gap or '')
                gap = ''
        else:
            word.append(token)
    flush_word()
    output.append(gap or '')
    return ''.join(output), column + len(gap or '')


def render_scenario(ks_path, md_path, name_map=None, *, wrap_width=DEFAULT_WRAP_WIDTH):
    """Inserts translations from Markdown into .ks and returns UTF-16LE bytes."""
    name_map = name_map or DEFAULT_NAMES
    raw = ks_path.read_bytes()
    orig_lines = raw.decode('cp932').splitlines(keepends=True)
    md_rows = read_markdown_table(md_path)

    md_iter = iter(md_rows)
    out_lines = []
    in_script = False
    replaced = 0
    column = 0

    for idx, line in enumerate(orig_lines):
        s = line.strip()
        if s in ('@iscript', '[iscript]'):
            in_script = True
            out_lines.append(line)
            continue
        if s in ('@endscript', '[endscript]'):
            in_script = False
            out_lines.append(line)
            continue
        if in_script:
            out_lines.append(line)
            continue

        parsed = parse_line(line)
        if not parsed:
            out_lines.append(line)
            continue

        row = next(md_iter, None)
        if row is None:
            raise ValueError(f'{ks_path.name}:{idx+1}: missing matching row in Markdown')

        # Select target translation: TLE > TL
        target = row['tle'] if row['tle'] else row['tl']
        # A physical newline advances the message unless escaped with \.
        # The page/return commands in Post also reset the visible column.
        continues = s.endswith('\\') and not LINE_RESET_RE.search(parsed['post'])
        if LINE_RESET_RE.search(parsed['pre']) or parsed['type'] == 'choice':
            column = 0

        if not target:
            # Preserve the Japanese source verbatim, including in a partial build.
            out_lines.append(line)
            if continues and parsed['type'] != 'choice':
                body = re.sub(r'\(\(.*?\)\)', '', parsed['text'])
                _, column = wrap_text_kag(body, 0, column)
            else:
                column = 0
            continue

        replaced += 1

        # Replace literal \n with KAG newline tag [r].
        target = target.replace(r'\n', '[r]')
        if wrap_width and parsed['type'] != 'choice':
            target, column = wrap_text_kag(target, wrap_width, column)
        if not continues:
            column = 0

        # Determine speaker translation
        speaker = parsed['speaker']
        char_row = row['character']
        translated_speaker = speaker
        if char_row and char_row not in (speaker, '<Choice>', '(Choice)'):
            translated_speaker = char_row
        elif speaker in name_map:
            translated_speaker = name_map[speaker]

        newline = '\r\n' if line.endswith('\r\n') else '\n'

        if parsed['type'] == 'choice':
            new_line = parsed['pre'] + target + parsed['post'] + newline
        elif parsed['type'] == 'dialogue':
            pre = parsed['pre']
            if translated_speaker and translated_speaker != speaker:
                pre = re.sub(r'\[name\s+txt=[\"\']?[^\"\'\]]+[\"\']?\]', f'[name txt="{translated_speaker}"]', pre)
            new_line = pre + target + parsed['post'] + newline
        else:
            new_line = parsed['pre'] + target + parsed['post'] + newline

        out_lines.append(new_line)

    if (extra := next(md_iter, None)) is not None:
        raise ValueError(f'{md_path.name}:{extra["row_idx"]}: extra unused row in Markdown')

    return ''.join(out_lines).encode('utf-16'), replaced

def discover_scenarios(scenario_dir):
    """Finds all unique .ks scenario files, giving priority to root files over scenario/ subfolder."""
    scenario_path = Path(scenario_dir)
    found = {}

    # 1. Search scenario/ subfolder first
    sub_dir = scenario_path / 'scenario'
    if sub_dir.exists():
        for p in sub_dir.glob('*.ks'):
            if p.name not in EXCLUDED_SCRIPTS and not p.name.startswith(('cgmode', 'evmode', 'mvmode', 'option', 'sound', 'snow', 'zoom', 'escape', 'ruby')):
                found[p.name] = p

    # 2. Search root scenario_dir (higher priority / patch files)
    for p in scenario_path.glob('*.ks'):
        if p.name not in EXCLUDED_SCRIPTS and not p.name.startswith(('cgmode', 'evmode', 'mvmode', 'option', 'sound', 'snow', 'zoom', 'escape', 'ruby')):
            found[p.name] = p

    return sorted(found.values(), key=lambda x: x.name)

def cmd_extract(args):
    scenarios = discover_scenarios(args.scenario)
    if not scenarios:
        raise ValueError(f'No scenario .ks files found in {args.scenario}')

    out_dir = Path(args.output)
    total_files = 0
    total_lines = 0

    print(f'Extracting {len(scenarios)} scenarios from {args.scenario} to {out_dir}...')
    for sc in scenarios:
        md_name = sc.stem + '.md'
        md_path = out_dir / md_name
        existing = md_path if (args.update and md_path.exists()) else None
        count = extract_scenario(sc, md_path, existing)
        total_files += 1
        total_lines += count
        print(f'  ✓ {sc.name} -> {md_name} ({count} lines)')

    print('=' * 50)
    print(f'Successfully extracted {total_files} files, {total_lines} total lines.')

def cmd_insert(args):
    scenarios = discover_scenarios(args.scenario)
    if not scenarios:
        raise ValueError(f'No scenario .ks files found in {args.scenario}')

    md_dir = Path(args.markdown)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_replaced = 0

    print(f'Building scenarios from {md_dir} and {args.scenario} into {out_dir}...')
    for sc in scenarios:
        md_name = sc.stem + '.md'
        md_path = md_dir / md_name
        if not md_path.exists():
            print(f'  ⚠ Skipping {sc.name} (no {md_name} found)')
            continue

        data, replaced = render_scenario(sc, md_path, wrap_width=args.wrap_width)
        out_file = out_dir / sc.name
        out_file.write_bytes(data)
        total_files += 1
        total_replaced += replaced
        print(f'  ✓ {sc.name} ({replaced} translated lines applied)')

    print('=' * 50)
    print(f'Successfully generated {total_files} .ks files, {total_replaced} translated lines applied.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)

    # extract
    p_ext = subparsers.add_parser('extract', help='Extract .ks scenarios into Markdown tables')
    p_ext.add_argument('scenario', type=Path, help='Path to game scenario directory (e.g. UNP)')
    p_ext.add_argument('output', type=Path, help='Output directory for .md tables')
    p_ext.add_argument('--update', action='store_true', help='Keep existing translations when updating')

    # insert
    p_ins = subparsers.add_parser('insert', help='Insert Markdown translations into .ks scenarios')
    p_ins.add_argument('markdown', type=Path, help='Path to directory containing .md tables')
    p_ins.add_argument('scenario', type=Path, help='Path to base scenario directory (e.g. UNP)')
    p_ins.add_argument('output', type=Path, help='Output directory for localized .ks files')

    p_ins.add_argument(
        '--wrap-width', type=int, default=DEFAULT_WRAP_WIDTH,
        help=f'Visible characters per line (default: {DEFAULT_WRAP_WIDTH}, 0 disables wrapping)',
    )

    args = parser.parse_args()
    if args.command == 'insert' and args.wrap_width < 0:
        p_ins.error('--wrap-width must be 0 or a positive integer')
    if args.command == 'extract':
        cmd_extract(args)
    elif args.command == 'insert':
        cmd_insert(args)

if __name__ == '__main__':
    main()
