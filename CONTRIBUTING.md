# Contributing

*[Version française](CONTRIBUTING.fr.md)*

Thanks for considering a contribution! This is a small personal project, so
the bar is low but a few things help keep it maintainable.

## Project scope

This bridge exists to translate a source of TV channels into the exact HTTP
shape [NetStream](https://github.com/GrapheneCt/NetStream) on PS Vita can
browse and play. It is **not** a general-purpose media server, and it is
**not** meant to redistribute licensed content — see the disclaimer in
`README.md`.

## Getting set up

```bash
git clone https://github.com/TheRealBerete/psvita-stream-bridge.git
cd psvita-stream-bridge
pip install -r requirements.txt
python build_channels.py
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Read `docs/ARCHITECTURE.md` before touching `app.py` — most of its code
exists to work around a specific, verified constraint of NetStream's
client. If a change looks unnecessarily convoluted, check that file first;
there's probably a reason documented right above the code.

## Making changes

- Keep `data/channels.json`'s shape (`id`, `name`, `country`, `categories`,
  `url`) stable — anything that consumes this bridge as a template for a
  different data source relies on it staying simple.
- If you touch anything related to NetStream's navigation model (folder
  hrefs, file extensions, HTML output), re-verify against the constraints
  table in `docs/ARCHITECTURE.md`, and test against a real device if you
  can — this project has already shipped subtle bugs that only showed up
  on actual hardware (see `CHANGELOG.md`).
- There's no test suite yet. For now, manually exercise the endpoints you
  changed with `curl` (see the examples in the READMEs) before opening a
  pull request, and mention what you tested in the PR description.

## Reporting a broken channel or a NetStream quirk

Open an issue with:
- the exact URL you hit (`/resolve/...`, `/status`, etc.),
- what NetStream (or `curl`) shows,
- whatever `/_status` reports for that channel, if relevant.

## Pull requests

Small, focused PRs are easier to review than large ones. If you're planning
a bigger change (a new data source backend, a different navigation scheme),
open an issue first to discuss the approach.
