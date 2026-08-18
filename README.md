# voiceprint

Train a small adapter on your writing, then use it to draft from the command line or an MCP client.

```console
$ voiceprint train ~/writing --name me
8793 words, 40 chunks from ~/writing
training 'me' on Qwen/Qwen2.5-14B — a few minutes. job fc-01M06S0G6DENM38AZ295W72W5K
safe to interrupt; pick it back up with:  voiceprint resume fc-01M06S0G6DENM38AZ295W72W5K
..........
done: 102 pairs from 8793 words -> /voices/me

$ voiceprint write --length short "decline the intro politely" "offer to reconnect in March"
Nope, my focus this month is on writing that book and finishing up other open loops.
Can I catch up with you in March?
```

voiceprint runs in your own [Modal](https://modal.com/) account. Source text stays local; derived
training chunks are sent to your Modal GPU container. There is no hosted voiceprint service or
separate account.

## How it works

voiceprint trains a LoRA adapter on a Hugging Face base model. It formats prompts as plain documents
instead of chat messages and generates several candidates using high-temperature min-p sampling.
The CLI ranks those candidates by similarity to the training corpus.

The approach was tested with roughly 1,000–2,000 words. More source text did not improve the
measured style score after about 700 words in the test corpus.

High-variance sampling also makes factual errors more likely. Put important names, dates, numbers,
and URLs in the notes, then verify them before publishing. Treat the output as a first draft.

## Install

voiceprint is not on PyPI yet:

```sh
git clone https://github.com/samzliu/voice-writer
cd voice-writer
uv venv
uv pip install -e .
```

You can use `python -m venv .venv && pip install -e .` instead of `uv`.

Set up Modal and deploy the GPU app once:

```sh
modal token new
voiceprint deploy
voiceprint check
```

`deploy` builds the training and serving images in your Modal workspace. A measured first run took
about 4 minutes to deploy, 6 minutes to train on an A100, and 364 seconds for the first write after
idle. Warm writes took about 3 seconds. Serving containers stop after 10 minutes of inactivity.

## Train a voice

Pass a Markdown or text file, or a directory containing them:

```sh
voiceprint train ~/my-writing --name me
voiceprint train post.md --name me
```

Use prose you wrote yourself. Headings, code blocks, tables, quotes, and bulleted outlines are
removed during preparation. The command rejects corpora below 300 usable words and warns below 700.

Corpus shape matters. If you want short-form output, include real short-form samples; the
`--length short` option cannot learn that style from a directory of essays.

Training runs as a remote job. If the terminal closes, reconnect to the latest unfinished job with:

```sh
voiceprint resume
```

## Write and rewrite

```sh
# Draft from notes
voiceprint write "the wedge is trust, not features" "our users are ops leads"

# Continue an existing draft
voiceprint write --continue-from draft.md

# Draft the next section using notes and the previous section
voiceprint write --notes-file section3.md --continue-from section2.md

# Request short output
voiceprint write --length short "decline the intro politely" "offer to reconnect in March"

# Rewrite stdin while preserving code and headings
pbpaste | voiceprint rewrite
```

Useful options:

- `--all` prints all candidates and their scores.
- `--candidates N` controls how many candidates to generate.
- `--temp` controls sampling variance. Lower values are more conservative; higher values vary more
  and produce more errors.
- `--voice NAME` selects a trained voice.
- `--scorer pangram` uses the Pangram ranker and requires `PANGRAM_API_KEY`.

## Manage voices and models

```sh
voiceprint voices
voiceprint use work
voiceprint write --voice work "..."
voiceprint delete old-voice
```

Two model presets are included:

| Preset | Model | Notes |
| --- | --- | --- |
| `qwen14b` | `Qwen/Qwen2.5-14B` | Default; used for the main evaluation |
| `qwen7b` | `Qwen/Qwen2.5-7B` | Smaller; measured 0.541 style and 1.000 novelty versus 0.548 and 1.000 for 14B |

List them with `voiceprint models`. You can also pass another Hugging Face base-model ID:

```sh
voiceprint train ~/writing --name me --model qwen7b
voiceprint train ~/writing --name me --model someone/Their-Base-7B
```

Instruct and chat models are rejected. Each base model gets its own serving container; voices using
the same base model share that container. Training and serving default to an A100-80GB. To use a
model that does not fit, change `TRAIN_GPU` and `SERVE_GPU` in `voiceprint/modal_app.py`, then
redeploy.

## MCP setup

An MCP-capable agent can use voiceprint for drafting while it handles planning, research, and fact
checking.

```sh
claude mcp add voiceprint -- /full/path/to/.venv/bin/voiceprint mcp
cp SKILL.md ~/.claude/skills/voiceprint/SKILL.md
```

`voiceprint check` prints the MCP command for the current installation.

## Evaluate a voice

```console
$ voiceprint eval me
voice: me  (5 drafts continuing held-out passages)
  stylometry   0.548   (your own unseen writing: 0.476)
  novelty      1.000   (1.000 = nothing lifted from the training text)
```

`eval` continues passages held out during training. The style score measures similarity to the
corpus; novelty checks whether output repeats the training text. A novelty score below 0.95 suggests
memorization.

The example above comes from an 8,800-word corpus. Because voiceprint selects the best of several
candidates using the style score, that score should not be compared directly with a single human
sample. The training default is three epochs: in testing, eight epochs reduced novelty and made
rewrites less faithful to their input.

## Cost and runtime

voiceprint does not charge for usage. Modal bills your account for GPU time and storage.

| Operation | Measured result |
| --- | --- |
| Train a voice | About 6 minutes on one A100 |
| Store an adapter | About 270 MB |
| Generate a warm draft | About 3 seconds |
| First draft after idle | 364 seconds in the measured run |

Training stores base-model weights in a shared Modal volume, so serving does not download them
again. The long first request after idle is container startup and model loading.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `voiceprint isn't deployed to your Modal workspace yet` | Run `voiceprint deploy`. |
| The first `write` takes several minutes | Wait for the serving container to start and load the model. |
| Changes do not appear after deployment | Run `modal app stop voiceprint --yes`, then deploy again. |
| `several voices exist` | Pass `--voice` or run `voiceprint use <name>`. |
| Files contain text but training reports few usable words | Only prose paragraphs count; outlines, headings, code, and tables are removed. |
| Training appears to stop after a network error | Run `voiceprint resume`. |

## Development

```sh
uv pip install -e ".[dev]"
pytest
```

The prompt format and sampling defaults live in `voiceprint/scaffold.py`.
`tests/test_scaffold.py` verifies that training and generation construct prompts the same way.

## Responsible use

Only train on your own voice or a voice you have explicit permission to use. Do not use voiceprint
for impersonation, deceptive accounts or reviews, or work that must be written without assistance.
See [POLICY.md](POLICY.md).

MIT licensed.
