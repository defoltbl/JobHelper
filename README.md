# JobHelper

A desktop assistant for a job search, for macOS. Five agents find postings, score them against
your CV, write an adapted CV and a cover letter for the good ones, and track what you applied to
and what companies answered. A sixth, the assistant, fills in application forms in your own
browser and does things in the app after your yes. It runs on **your Claude subscription** – no
API key, no per-token bill – and your data stays on your Mac, encrypted.

![Tests](https://github.com/defoltbl/JobHelper/actions/workflows/tests.yml/badge.svg)
![Platform](https://img.shields.io/badge/platform-macOS-000000?logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-Qt%20Quick%20(PySide6)-41CD52?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-yellow)

![The main window](docs/img/02_main.png)

## Highlights

- **Never acts in your name.** It does not apply or send anything, and reads the mailbox read-only.
- **Never claims what your CV does not show.** Every CV, letter and form answer the model writes is
  checked against your own CV in plain code before it is saved.
- **Search and scoring you can read.** Czech boards, LinkedIn, company career sites and remote
  boards; each posting gets a 0–100 score with the reason in words.
- **Fills application forms** in Chrome, Brave, Edge, Opera or Safari – empty fields only, never
  Submit.
- **Private by design.** AES-256-GCM encrypted data, keys in the macOS Keychain, signed rule files.
- **A real Mac app** with a desktop widget and a weekly run with the window closed.
- **2,000+ offline tests**, run on every core here and by GitHub Actions on every push.

## Quick start

You need macOS, Python 3.14 and the Claude Code program signed in with a Claude subscription
(LibreOffice is optional, for PDFs).

> **Do not set `ANTHROPIC_API_KEY`.** Leaving it unset is what makes the app use the subscription.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements.lock
claude auth login             # once: sign in with your Claude subscription
python app_qt.py
```

The welcome card checks the sign-in, lets you choose your CV and connects your mailbox. To build
`JobHelper.app` for the Applications folder, see
[Build JobHelper.app](docs/CODE.md#build-jobhelperapp).

## Testing

```bash
python -m pyflakes jobhelper tests scripts app_qt.py run.py status.py
python -m pytest
```

The tests run offline in temporary folders and never touch real data, the Keychain, Claude, a
mailbox or a browser. GitHub Actions runs the same two commands on a Mac after every push.

## Documentation

| Document | What is in it |
|---|---|
| [User guide](docs/GUIDE.md) ([PDF](docs/GUIDE.pdf)) | Every screen, step by step, with pictures – including the [assistant](docs/GUIDE.md#9-fill-in-an-application-form) and [data protection](docs/GUIDE.md#19-protect-your-data) |
| [Technical documentation](docs/CODE.md) ([PDF](docs/CODE.pdf)) | [Tech stack](docs/CODE.md#2-know-the-tech-stack), [install and run](docs/CODE.md#3-install-the-app), [code structure with diagrams](docs/CODE.md#6-understand-the-structure-of-the-code), [tests](docs/CODE.md#8-test-a-change) |
| [Engineering notes and known limits](docs/NOTES.md) | The decisions behind the design, and what the app cannot do yet |
| [Command reference](COMMANDS.md) | Every command-line command and option |
| [Handbook](HANDBOOK.md) | The rules the app is built by and what is left to do |
| [AGENTS.md](AGENTS.md) | Instructions for AI coding agents: commands and the rules they must keep |
| [Changelog](CHANGELOG.md) | What changed, day by day |

Before you publish a fork, run `python scripts/push_check.py --install-hook` once: it stops a push
that would publish a personal detail, a secret or the data folder
([details](docs/CODE.md#the-check-before-a-push)).

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md): free to read, run, change and share for any
noncommercial purpose; selling it or using it to make money needs the author's written
permission. The libraries keep their own licences. `JobHelper.app` is not published here, because a
built app contains Qt and Anthropic's Claude Code program under their own terms: build it yourself.

## Author

**Andrii Maksymenko**, Junior Software Developer, Prague.

- Case study: [andrii-maksymenko.com/projects/jobhelper](https://andrii-maksymenko.com/projects/jobhelper/)
- Portfolio: [andrii-maksymenko.com](https://andrii-maksymenko.com)
- LinkedIn: [linkedin.com/in/andrii-maksymenko-83628932a](https://www.linkedin.com/in/andrii-maksymenko-83628932a)
- GitHub: [github.com/defoltbl](https://github.com/defoltbl)
