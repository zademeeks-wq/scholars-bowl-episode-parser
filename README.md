# Scholars' Bowl episode parser

Turns the auto-generated caption transcripts of *Tennessee Scholars' Bowl* (seasons 41 and 40)
into rows in the same format as the Season 42 `Questions` sheet: the 19 original columns plus
three review columns (`Needs Review`, `Review Notes`, `Transcript Excerpt`).

```
data/episodes/S41_E59.txt   compact hand-written source for one episode (the checked work)
data/csv/S41_E59.csv        generated rows for that episode
tools/build.py              expands and checks episode files
data/transcripts/           (git-ignored) season_40.txt / season_41.txt as supplied
```

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
