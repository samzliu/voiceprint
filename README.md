# Voiceprint

**A small model that writes like you.** Train it on a few pages of your writing, then draft from
the terminal or any MCP client.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/voiceprint.svg?cacheSeconds=300)](https://pypi.org/project/voiceprint/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/samzliu/voiceprint/blob/main/LICENSE)

[Quickstart](#quickstart) · [Examples](#what-you-can-do) · [MCP](#use-it-from-an-agent) ·
[Evaluation](#evaluate-the-result) · [Issues](https://github.com/samzliu/voiceprint/issues)

<p align="center">
  <img src="https://raw.githubusercontent.com/samzliu/voiceprint/main/.github/assets/voiceprint-demo.svg" alt="Voiceprint terminal demo: train a voice, then draft a short reply" width="100%">
</p>

Voiceprint is built for first drafts: emails, posts, essays, and sections of longer work. It learns
style from your prose while an agent or a set of notes supplies the facts and structure.

If Voiceprint is useful to you, [star the repository](https://github.com/samzliu/voiceprint) so
other writers and developers can find it.

Try it out [here](https://voiceprint-demo.voiceprint-demo.workers.dev). Note it may take a few minutes for to warm up. 

## Why Voiceprint

- **Your voice, not AI slop.** A LoRA adapter learns from prose you already wrote. In one run, Pangram 4.0 classified all ~900 words of an AI generated draft from an adapter trained on a ~9k word corpus as human-written.
- **A small corpus.** About 1,000–2,000 words is enough.
- **CLI and MCP.** Use it directly or let Claude Code, Codex, or another MCP client call it.
- **Runs in your account.** Training and inference run in your own Modal workspace. There is no
  Voiceprint service or separate account.
- **Measurable.** The built-in evaluation checks style similarity and memorization on held-out
  text.

  
![Pangram 4.0 classifying an 888-word original essay as 100% human-written](https://raw.githubusercontent.com/samzliu/voiceprint/main/.github/assets/pangram-human-written-baseline.png)



## Quickstart

### Install with a coding agent

Paste this into Claude Code, Codex, or another coding agent with terminal access:

```text
Set up Voiceprint for me from https://github.com/samzliu/voiceprint.
Read the README and follow its current setup instructions. Install from PyPI,
run voiceprint check, and configure the Voiceprint MCP server for this agent.
Pause if Modal needs me to authenticate. Before training, ask me for the folder
containing my writing and remind me that the corpus should use one consistent voice.
```

The agent can handle installation, deployment, checks, and MCP configuration. You may need to
complete Modal's browser authentication and choose the writing folder to train on.

### Install manually

#### 1. Install

Install Voiceprint with `uv`:

```sh
uv tool install voiceprint
```

Or use `pip install voiceprint` in a Python 3.10 or newer environment.

#### 2. Deploy

Create a [Modal](https://modal.com/) account, then deploy the training and serving images:

```sh
modal token new
voiceprint deploy
voiceprint check
```

#### 3. Train

Train a voice from Markdown or text files:

```sh
voiceprint inspect-corpus ~/my-writing
voiceprint train ~/my-writing --name me
```

#### 4. Write

```sh
voiceprint write "the wedge is trust, not features" "our users are ops leads"
```

The first setup takes roughly 15 minutes in the measured configuration. Training continues as a
remote job if you close the terminal; reconnect with `voiceprint resume`.

## What you can do

### Draft from a brief

Pass each note as a separate argument:

```sh
voiceprint write \
  "the audience is engineering leaders" \
  "the wedge is trust, not features" \
  "end with an invitation to reply"
```

For longer briefs, use a file:

```sh
voiceprint write --notes-file brief.md
```

### Continue a draft

Your existing words give the model both context and a strong style signal:

```sh
voiceprint write --continue-from draft.md
```

To write the next section from new notes:

```sh
voiceprint write --notes-file section3.md --continue-from section2.md
```

### Rewrite existing text

```sh
voiceprint rewrite draft.md
pbpaste | voiceprint rewrite
```

Code blocks and headings pass through unchanged.

### Generate short-form copy

```sh
voiceprint write --length short \
  "decline the intro politely" \
  "offer to reconnect in March"
```

Short-form works best when the training corpus includes short-form writing.

### Choose raw or edited delivery

Voiceprint's raw output preserves the learned voice most faithfully, but it can contain factual or
grammatical errors. An agent using Voiceprint should label that as **raw mode** and leave the prose
untouched.

In **edited mode**, limit changes to false facts, spelling, grammar, broken syntax, and accidental
repetition. Avoid general AI polishing such as smoothing transitions, replacing metaphors,
tightening rhythm, or restructuring paragraphs; those changes can make the result read more like a
generic assistant. A general model may prepare a private correction draft, but `edit_span` or
`revoice` must produce the final user-visible words. Regenerate a bad passage from corrected notes
instead. Even these bounded edits may make the result read more AI-like or change detector results.

You can score the exact final artifact after editing:

```sh
voiceprint score final.md
voiceprint score final.md --scorer pangram  # requires PANGRAM_API_KEY
```


## Use it from an agent

Voiceprint exposes an MCP server so an agent can research and plan while the adapter handles the
prose. For a guided installation, use the [agent setup prompt](#install-with-a-coding-agent). To
register an existing installation with Claude Code manually:

```sh
claude mcp add voiceprint -- /full/path/to/.venv/bin/voiceprint mcp
cp SKILL.md ~/.claude/skills/voiceprint/SKILL.md
```

`voiceprint check` prints the MCP command with the path for your installation.

An agent can use Voiceprint in three ways:

1. Continue text you already started.
2. Turn an outline or brief into a draft.
3. Interview you for the missing ideas and facts, then draft section by section.

The third workflow is useful for factual writing: your answers become notes instead of leaving the
voice model to guess.

For edits, the MCP server also exposes `edit_span` for one exact selection and `revoice` for a
whole provisional draft. Both guarantee that the trained adapter, rather than the planning model,
writes the final returned prose.

## Prepare a good corpus

Use prose you wrote yourself. A directory of `.md` and `.txt` files works well:

```sh
voiceprint train ~/my-writing --name me
voiceprint train post.md --name me
```

The preparation step removes headings, code blocks, tables, quotes, and bulleted outlines. The CLI
rejects fewer than 300 usable words and warns below 700. `voiceprint inspect-corpus` runs the same
check without starting a GPU; it also reports ignored files and removes exact duplicate passages.
The paid hosted workflow uses a stricter 1,000-word gate and recommends at least 2,000 words before
checkout.

Keep the corpus consistent. Use writing with the same voice, audience, and level of formality you
want Voiceprint to reproduce. Mixing personal essays, corporate copy, academic prose, and heavily
edited work gives the adapter conflicting signals.

Choose samples that match what you want to produce. Essays teach essay structure; short emails and
posts teach short-form rhythm. Avoid transcripts, heavily co-edited work, and generic company copy.

## How it works

Voiceprint builds training pairs from your corpus and trains a LoRA adapter on a Hugging Face
instruct model. One rule drives the whole design: **train on human text in the format you generate
in.** Each training pair is a chat turn — the user turn is an instruction, the assistant turn is a
paragraph you actually wrote — and loss falls only on the assistant span. Generation then goes
through the same chat template.

Both halves are load-bearing. An untrained instruct model asked for a paragraph is caught by
detectors every time, because the assistant distribution it was tuned into *is* the fingerprint. An
adapter trained on plain documents but prompted with the chat template fails too, for the mirror
reason: it is being asked at inference for something it never saw. Matching them is the technique,
which is why each voice records the format it was trained in and refuses to be served under the
other one.

At generation time it:

1. Renders the brief and optional draft prefix through the base model's chat template.
2. Draws a small batch of candidates and scores each with an AI detector.
3. Returns the first draft that passes, drawing again only if none did (cap: 6).
4. Ranks by stylometric similarity when more than one candidate passes.

Because a trained adapter usually passes on the first or second candidate, the common case costs
one batch rather than a fixed eight generations.

In tests, the style score flattened after roughly 700 words. The base model already knows how to
write; the adapter is learning the distribution of choices that makes the writing sound like you.

Useful controls:

- `--all` prints every candidate and its score.
- `--candidates N` changes the number of candidates.
- `--temp` controls variance. Lower values are more conservative; higher values vary more and make
  more mistakes.
- `--voice NAME` selects a trained voice.
- `--detector` chooses the gate: `binoculars` (default, self-hosted, free per call), `pangram`
  (requires `PANGRAM_API_KEY`), or `none` to return the first draw ungated.
- `--scorer pangram` uses the Pangram ranker and requires `PANGRAM_API_KEY`.

`write` reports `p_human` and how many candidates it drew on stderr, so piping stdout to a file
still gets clean prose. If nothing clears the detector it returns the closest candidate and says
so. When that happens, change the notes and regenerate — do not edit the prose by hand. Editing
finished output, whether by a human or an AI polish pass, reliably re-triggers detectors on the
whole passage. To change one sentence, use `edit_span`, which has the adapter write the
replacement's final words.

## Evaluate the result

```console
$ voiceprint eval me
voice: me  (5 drafts continuing held-out passages)
  stylometry   0.548   (your own unseen writing: 0.476)
  novelty      1.000   (1.000 = nothing lifted from the training text)
```

`eval` continues passages held out during training. Stylometry measures similarity to the corpus;
novelty checks whether the adapter repeats training text. A novelty score below 0.95 suggests
memorization.

## Models and voices

Manage multiple voices from the CLI:

```sh
voiceprint voices
voiceprint use work
voiceprint write --voice work "..."
voiceprint delete old-voice
```

Two base-model presets:

| Preset | Model | Notes |
| --- | --- | --- |
| `qwen14b` | `Qwen/Qwen2.5-14B-Instruct` | Default; the cheapest base that passes |
| `mistral24b` | `mistralai/Mistral-Small-24B-Instruct-2501` | Better prose, Apache-2.0 |

Use a preset or another Hugging Face instruct-model ID:

```sh
voiceprint train ~/writing --name me --model mistral24b
voiceprint train ~/writing --name me --model someone/Their-Model-7B-Instruct
```

The base must carry a chat template, since the adapter is both trained and served through it.
Training stops immediately if it does not, before any GPU time is spent. Serving is pinned to one
base: a LoRA adapter is a delta on specific weights, so a second base means a second resident
container, not a second adapter. Training and serving default to an A100-80GB and the detector to
an L40S; change `TRAIN_GPU`, `SERVE_GPU` and `DETECTOR_GPU` in `voiceprint/modal_app.py` to use
different hardware.

> **Voices trained before the chat-format change need retraining.** They were trained as plain
> documents on a pretrained base and cannot be served by the instruct engine. `voiceprint voices`
> marks them, and generation refuses them with a retrain hint rather than returning prose that has
> quietly lost the voice.

## Privacy, accuracy, and cost

Source files stay on your machine. Derived training chunks are sent to the GPU container in your
Modal account, and adapters and model weights are stored in your Modal volumes. The project has no
hosted backend.

The sampling settings that preserve variation also increase factual errors. Put names, dates,
numbers, and URLs in the notes, and verify the finished draft. Voiceprint is not a fact checker.

Modal bills your account for GPU time and storage.

| Operation | Measured result |
| --- | --- |
| Deploy the images | About 4 minutes, once |
| Train one voice | About 6 minutes on one A100 |
| Store one adapter | About 270 MB |
| Generate with a warm container | About 3 seconds |
| First generation after idle | 364 seconds in the measured run |

Serving containers stop after 10 minutes of inactivity. Model weights remain in a shared Modal
volume, so a cold start loads them from storage rather than downloading them again.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Voiceprint isn't deployed to your Modal workspace yet` | Run `voiceprint deploy`. |
| The first `write` takes several minutes | Wait for the container to start and load the model. |
| Deployed code looks stale | Run `modal app stop voiceprint --yes`, then deploy again. |
| `several voices exist` | Pass `--voice` or run `voiceprint use <name>`. |
| Training finds little usable prose | Add prose paragraphs; headings, code, tables, and outlines do not count. |
| The terminal disconnected during training | Run `voiceprint resume`. |

If the problem persists, [open an issue](https://github.com/samzliu/voiceprint/issues) with the
command you ran and the full error output.

## Contributing

Issues and pull requests are welcome. For local development:

```sh
uv pip install -e ".[dev]"
pytest
```

The prompt format and sampling defaults live in `voiceprint/scaffold.py`.
`tests/test_scaffold.py` verifies that training and generation build prompts the same way.

Before opening a pull request, run the test suite and explain any behavior or default that changes.
For larger changes, start with an issue so the approach can be discussed first.

## Responsible use

Only train on your own voice or a voice you have explicit permission to use. Do not use Voiceprint
for impersonation, deceptive accounts or reviews, or work that must be written without assistance.
See the [use policy](https://github.com/samzliu/voiceprint/blob/main/POLICY.md).

## License

[MIT](https://github.com/samzliu/voiceprint/blob/main/LICENSE) © Voiceprint contributors
