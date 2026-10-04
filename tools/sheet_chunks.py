#!/usr/bin/env python3
"""Print data/Questions.csv in pieces that can be written to a Google Sheet with a values update.

  sheet_chunks.py info          row and chunk counts, plus a checksum per column (characters, or the sum
                                for the numeric columns)
  sheet_chunks.py N             chunk N: line 1 is the target range, line 2 is a JSON array of rows
  sheet_chunks.py episodes K    repeatCell requests that fill Episode, Round and Matchup for episode group K

Episode, Round and Matchup repeat on every row of an episode, so they are written once per episode with the
`episodes` requests and left null here (the values update skips null cells).

Text that the Sheets UI would turn into a number, date, boolean or formula gets a leading apostrophe so it
stays text: anything starting with a digit or = + - @, TRUE and FALSE, dollar amounts, and answers such as
"September 16".
"""
import csv
import json
import os
import re
import sys

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'Questions.csv')
LIMIT = 25000             # characters of JSON per chunk
SKIP = {0, 1, 8}          # Episode, Round, Matchup are filled by repeatCell requests
NUMERIC = {3, 16, 18}     # Question #, Points, Parts

MONTH = (r'(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|sep(t(ember)?)?'
         r'|oct(ober)?|nov(ember)?|dec(ember)?)')
CURRENCY = re.compile(r'^[$£€¥]\s?-?[\d,]+(\.\d+)?$')
DATE = re.compile(r'^' + MONTH + r'\.?,?\s+\d{1,4}(,\s*\d{4})?$', re.I)

rows = list(csv.reader(open(CSV, newline='', encoding='utf-8')))
header, data = rows[0], rows[1:]


def cell(i, v):
    if i in SKIP:
        return None
    if i in NUMERIC:
        return int(v) if v != '' else ''
    if v == '':
        return ''
    if (v[0] in '=+-@' or v[0].isdigit() or v.upper() in ('TRUE', 'FALSE')
            or CURRENCY.match(v) or DATE.match(v)):
        return "'" + v
    return v


def encode_row(r):
    return [cell(i, v) for i, v in enumerate(r)]


def boundaries():
    out, start, size = [], 0, 0
    for idx, r in enumerate(data):
        n = len(json.dumps(encode_row(r), ensure_ascii=True, separators=(',', ':'))) + 1
        if size and size + n > LIMIT:
            out.append((start, idx))
            start, size = idx, 0
        size += n
    out.append((start, len(data)))
    return out


BOUNDS = boundaries()


def col(n):
    s = ''
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


if len(sys.argv) < 2:
    sys.exit(__doc__)

cmd = sys.argv[1]
if cmd == 'info':
    print('data rows', len(data), 'chunks', len(BOUNDS))
    for i, h in enumerate(header):
        if i in NUMERIC:
            total = sum(int(r[i]) for r in data if r[i] != '')
        else:
            total = sum(len(r[i]) for r in data)
        print(col(i), h, total)
elif cmd == 'episodes':
    k = int(sys.argv[2])
    blocks = []
    for idx, r in enumerate(data):
        row = idx + 2
        if blocks and blocks[-1][0] == r[0]:
            blocks[-1][2] = row
        else:
            blocks.append([r[0], row, row, r[1], r[8]])
    reqs = []
    for ep, first, last, rnd, match in blocks[k * 18:(k + 1) * 18]:
        for c, val in ((0, ep), (1, rnd), (8, match)):
            reqs.append({"repeatCell": {"range": {"sheetId": 0, "startRowIndex": first - 1, "endRowIndex": last,
                                                   "startColumnIndex": c, "endColumnIndex": c + 1},
                                        "cell": {"userEnteredValue": {"stringValue": val}},
                                        "fields": "userEnteredValue"}})
    print(json.dumps(reqs, ensure_ascii=False, separators=(',', ':')))
else:
    n = int(cmd)
    a, b = BOUNDS[n]
    vals = [encode_row(r) for r in data[a:b]]
    print('range: Questions!A%d:V%d  rows=%d' % (a + 2, a + 1 + len(vals), len(vals)))
    print(json.dumps(vals, ensure_ascii=True, separators=(',', ':')))
