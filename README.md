# Scholars' Bowl episode parser

Turns the auto-generated caption transcripts of *Tennessee Scholars' Bowl* (seasons 41 and 40)
into rows in the same format as the Season 42 `Questions` sheet: the 19 original columns plus
three review columns (`Needs Review`, `Review Notes`, `Transcript Excerpt`).

## Output

| Where | What |
|---|---|
| [Google Sheet](https://docs.google.com/spreadsheets/d/1WuuMKO38TOw4kVJcfPlkz4xKOONf6aRNJdFEsKEK370/edit) | `Questions` (every row), `Review Queue` (live filter of the flagged rows), `Notes` |
| `data/Questions.csv` | the same rows, 22 columns |
| `data/review_queue.csv` | the flagged rows only, with the caption lines each one came from |
| `data/Questions.xlsx` | the three tabs as a workbook, formatted like the S42 file |
| `data/episodes/*.txt`, `data/csv/*.csv` | per-episode source and generated rows |

Season 40 has 56 episodes (4,435 rows: 2,571 tossups, 1,864 bonuses) and Season 41 has 16 (1,260 rows:
700 tossups, 560 bonuses). 472 rows are flagged `Needs Review`, and 360 rows have `Team` = `Unknown`.

```
data/episodes/S41_E59.txt   compact hand-written source for one episode (the checked work)
data/csv/S41_E59.csv        generated rows for that episode
tools/build.py              expands and checks episode files
tools/assemble.py           merges the per-episode CSVs into the combined files in data/
tools/sheet_chunks.py       prints Questions.csv in chunks for writing into the Google Sheet
data/transcripts/           (git-ignored) season_40.txt / season_41.txt as supplied
```

## Coverage

* Season 40: episodes 1 to 10 and 17 to 62. Episodes 11 to 16 are not in `season_40.txt`.
* Season 41: episodes 39 to 51, 53, 55 and 59. Episodes 35 to 38, 52, 54 and 57 have a header but no
  caption text. Episodes 56 and 58 carry the text of episode 59 word for word (checked line by line), so
  episode 59 is entered once.
* `Round` by episode. Season 40: Round 1 = 1 to 31, Round of 32 = 32 to 47, Round of 16 = 48 to 55,
  Round of 8 = 56 to 59, Round of 4 = 60 and 61, Championship = 62. Season 41: Round of 32 = 39 to 44,
  Round of 16 = 45 to 51, Round of 8 = 53 and 55, Championship = 59.

## Conventions for Seasons 40 and 41

* Team labels are the school name. A school that fielded more than one team in a season is labelled with
  its captain, for example `Maryville High School (Mohammed's team)`, and each team keeps one label across
  its episodes. Schools that share a name are told apart by place: `Central High School (Knoxville)`,
  `Corbin High School (KY)`, `Somerset High School (KY)`.
* Player names are first names from the host's introductions. A normalization pass gave each player one
  spelling across the episodes, but the captions garble many names (Olivia appears as "Livia", Mohammed as
  "Mohib", Costin as "Coston"), so some spellings can still be wrong.
* The Season 40 captions turn "mo" into "Mohib" inside some words ("Mohibdel" for "model"); the question
  text has the real word restored.
* `Team` = `Unknown` and `Points To` = `Unknown` when the captions name neither the buzzer nor the team.
  Where the host gives a halftime margin or says both teams scored over 400, those figures were used to
  place some unnamed tossups (episodes 59 and 60), and the row's `Review Notes` gives the reasoning. The
  rest stay `Unknown`.
* The totals that `build` prints are partial for episodes 58, 61 and 62, because some buzzers are unnamed
  and some bonuses have no clear ruling. The captions never give the score.
* A halftime challenge or a re-ruling is entered with the final ruling and a note (for example episode 57
  bonus 8, where Webb's successful challenge adds 20).
* A question the captions cut off or skip is entered with what is readable, `[unclear]` where words are
  missing, and flagged.

## Review flags

`Needs Review` = `Yes` marks a row to check. `Review Notes` says what is uncertain and `Transcript Excerpt`
holds the caption lines the row came from. A row is flagged when its note starts with `!` in the episode
file, and automatically when `Result` is `Unclear` or `Team` / `Steal Team` is `Unknown`. A note starting
with `.` is informational and does not flag the row.

## Rebuilding the combined files

```
python3 tools/build.py build data/episodes/*.txt     # rewrites data/csv/*.csv, must report 0 errors
python3 tools/assemble.py                            # rewrites data/Questions.csv, review_queue.csv, Questions.xlsx
```

`assemble.py` stops on duplicate rows, em dashes in the text columns and `Unclear` results that are not
flagged. `--no-xlsx` skips the workbook, which needs `openpyxl`.

## Google Sheet

The sheet was filled from `data/Questions.csv` through the Sheets connector in 86 chunks of about 70 rows
(`python3 tools/sheet_chunks.py N` prints chunk N as a JSON array for a values update), then compared
with the CSV cell by cell. Dollar amounts and one date-like answer were written as text so Sheets keeps
them as typed. `Review Queue` is a `FILTER` formula over the `Needs Review` column of `Questions`, and the
counts on `Notes` are formulas. To rebuild it by hand, upload `data/Questions.csv` with File > Import and
choose Replace current sheet.

## Per-episode workflow

```
python3 tools/build.py index S41                    # caption line ranges, EMPTY episodes, [done] markers
python3 tools/build.py build data/episodes/S41_E44.txt   # must report 0 ERROR lines; read every warn
python3 tools/build.py show  S41_E44                # compact view to compare against the captions
python3 tools/build.py show  S41_E44 --flagged
```

`build` checks tossup numbering, that every bonus follows a tossup somebody won, that named players are
on the right roster, and that the question words and answer actually appear in the caption lines it
locates for that row. It also prints points per team.

## Compact episode format

```
@EP S41 E59
@ROUND Championship                     Round 1 | Round of 32 | Round of 16 | Round of 8 | Round of 4 | Championship
@TEAMS Webb School of Knoxville | Jefferson County High School     (order the host introduced them)
@R1 Sam, Jackson, Penny, Stephen, James, Ridge                      first names, starters + alternates
@R2 Zach, Elaine, Max, Amy, Eli, Evan, Isabella, Laurel
T12 | Health | question text | answer | Zach:C | Sam:C | note        tossup: buzz | steal | note
B12 | Health | question text | answer | Zach:P10 | note               bonus 12 follows tossup 12
```

* buzz / steal: `Name:C|I|U` (team comes from the roster), `2:I` (team 2, player not named),
  `?:C` (player and team unknown, becomes team `Unknown`), `NB` nobody buzzed, `?` whole tossup unclear.
  Steal is left empty (`| |`) when there was none.
* bonus result: `C`, `I`, `U`, `P10` (partial, points awarded). Optional `2/` bonus team and `Name:`
  in front, e.g. `2/Zach:I`. The bonus team defaults to whoever won the tossup.
* multi-part text and answers: `Part 1: ... // Part 2: ...` (becomes `Part 1: ... | Part 2: ...`).
* note: `!` prefix = needs review (flagged, with caption excerpt); `.` prefix = informational only.
* rows are written in transcript order (tossup, its bonus, next tossup...).

## Conventions (copied from the S42 sheet)

* `Episode` is `S41 E59`; `Matchup` is `Team A vs Team B`; names are first names only.
* `Result` / `Steal Result` / `Outcome` use `Correct`, `Incorrect`, `Partial`, `No Buzz`, `Missed`, `Unclear`.
* Tossup correct = 10 points. Bonus correct = 20, two-part partial = 10, "name four" bonuses = 5 per item.
* Unclear tossup: Points 0, Points To `None given`. Unclear bonus: Points blank, Points To = bonus team.
* Unknown winning team: Team and Points To are `Unknown`.
* `Category` is what the host announces ("math visual" = Math; plain "visual bonus" = Visual);
  `Subject Area` comes from the category table in `tools/build.py` (taken from S42).
* Question text is cleaned up (punctuation, obvious caption mishearings) but never invented: anything
  lost or garbled stays as `[unclear]` and the row is flagged.

## Reading the captions

* There are no speaker labels. The host says the player's first name, then the answer, then a verdict.
* A wrong answer is followed by "chance to steal <team>" (captions: "no chance", "chances do a web",
  "steals").
* "plus up", "pass up", "the throne" = "toss up". "No points on the bonus" = 0, "right for 20" = 20,
  "ten points on the bonus" = partial.
* Player names are often misheard (for example Zach shows up as Zachary / Jacques / Jack / Zach).
  Bonus announcements ("bonus for Jefferson County") pin down the winning team when the name is garbled.
* A buzz mid-question cuts the text off; the host often finishes reading it for the steal.
* Alternates can play in the second half. When time runs out a tossup can have no bonus.
