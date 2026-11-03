# NotePDF

Add highlights and comments to a PDF from a config file, with no manual selection. NotePDF can
also generate that config from the revision markers in your LaTeX source, such as
`{\color{revcolor} ...}`. That makes it easy to hand reviewers a PDF where every change is
highlighted and explained.

The annotations are the same kind Edge and Acrobat create when you select text and click
*Highlight*: standard PDF `/Highlight` (or underline/strikeout/squiggly) annotations with one quad
per text line, the comment in `/Contents`, an author, and a pre-rendered appearance stream. That's
why they show up in Acrobat, Edge, Firefox and most other readers. Built on
[PyMuPDF](https://pymupdf.readthedocs.io/).

## Install

```bash
uv sync --extra fuzzy --extra gui      # or: pip install -e ".[fuzzy,gui]"
```

Both extras are optional:
- `fuzzy` (rapidfuzz) lets NotePDF recover when the TeX source and the PDF differ slightly.
- `gui` (FastAPI, uvicorn) is for the [graphical interface](#gui).

## GUI

`notepdf gui` opens NotePDF in your browser (full guide: [docs/GUI.md](docs/GUI.md)). Under WSL that's your Windows browser. You can also
pass a file to open: `notepdf gui paper.pdf`.

- **Select text to highlight it, as in Edge or Acrobat.** Drag across words (or double-click one) and
  choose *Highlight*, *Underline*, *Strikeout* or *Comment…* in the toolbar that appears. The entry
  targets exactly that occurrence, adding `pages`/`occurrence` only when the text appears more than
  once.
- **See every highlight before saving.** The PDF shows where each entry lands, and the list on the
  left shows whether it was found. Every change is matched again right away. Hover a highlight to
  read its comment; click it to edit it.
- **Edit an entry** on the right: text or regex, comment, color, type, opacity, pages, occurrence,
  matching mode and the other [config options](#config-reference). The *Document* tab holds the
  defaults and the output file.
- **Import from LaTeX.** Choose the main `.tex`, the markers (`revcolor`, `\rev`, …) and their
  colors. The marked passages become entries with their `%@note` comments and `file.tex:line`
  sources. *Re-import* refreshes them after you edit the paper and keeps entries you added by hand.
  Skipped equations are listed under *Notes*.
- **Save PDF** writes the annotations. *Save config* writes a YAML file that `notepdf apply` can use too.
- English and 简体中文; light, dark or system theme (⚙).

The interface is built once from `app/` (needs Node.js):

```bash
cd app && npm install && npm run build      # writes src/notepdf/gui/dist
```

The server listens on 127.0.0.1:8766 only and rejects requests for other host names. It can read
and write any file you can, so don't bind it to other addresses with `--host`. Preferences and
recent files are kept in `~/.config/notepdf/gui.json`.

### Desktop app

The same interface also runs as a desktop app, a [Tauri](https://tauri.app) shell in
`app/src-tauri`, with native open and save dialogs and drag-and-drop of PDFs, configs and `.tex`
files. It starts its own backend (`.venv/bin/python -m notepdf gui --app` on a free port) and stops
it when the window closes. Under WSL the window shows through WSLg.

Build and install the `.deb` (needs Rust; the build also builds the interface):

```bash
cd app
npm install
PATH=~/.cargo/bin:$PATH npm run tauri build -- --bundles deb
sudo apt install ./src-tauri/target/release/bundle/deb/NotePDF_0.1.0_amd64.deb
```

Start it from the applications menu (*NotePDF*) or with `notepdf-app [file]`. The binary isn't
called `notepdf`, so it doesn't clash with the command-line tool. The app belongs to the NotePDF
folder it was built from and runs that folder's `.venv`. Set
`NOTEPDF_HOME=/path/to/NotePDF` to point it somewhere else. If it can't start, the backend's
output is in `app-backend.log` in that folder.

If `tauri build` stops with *Too many open files*, the system is out of inotify instances (editors
and other tools use them). Raise the limit with `sudo sysctl fs.inotify.max_user_instances=512` and
build again.

For UI development, run `notepdf gui --no-browser` and `cd app && npm run dev`, then open
http://localhost:1421. Changes reload as you edit.

## Quick start: highlights from a config file

```yaml
# highlights.yaml
input: paper.pdf
defaults:
  author: Taylor
annotations:
  - text: "significantly outperforms the baseline on every benchmark"
    comment: "Reviewer 2, point 3"
    color: "#A5D6A7"
  - text: "our method"
    pages: 2
    occurrence: all
```

```bash
notepdf apply highlights.yaml          # writes paper.annotated.pdf
notepdf list paper.annotated.pdf       # check what was added
```

You don't need to say where the text is. NotePDF searches the whole document, across line breaks,
hyphenation and columns. `pages` is optional and only narrows the search. See
[examples/highlights.yaml](examples/highlights.yaml) for every option. To try it, run
`python examples/make_sample_pdf.py && notepdf apply examples/highlights.yaml`.

## Quick start: highlights from LaTeX revision markers

Mark revised text as you normally would, and add a `%@note:` comment where you want an annotation
comment. LaTeX ignores it, so the PDF doesn't change:

```latex
\definecolor{revcolor}{RGB}{0,0,255}
\newcommand{\rev}[1]{{\color{revcolor}#1}}

{\color{revcolor} %@note: R1.1 clarified the motivation
We propose \ours, which is \emph{much} faster than prior work~\cite{a,b}.}

%@note: R2.3 new experiment
\rev{We further evaluate on three new datasets.}
```

Then, with the compiled PDF:

```bash
# one step: find the markers and annotate the PDF
notepdf tex paper.tex paper.pdf                       # -> paper.annotated.pdf

# or two steps: generate an editable config, review it, then apply it
notepdf tex2config paper.tex --pdf paper.pdf -o revisions.yaml
notepdf apply revisions.yaml
```

By default the marker is `revcolor`. Use `--color NAME`, `--macro NAME` or `--env NAME`
(repeatable) or a config file (`-c`, see [examples/tex_config.yaml](examples/tex_config.yaml)) for
other markers.

### What NotePDF recognizes in TeX

| Marker | Example | Config |
|---|---|---|
| Color group | `{\color{revcolor} ...}`, `\begingroup\color{revcolor}...\endgroup` | `color: revcolor` |
| Color switch | `\color{revcolor} ... \color{black}` (until the group or environment ends) | `color: revcolor` |
| Colored argument | `\textcolor{revcolor}{...}` | `color: revcolor` |
| Macro | `\rev{...}`, `\rev[x]{...}` | `macro: rev`, or detected automatically when its definition uses a marker color |
| Environment | `\begin{revised} ... \end{revised}` | `env: revised` |

**Comments** come from `%@note:` lines. A note belongs to a marker if it's inside the marker, or on
the line just above the marker's line. Consecutive `%@note:` lines join into one comment. A marker
without a note gets its spec's `comment` template if you set one (placeholders: `{n}`, `{file}`,
`{line}`, `{marker}`); otherwise it gets no comment.

**How a marked block becomes searchable text:**
- `\input`/`\include` are followed.
- `%` comments, `\iffalse…\fi` and `comment` environments are ignored.
- Text commands keep their text: `\emph{x}` becomes `x`.
- Zero-argument macros from the preamble are expanded (`\ours` becomes `OurNet`). Add others under
  `tex.replacements`.
- Citations, references, URLs and inline math become `{{gap}}` placeholders, because their
  rendered form can't be predicted.
- Paragraphs, list items and headings become separate entries. A comment goes on the first
  highlight of its block.
- Captions and footnotes become their own entries.
- Display equations, tables and figure bodies aren't highlighted. They're listed in the report so
  you can handle them yourself.

**Matching TeX entries to the PDF:**
- Entries are searched in source order, which resolves repeated phrases.
- If the PDF still shows the marker color, characters in that color are preferred. A clean build
  with the color set to black works too.
- If a block isn't found as a whole, NotePDF tries fuzzy matching (needs the `fuzzy` extra), then
  matches it sentence by sentence and merges the adjacent pieces.

## Config reference

Top level:

| Key | Default | Meaning |
|---|---|---|
| `input` | – | PDF to annotate (relative to the config file). `-i` overrides it. |
| `output` | `<input>.annotated.pdf` | Where to write. If it's the same as `input`, the file is updated incrementally. |
| `password` | – | For encrypted PDFs. |
| `remove_existing` | `true` | Remove annotations from earlier NotePDF runs first, so reruns don't duplicate them. Other annotations are kept. |
| `defaults` | – | Style for every entry (see below). |
| `annotations` | `[]` | Entries to add. |
| `tex` | – | Generate more entries from LaTeX: `main`, `markers`, `detect_macros`, `replacements`, `include_captions`, `include_footnotes`, `min_segment_chars`. |

Each entry has `text` (may contain `{{gap}}` / `{{gap:N}}`) or `regex`, plus optionally:

| Key | Meaning |
|---|---|
| `comment` | Comment text (`/Contents`). |
| `pages` | `3`, `[3, 5]`, `"3-5"`, `"7-"` (1-based). Default: all pages. |
| `context_before` / `context_after` | Text that must appear just before or after the match. |
| `text_color` | Prefer matches rendered in this text color. |
| `group` | Entries in a group share one comment. |
| `required` | `false`: a missing entry doesn't fail `--strict`. |

Style keys, set in `defaults` or on any entry or TeX marker:

| Key | Default | Values |
|---|---|---|
| `type` | `highlight` | `highlight`, `underline`, `strikeout`, `squiggly` |
| `color` | `yellow` | `"#RRGGBB"`, a name (yellow, green, blue, cyan, pink, red, orange, purple, gray), or `[r, g, b]` |
| `opacity` | `0.4` | 0–1 |
| `author`, `subject` | –, `NotePDF` | `/T`, `/Subj` |
| `match` | `normalized` | `normalized`: letters and digits only, ignoring case, punctuation, hyphenation, line breaks and accents. `exact`: punctuation counts. `fuzzy`: approximate. |
| `case_sensitive`, `whole_word` | `false` | |
| `occurrence` | `first` | `first`, `all`, `N`, `[N, M]` (1-based) |
| `popup` | `closed` | `closed`, `open`, `none` (the comment's popup window) |
| `sticky_note` | `false` | Also add a margin note icon. Use it for viewers that don't show highlight comments. |
| `continuation_comment` | `none` | For a match split across pages: `none`, `same`, or any text, e.g. `"(continued)"` |
| `sequential` | `false` | Search forward from the previous match first. |
| `fuzzy_fallback`, `split_fallback` | `false` | Recovery strategies (on by default for TeX entries). `fuzzy_threshold` defaults to 90. |

## Commands

```
notepdf apply CONFIG [-i PDF] [-o PDF] [--dry-run] [--strict] [--report out.json] [-v]
notepdf tex MAIN.tex PDF [-o PDF] [-c CONFIG] [--color/--macro/--env NAME] [--highlight COLOR] [--save-config FILE]
notepdf tex2config MAIN.tex -o FILE.yaml [--pdf PDF] [-c CONFIG] [--color/--macro/--env NAME] [--highlight COLOR]
notepdf list PDF [--json] [--all]
notepdf clear PDF [-o PDF]
notepdf gui [PDF | CONFIG | MAIN.tex] [--port 8766] [--no-browser]
```

`--strict` exits with 1 when a required entry isn't found, so you can use NotePDF in a build
script. Configuration errors exit with 2.

From Python:

```python
from notepdf import Config, apply
report = apply(Config.load("highlights.yaml"))
print([r.entry.label for r in report.missing])
```

## Viewer notes

- **Acrobat / Acrobat Reader, Edge, Firefox:** highlights render, and comments appear on hover or
  click and in the comments pane.
- **Chrome's built-in viewer:** draws the highlights but has no comment UI. Use
  `sticky_note: true` if Chrome readers need to see the comments.
- Annotations are tagged with `/NM (notepdf-…)`. That's how reruns and `notepdf clear` find them
  without touching anyone else's annotations.

## Limitations

- Scanned PDFs have no text layer. Run OCR first.
- Text produced by complex macros may not match the source. Use `tex.replacements`, or edit the
  generated config.
- Display equations and figure contents aren't highlighted. The report lists them.

## Development

```bash
uv run pytest
```

The tests build their PDFs with PyMuPDF, so no LaTeX is needed. `tests/test_e2e_tex.py` compiles
`examples/paper` and runs only if `pdflatex` is on `PATH`.

## License

AGPL-3.0-or-later, because PyMuPDF is AGPL-licensed.
