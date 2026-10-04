#!/usr/bin/env python3
"""Expand compact episode files into Questions-sheet rows and check them.

Episode file grammar (details in README.md):

  @EP S41 E59                  episode id (season, episode number)
  @ROUND Championship          round label used in the sheet
  @TEAMS Team A | Team B       team 1 / team 2; matchup order = order the host introduced them
  @R1 Sam, Jackson, Penny      first names on team 1 (starters + alternates)
  @R2 Zach, Elaine, Max        first names on team 2
  T12 | Health | text | answer | Zach:C | Sam:C | note        tossup
  B12 | Health | text | answer | Zach:P10 | note               bonus (follows tossup 12)

  buzz / steal token:  Name:C  Name:I  Name:U   (team looked up from the roster)
                       2:I     team 2, player not named
                       ?:C     player and team not identified
                       NB      nobody buzzed          ?   whole tossup unclear
  bonus token:         C  I  U  P10  P5 ...  optionally  team/  and  Name:  in front
                       e.g.  2/Zach:I   ?/C    (team defaults to whoever won the tossup)
  note:                '!' prefix = needs review (flagged); '.' prefix = informational only
  multi-part text:     parts are separated by ' // ' and become ' | ' in the sheet
"""
import argparse
import csv
import difflib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, 'data', 'episodes')
CSV_DIR = os.path.join(ROOT, 'data', 'csv')
TRANSCRIPT_DIRS = [os.environ.get('SB_TRANSCRIPTS', ''), os.path.join(ROOT, 'data', 'transcripts')]

COLUMNS = ['Episode', 'Round', 'Question Type', 'Question #', 'Question Text', 'Correct Answer',
           'Category', 'Subject Area', 'Matchup', 'Answered By', 'Team', 'Result', 'Steal By',
           'Steal Team', 'Steal Result', 'Outcome', 'Points', 'Points To', 'Parts',
           'Needs Review', 'Review Notes', 'Transcript Excerpt']

# Category -> Subject Area, taken from the S42 workbook (majority mapping per category).
SUBJECT = {
    'Art': 'Fine Arts', 'Music': 'Fine Arts', 'Architecture': 'Fine Arts',
    'Foreign Language': 'Foreign Language',
    'Visual': 'General & Visual', 'Sports': 'General & Visual', 'Games': 'General & Visual',
    'Miscellaneous': 'General & Visual',
    'Mystery Word': 'Language Arts', 'Literature': 'Language Arts', 'Spelling': 'Language Arts',
    'English': 'Language Arts', 'Vocabulary': 'Language Arts', 'Grammar': 'Language Arts',
    'Algebra': 'Mathematics', 'Math': 'Mathematics', 'Geometry': 'Mathematics',
    'Pre-Calculus': 'Mathematics',
    'Religion': 'Religion & Mythology', 'Mythology': 'Religion & Mythology',
    'Astronomy': 'Science & Technology', 'Health': 'Science & Technology',
    'Chemistry': 'Science & Technology', 'Technology': 'Science & Technology',
    'Science': 'Science & Technology', 'Biology': 'Science & Technology',
    'Physics': 'Science & Technology', 'Geology': 'Science & Technology',
    'History': 'Social Studies', 'Geography': 'Social Studies', 'Government': 'Social Studies',
    'Economics': 'Social Studies', 'U.S. Presidents': 'Social Studies',
    'U.S. History': 'Social Studies', 'World History': 'Social Studies',
}
CAT_ALIAS = {c.lower(): c for c in SUBJECT}
CAT_ALIAS.update({
    'us history': 'U.S. History', 'u.s. history': 'U.S. History', 'american history': 'U.S. History',
    'world history': 'World History', 'foreign language': 'Foreign Language',
    'pre calculus': 'Pre-Calculus', 'precalculus': 'Pre-Calculus', 'pre-calc': 'Pre-Calculus',
    'misc': 'Miscellaneous', 'mystery': 'Mystery Word', 'us presidents': 'U.S. Presidents',
    'presidents': 'U.S. Presidents', 'arts': 'Art', 'fine arts': 'Art', 'computer science': 'Technology',
})

RESULT_WORD = {'C': 'Correct', 'I': 'Incorrect', 'U': 'Unclear'}
STOP = set('the a an of to in and or is are was were be by for on at as with that this it its from '
           'which what who whom whose how when where why do does did has have had not no yes you '
           'your their there these those one two'.split())
WORD = re.compile(r"[a-z0-9']+")
SPLIT = re.compile(r'\s\|(?=\s|$)')
HDR = re.compile(r'^\s*Episode\s+(\d+)\b', re.I)


# ---------------------------------------------------------------- transcripts
def fix_mojibake(s):
    if 'Ã' in s or 'â€' in s:
        try:
            return s.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


_cache = {}


def load_transcript(season):
    """season like 'S41' -> list of lines (index 0 = file line 1)."""
    if season in _cache:
        return _cache[season]
    num = season[1:]
    for d in TRANSCRIPT_DIRS:
        if not d:
            continue
        for name in ('season_%s.txt' % num, 's%s.txt' % num):
            p = os.path.join(d, name)
            if os.path.exists(p):
                with open(p, encoding='utf-8') as fh:
                    lines = [fix_mojibake(l) for l in fh.read().split('\n')]
                _cache[season] = lines
                return lines
    return None


def episode_span(lines, epnum):
    heads = [(i, int(HDR.match(l).group(1))) for i, l in enumerate(lines) if HDR.match(l)]
    for k, (i, n) in enumerate(heads):
        if n == epnum:
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            return i, end
    return None


def episode_lines(lines, epnum):
    """[(file line number, text)] of the non-empty lines of one episode."""
    sp = episode_span(lines, epnum)
    if not sp:
        return []
    return [(j + 1, lines[j]) for j in range(sp[0] + 1, sp[1]) if lines[j].strip()]


# ---------------------------------------------------------------- text helpers
def toks(s):
    return WORD.findall(s.lower().replace('’', "'"))


def content_tokens(s):
    return [t for t in toks(s) if t not in STOP and not t.isdigit() and len(t) > 2]


def fuzzy_in(tok, vocab):
    if tok in vocab:
        return True
    if len(tok) < 4:
        return False
    return bool(difflib.get_close_matches(tok, vocab, n=1, cutoff=0.82))


def strip_part_labels(s):
    return re.sub(r'\bPart \d+:\s*', '', s)


# ---------------------------------------------------------------- parsing
class Err(Exception):
    pass


def parse_episode_file(path):
    ep = {'path': path, 'teams': [], 'rosters': [set(), set()], 'qs': [], 'round': '', 'id': ''}
    with open(path, encoding='utf-8') as fh:
        for ln, raw in enumerate(fh, 1):
            line = raw.rstrip('\n')
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if line.startswith('@'):
                key, _, val = line[1:].partition(' ')
                val = val.strip()
                if key == 'EP':
                    ep['id'] = val
                elif key == 'ROUND':
                    ep['round'] = val
                elif key == 'TEAMS':
                    ep['teams'] = [t.strip() for t in val.split('|')]
                elif key in ('R1', 'R2'):
                    names = [n.strip() for n in val.split(',') if n.strip()]
                    ep['rosters'][int(key[1]) - 1] = {n.lower() for n in names}
                    ep['roster_display_%s' % key] = names
                else:
                    raise Err('%s:%d unknown directive @%s' % (path, ln, key))
                continue
            parts = [p.strip() for p in SPLIT.split(line)]
            m = re.fullmatch(r'([TB])(\d+)', parts[0])
            if not m:
                raise Err('%s:%d cannot parse line start %r' % (path, ln, parts[0]))
            ep['qs'].append({'kind': m.group(1), 'num': int(m.group(2)), 'parts': parts[1:], 'ln': ln})
    if not ep['id'] or not ep['round'] or len(ep['teams']) != 2:
        raise Err('%s: need @EP, @ROUND and two @TEAMS' % path)
    return ep


def team_of_name(ep, name, where):
    key = name.strip().lower()
    hits = [i for i in (0, 1) if key in ep['rosters'][i]]
    if not hits:
        raise Err('%s: player %r is on neither roster' % (where, name))
    if len(hits) > 1:
        raise Err('%s: player %r is on both rosters; write 1.%s or 2.%s' % (where, name, name, name))
    return hits[0]


def parse_actor(ep, tok, where):
    """Tossup buzz/steal token -> dict(kind, team, name, code) or None."""
    tok = tok.strip()
    if tok in ('', '-'):
        return None
    if tok.upper() == 'NB':
        return {'kind': 'NB'}
    if tok == '?':
        return {'kind': '?'}
    m = re.fullmatch(r'(?:([12?])\.)?([^:]*):([CIU])', tok)
    if not m:
        raise Err('%s: bad buzz/steal token %r' % (where, tok))
    pre, left, code = m.groups()
    left = left.strip()
    if pre == '?':
        return {'kind': 'A', 'team': 'U', 'name': left, 'code': code}
    if left == '?':
        return {'kind': 'A', 'team': 'U', 'name': '', 'code': code}
    if left in ('1', '2'):
        return {'kind': 'A', 'team': int(left) - 1, 'name': '', 'code': code}
    if left == '':
        raise Err('%s: token %r has no player or team' % (where, tok))
    if pre:
        team = int(pre) - 1
        if left.lower() not in ep['rosters'][team]:
            raise Err('%s: %r is not on roster %s' % (where, left, pre))
    else:
        team = team_of_name(ep, left, where)
    return {'kind': 'A', 'team': team, 'name': left, 'code': code}


def parse_bonus_token(ep, tok, where):
    tok = tok.strip()
    m = re.fullmatch(r'(?:([12?])/)?(?:(?:([12])\.)?([^:/]*):)?([CIU]\d*|P\d+)', tok)
    if not m:
        raise Err('%s: bad bonus token %r' % (where, tok))
    team_s, pre, name, code = m.groups()
    team = None
    if team_s:
        team = 'U' if team_s == '?' else int(team_s) - 1
    if name:
        name = name.strip()
        if pre:
            nteam = int(pre) - 1
        elif team is not None and team != 'U':
            nteam = team
        else:
            nteam = team_of_name(ep, name, where)
        if team is None:
            team = nteam
        elif team != nteam:
            raise Err('%s: %r is not on the bonus team' % (where, name))
    return {'team': team, 'name': name or '', 'code': code}


def canon_cat(cat, where, warns):
    key = cat.strip().lower()
    if key in CAT_ALIAS:
        return CAT_ALIAS[key]
    warns.append('%s: new category %r (no Subject Area mapping yet)' % (where, cat))
    return cat.strip()


# ---------------------------------------------------------------- expansion
def expand(ep):
    errs, warns, rows = [], [], []
    team_name = lambda t: ep['teams'][t] if t in (0, 1) else ('Unknown' if t == 'U' else '')
    matchup = '%s vs %s' % tuple(ep['teams'])
    tossups = {}
    last_t = 0
    for q in ep['qs']:
        n, kind, parts = q['num'], q['kind'], q['parts']
        where = '%s line %d (%s%d)' % (os.path.basename(ep['path']), q['ln'], kind, n)
        try:
            if kind == 'T':
                if len(parts) < 4:
                    raise Err('%s: tossup needs category | text | answer | buzz' % where)
                parts = parts + [''] * (6 - len(parts))
                cat, text, ans, buzz_s, steal_s, note = parts[:6]
                if steal_s.startswith(('.', '!')) and not note:
                    note, steal_s = steal_s, ''
                cat = canon_cat(cat, where, warns)
                if n != last_t + 1:
                    errs.append('%s: tossup number %d does not follow %d' % (where, n, last_t))
                last_t = n
                buzz = parse_actor(ep, buzz_s, where)
                steal = parse_actor(ep, steal_s, where)
                if buzz is None:
                    raise Err('%s: tossup needs a buzz field (NB = nobody buzzed)' % where)
                row = base_row(ep, matchup, 'Tossup', n, text, ans, cat, note)
                a_team = ''
                if buzz['kind'] == 'NB':
                    row.update(Result='No Buzz', Outcome='Missed', Points=0, **{'Points To': 'None given'})
                elif buzz['kind'] == '?':
                    row.update(Team='Unknown', Result='Unclear', Outcome='Unclear', Points=0,
                               **{'Points To': 'None given'})
                else:
                    a_team = buzz['team']
                    row.update(**{'Answered By': buzz['name'], 'Team': team_name(a_team),
                                  'Result': RESULT_WORD[buzz['code']]})
                    if buzz['code'] == 'C':
                        if steal:
                            raise Err('%s: steal after a correct buzz' % where)
                        row.update(Outcome='Correct', Points=10, **{'Points To': team_name(a_team)})
                    elif buzz['code'] == 'U':
                        row.update(Outcome='Unclear', Points=0, **{'Points To': 'None given'})
                    else:
                        row.update(Outcome='Missed', Points=0, **{'Points To': 'None given'})
                if steal:
                    if steal['kind'] != 'A':
                        raise Err('%s: bad steal token' % where)
                    if a_team in (0, 1) and steal['team'] in (0, 1) and steal['team'] == a_team:
                        raise Err('%s: steal by the same team as the first buzz' % where)
                    row.update(**{'Steal By': steal['name'], 'Steal Team': team_name(steal['team']),
                                  'Steal Result': RESULT_WORD[steal['code']]})
                    if steal['code'] == 'C':
                        row.update(Outcome='Correct', Points=10, **{'Points To': team_name(steal['team'])})
                    elif steal['code'] == 'U':
                        row.update(Outcome='Unclear', Points=0, **{'Points To': 'None given'})
                win = None
                if row['Outcome'] == 'Correct':
                    win = row['Points To']
                tossups[n] = {'cat': cat, 'win': win, 'row': row}
                rows.append(row)
            else:
                if len(parts) < 4:
                    raise Err('%s: bonus needs category | text | answer | result' % where)
                parts = parts + [''] * (5 - len(parts))
                cat, text, ans, res_s, note = parts[:5]
                ts = tossups.get(n)
                if ts is None:
                    raise Err('%s: no tossup %d before this bonus' % (where, n))
                cat = canon_cat(cat, where, warns) if cat else ts['cat']
                bt = parse_bonus_token(ep, res_s, where)
                if bt['team'] is None:
                    if ts['win'] is None:
                        raise Err('%s: tossup %d was not won; give the bonus team as 1/ 2/ or ?/' % (where, n))
                    bteam = ts['win']
                else:
                    bteam = team_name(bt['team'])
                    if ts['win'] is not None and bteam != ts['win']:
                        errs.append('%s: bonus team %s differs from tossup winner %s' % (where, bteam, ts['win']))
                code = bt['code']
                row = base_row(ep, matchup, 'Bonus', n, text, ans, cat, note)
                row.update(**{'Answered By': bt['name'], 'Team': bteam})
                if code[0] == 'C':
                    pts = int(code[1:]) if len(code) > 1 else 20
                    row.update(Result='Correct', Outcome='Correct', Points=pts, **{'Points To': bteam})
                elif code == 'I':
                    row.update(Result='Incorrect', Outcome='Missed', Points=0, **{'Points To': 'None given'})
                elif code[0] == 'P':
                    row.update(Result='Partial', Outcome='Partial', Points=int(code[1:]), **{'Points To': bteam})
                else:
                    row.update(Result='Unclear', Outcome='Unclear', Points='', **{'Points To': bteam})
                rows.append(row)
        except Err as e:
            errs.append(str(e))
    return rows, errs, warns


def base_row(ep, matchup, qtype, n, text, ans, cat, note):
    text = text.replace(' // ', ' | ')
    ans = ans.replace(' // ', ' | ')
    nparts = len(re.findall(r'\bPart \d+:', text))
    flag = 'Yes' if note.startswith('!') else ''
    note_txt = note[1:].strip() if note[:1] in '!.' and note else note.strip()
    return {'Episode': ep['id'], 'Round': ep['round'], 'Question Type': qtype, 'Question #': n,
            'Question Text': text, 'Correct Answer': ans, 'Category': cat,
            'Subject Area': SUBJECT.get(cat, ''), 'Matchup': matchup, 'Answered By': '', 'Team': '',
            'Result': '', 'Steal By': '', 'Steal Team': '', 'Steal Result': '', 'Outcome': '',
            'Points': '', 'Points To': '', 'Parts': nparts if nparts >= 2 else 1,
            'Needs Review': flag, 'Review Notes': note_txt, 'Transcript Excerpt': ''}


# ---------------------------------------------------------------- checks against captions
def tok_match(a, b):
    if a == b:
        return True
    if len(a) >= 5 and len(b) >= 5 and a[0] == b[0]:
        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85
    return False


def coverage(key, window_words):
    vocab = set(window_words)
    vl = list(vocab)
    hit = 0
    for k in key:
        if k in vocab or (len(k) >= 4 and difflib.get_close_matches(k, vl, n=1, cutoff=0.82)):
            hit += 1
    return hit / len(key)


def locate(ep_lines, rows):
    """Return the caption line index (into ep_lines) where each row's question starts."""
    stream = [(w, li) for li, (_, t) in enumerate(ep_lines) for w in toks(t)]
    words = [w for w, _ in stream]
    starts, pos = [], 0
    for r in rows:
        txt = strip_part_labels(r['Question Text'])
        txt = re.sub(r'\[unclear[^\]]*\]', ' ', txt)
        key = content_tokens(txt)[:10]
        if len(key) < 2:
            starts.append(None)
            continue
        win = 3 * len(key) + 12
        found = None
        for j in range(min(3, len(key))):
            for p in range(pos, len(words)):
                if tok_match(words[p], key[j]):
                    if coverage(key, words[max(0, p - 8):p + win]) >= 0.7:
                        found = p
                        break
            if found is not None:
                break
        if found is not None:
            # a bonus can start with words that also occur in the tossup just before it, so
            # prefer the nearby candidate whose tight window covers the whole key best
            tight, best = 2 * len(key) + 8, -1.0
            for q in range(found, min(len(words), found + win)):
                if any(tok_match(words[q], key[j]) for j in range(min(3, len(key)))):
                    sc = coverage(key, words[max(0, q - 2):q + tight])
                    if sc > best + 1e-9:
                        best, found = sc, q
        if found is None:
            starts.append(None)
        else:
            starts.append(stream[found][1])
            pos = found + 1
    return starts


def annotate_blocks(ep_lines, rows, warns):
    starts = locate(ep_lines, rows)
    for idx, r in enumerate(rows):
        s = starts[idx]
        label = '%s %s%d' % (r['Episode'], r['Question Type'][0], r['Question #'])
        if s is None:
            warns.append('%s: could not locate this question in the captions' % label)
            continue
        nxt = next((starts[j] for j in range(idx + 1, len(rows)) if starts[j] is not None), None)
        end = (nxt + 1) if nxt is not None else min(len(ep_lines), s + 25)
        lo = s - 1 if s > 0 and re.search(r'toss|bonus|visual', ep_lines[s - 1][1], re.I) else s
        block = ep_lines[lo:max(end, s + 1)]
        r['_lines'] = (block[0][0], block[-1][0])
        r['_block'] = ' / '.join(t.strip() for _, t in block)
        flagged_or_noted = bool(r['Review Notes'])
        vocab = list({w for _, t in block for w in toks(t)})
        ct = content_tokens(re.sub(r'\[unclear[^\]]*\]', ' ', strip_part_labels(r['Question Text'])))
        if ct and not flagged_or_noted:
            cov = sum(1 for k in ct if fuzzy_in(k, vocab)) / len(ct)
            if cov < 0.55:
                warns.append('%s: only %d%% of question words appear in the captions block (lines %d-%d)'
                             % (label, round(cov * 100), *r['_lines']))
        ans = r['Correct Answer']
        at = content_tokens(ans)
        if at and not flagged_or_noted and not re.search(r'\d', ans):
            cov = sum(1 for k in at if fuzzy_in(k, vocab)) / len(at)
            if cov < 0.34:
                warns.append('%s: answer %r not found in captions block (lines %d-%d); add a note if inferred'
                             % (label, ans[:40], *r['_lines']))


def finalize(rows):
    for r in rows:
        if 'Unclear' in (r['Result'], r['Steal Result'], r['Outcome']) and not r['Needs Review']:
            r['Needs Review'] = 'Yes'
            r['Review Notes'] = (r['Review Notes'] + '; ' if r['Review Notes'] else '') + 'result unclear in captions'
        if r['Needs Review'] == 'Yes':
            lines = r.get('_lines')
            if lines:
                r['Review Notes'] += ' (captions lines %d-%d)' % lines
            r['Transcript Excerpt'] = r.get('_block', '')[:1500]


# ---------------------------------------------------------------- driver
def build_file(path, verbose=False, write=True):
    ep = parse_episode_file(path)
    rows, errs, warns = expand(ep)
    season = ep['id'].split()[0]
    epnum = int(ep['id'].split()[1][1:])
    lines = load_transcript(season)
    elines = episode_lines(lines, epnum) if lines else []
    mentions = ''
    if elines:
        txt = ' '.join(t for _, t in elines)
        tmention = len(re.findall(r'\btoss\s?-?up\b|\bplus up\b|\bpass up\b|\bthrone\b', txt, re.I))
        bmention = len(re.findall(r'\bbonus\b', txt, re.I))
        mentions = 'captions mention toss up x%d, bonus x%d' % (tmention, bmention)
        annotate_blocks(elines, rows, warns)
    elif lines is not None:
        warns.append('no captions found for %s' % ep['id'])
    else:
        warns.append('transcript for %s not available; skipped caption checks' % season)
    finalize(rows)
    nt = sum(1 for r in rows if r['Question Type'] == 'Tossup')
    nb = len(rows) - nt
    flagged = sum(1 for r in rows if r['Needs Review'] == 'Yes')
    noted = sum(1 for r in rows if r['Review Notes'] and r['Needs Review'] != 'Yes')
    totals = {}
    for r in rows:
        if r['Points'] != '' and r['Points To'] not in ('None given', ''):
            totals[r['Points To']] = totals.get(r['Points To'], 0) + int(r['Points'])
    print('%s | %s | %s' % (ep['id'], ep['round'], rows[0]['Matchup'] if rows else '?'))
    print('  rows %d (T%d B%d) | flagged %d | info notes %d | %s' % (len(rows), nt, nb, flagged, noted, mentions))
    print('  points: ' + ', '.join('%s %d' % (k, v) for k, v in sorted(totals.items())))
    for e in errs:
        print('  ERROR ' + e)
    for w in warns:
        print('  warn  ' + w)
    if write and not errs:
        os.makedirs(CSV_DIR, exist_ok=True)
        out = os.path.join(CSV_DIR, ep['id'].replace(' ', '_') + '.csv')
        with open(out, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            for r in rows:
                w.writerow([r[c] for c in COLUMNS])
        print('  wrote ' + os.path.relpath(out, ROOT))
    return rows, errs, warns


def cmd_show(args):
    path = os.path.join(CSV_DIR, args.episode.replace(' ', '_') + '.csv')
    with open(path, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if args.flagged and r['Needs Review'] != 'Yes':
            continue
        who = r['Answered By'] or '-'
        if r['Question Type'] == 'Tossup':
            stl = ''
            if r['Steal Team']:
                stl = ' > steal %s/%s %s' % (r['Steal By'] or '-', r['Steal Team'][:10], r['Steal Result'])
            line = '%-4s %s/%s %s%s' % ('T' + r['Question #'], who, r['Team'][:10] or '-', r['Result'], stl)
        else:
            line = '%-4s %s/%s %s' % ('B' + r['Question #'], who, r['Team'][:10], r['Result'])
        print('%s -> %s %s%s | %s | %s | %s%s' % (
            line, r['Outcome'], r['Points'], ' to ' + r['Points To'][:10] if r['Points To'] != 'None given' else '',
            r['Category'], r['Question Text'][:args.width], r['Correct Answer'][:40],
            ('  [%s%s]' % ('REVIEW: ' if r['Needs Review'] == 'Yes' else 'note: ', r['Review Notes'][:args.width])) if r['Review Notes'] else ''))


def cmd_index(args):
    for season in args.seasons:
        lines = load_transcript(season)
        if lines is None:
            print('no transcript for', season)
            continue
        heads = [(i, l.strip()) for i, l in enumerate(lines) if HDR.match(l)]
        print('== %s: %d headers' % (season, len(heads)))
        for k, (i, h) in enumerate(heads):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            n = sum(1 for l in lines[i + 1:end] if l.strip())
            done = os.path.exists(os.path.join(EP_DIR, '%s_E%02d.txt' % (season, int(HDR.match(h).group(1)))))
            print('  %-42s file lines %6d-%-6d  text lines %4d %s%s' % (
                h[:42], i + 1, end, n, '(EMPTY)' if n < 20 else '', '  [done]' if done else ''))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')
    b = sub.add_parser('build', help='build and check one or more episode files')
    b.add_argument('files', nargs='*')
    b.add_argument('--no-write', action='store_true')
    sh = sub.add_parser('show', help='print a built episode compactly')
    sh.add_argument('episode', help='e.g. S41_E59')
    sh.add_argument('--flagged', action='store_true')
    sh.add_argument('--width', type=int, default=70)
    i = sub.add_parser('index', help='list episodes and their caption line ranges')
    i.add_argument('seasons', nargs='*', default=['S41', 'S40'])
    args = ap.parse_args()
    if args.cmd == 'index':
        cmd_index(args)
    elif args.cmd == 'show':
        cmd_show(args)
    elif args.cmd == 'build':
        files = args.files or sorted(os.path.join(EP_DIR, f) for f in os.listdir(EP_DIR) if f.endswith('.txt'))
        bad = 0
        for f in files:
            try:
                _, errs, _ = build_file(f, write=not args.no_write)
                bad += bool(errs)
            except Err as e:
                print('ERROR', e)
                bad += 1
        sys.exit(1 if bad else 0)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
