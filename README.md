# voiceprint

Train a small model on a little of your writing, then draft in your voice — from the terminal, or
from inside any agent that speaks MCP.

```
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

Everything runs in **your own Modal account**. There is no service behind this, no signup, no
account with us, nothing to pay us for. Your writing stays on your machine; the chunks it derives
go to your GPU container and nowhere else.

## Why it works

A LoRA adapter trained on ~1–2k words of your prose, applied to a **base** model — not an instruct
model — and prompted as a plain document rather than a chat turn. Two details carry the result:

- **Never a chat template.** The same base model given the same brief as a chat instruction is
  caught by AI detectors 100% of the time. Formatted as a document, it reads human.
- **min-p sampling at high temperature.** Low temperature collapses the variance that makes prose
  sound like a person. Top-p is the worst of the three options.

More data doesn't help. The curve is flat above ~700 words: the base model already knows how to
write, and the adapter only installs *how you sound*.

## The honest boundary

The high-variance sampling that makes this read human also makes it unreliable on specifics. **It
will invent URLs, dates, names and numbers.** That's not a bug to be patched — it's the same knob.

Put every fact you care about into the notes, and check the specifics before you publish. This is a
first-draft engine in your voice. You keep it honest.

## Setup

Not on PyPI yet. For now:

```sh
git clone https://github.com/samzliu/voice-writer && cd voice-writer
uv venv && uv pip install -e .        # or: python -m venv .venv && pip install -e .
```

Then, once:

```sh
modal token new       # free Modal account, no card needed to start
voiceprint deploy     # builds two GPU images into your workspace — ~4 min the first time
voiceprint check      # confirms the account, the deployment, and your voices
```

`deploy` is a real step, not ceremony: it's what keeps a container warm between calls, so your
second draft doesn't wait on a cold 14B load.

**What the first run actually costs you in time**, measured rather than estimated:

| | |
|---|---|
| `voiceprint deploy` | ~4 min, once ever (builds two GPU images) |
| `voiceprint train` | ~6 min on an A100 |
| first `write` after idle | **364 s** — container start, then 28 GB of weights into the GPU |
| every `write` after that | **3 s** |

Training downloads the base model into a volume that serving shares, so writing never re-downloads
it — the cold start is the engine coming up, not a download. Containers sleep after 10 minutes
idle, so the first draft of a session pays it and the rest of the session doesn't. Budget about 15
minutes from clone to first draft.

## Train

```sh
voiceprint train ~/my-writing --name me     # a folder of .md/.txt you wrote
voiceprint train post.md --name me          # or one file
```

- **~1–2k words is enough.** Below 300 it refuses; below 700 it warns.
- Prose *you* wrote. Not transcripts, not things you co-edited, not your company's blog voice.
- Code blocks, headings, tables, quotes and bulleted outlines are stripped — a notes app is half
  thinking-out-loud, and training on fragments gets you a model that writes in fragments.
- **If you want good short-form, feed it short-form.** `--length short` is a trained control, so
  it's only as good as the number of genuinely short pieces in your corpus. A folder of essays
  teaches it essays.

Training is spawned, not held open on a connection, so closing your laptop can't throw away a GPU
job you paid for:

```sh
voiceprint resume            # pick the most recent run back up
```

## Write

The same command covers a fresh section, a continuation, and the next section of something long —
because a body prefix is just a partly-filled document.

```sh
# from a brief
voiceprint write "the wedge is trust, not features" "our users are ops leads"

# continue what you started (the strongest mode — your own tokens set the voice)
voiceprint write --continue-from draft.md

# next section, aware of the last one
voiceprint write --notes-file section3.md --continue-from section2.md

# short things sound different from essays, so ask for short
voiceprint write --length short "decline the intro politely" "offer to reconnect in March"

# say this in my voice; code and headings pass through untouched
pbpaste | voiceprint rewrite
```

Useful flags: `--all` shows all eight candidates with scores, `--candidates N` changes how many,
`--temp` is the polish-vs-variance dial (1.2 cleaner, 1.8 more human and more glitchy), `--voice`
picks between voices, `--scorer pangram` swaps the ranker if you have a key.

## Many voices, many models

Train as many voices as you like — your own, your newsletter's, a client's you write for:

```sh
voiceprint voices              # list them; * marks the default
voiceprint use work            # set the default for bare commands
voiceprint write --voice work "..."
voiceprint delete old-voice    # forget it, and drop its adapter from your volume
```

Any Hugging Face **base** model works as the foundation:

```sh
voiceprint models                                   # presets
voiceprint train ~/writing --name me --model qwen7b
voiceprint train ~/writing --name me --model someone/Their-Base-7B
```

| preset | model | |
|---|---|---|
| `qwen14b` | Qwen/Qwen2.5-14B | default; the size the technique was validated at |
| `qwen7b` | Qwen/Qwen2.5-7B | 0.541 style / 1.000 novelty vs 14b's 0.548 — half the size, no real loss |

Two presets, because those are the two that have been trained and measured. Any other Hugging Face
base model works by id; it just hasn't been tried here, and a preset nobody has run is a
recommendation you can't stand behind.

Each base model gets its own warm container, so voices sharing a base share one loaded model and
cost nothing extra. **Instruct and chat models are refused** — they already have a voice, and it
isn't yours. Everything runs on an A100-80GB, which fits any of this comfortably; a base too big
for 80 GB means editing `TRAIN_GPU`/`SERVE_GPU` in `modal_app.py` and redeploying.

## Use it from an agent

This is the surface that matters. The model is a *voice*, not a writer — it can't plan, research,
or keep facts straight. An agent that can do those things drives it:

```sh
claude mcp add voiceprint -- /full/path/to/.venv/bin/voiceprint mcp
cp SKILL.md ~/.claude/skills/voiceprint/SKILL.md      # so it knows how to drive it
```

(`voiceprint check` prints the exact `claude mcp add` line for your install.)

Then ask your agent to write something. It picks one of three workflows — continue what you have,
outline first, or interview you until it knows what you actually think — and calls the voice model
section by section. The interview workflow is also how facts get in: things you said out loud go
into the notes, where the model is conditioned on them instead of inventing them.

## Is it working?

```sh
$ voiceprint eval me
voice: me  (5 drafts continuing held-out passages)
  stylometry   0.548   (your own unseen writing: 0.476)
  novelty      1.000   (1.000 = nothing lifted from the training text)
```

`eval` continues passages the adapter never saw during training and asks three questions: does it
sound like you, is it just reciting your corpus, and how does that compare to a real sample of your
own unseen writing. Novelty below 0.95 means it memorized and the run is bad.

Those are real numbers from a real 8.8k-word corpus, with a caveat worth stating: best-of-N
*selects* for the style score, so scoring above your own baseline means "picked from eight tries",
not "more you than you are". Novelty is the number to actually trust.

The defaults were set by measuring. At 8 epochs the training loss reached 0.000 and the adapter
began ignoring its input on rewrites — handing back corpus-flavoured prose instead of your text in
your voice. At 3, novelty went to 1.000, the style score went *up*, and rewrites started preserving
content.

## What it costs

| | |
|---|---|
| Train a voice | ~6 minutes of one A100, once per voice |
| Store an adapter | ~270 MB in your Modal volume |
| A draft | 3 s warm; 364 s if the container had gone to sleep |

Containers shut down after 10 minutes idle, so a writing session is cheap and leaving it alone
costs nothing. Nothing is charged by us — you're paying Modal for your own GPU time.

## When something's wrong

| symptom | what's happening |
|---|---|
| `voiceprint isn't deployed to your Modal workspace yet` | run `voiceprint deploy` |
| first `write` hangs for minutes | cold container downloading the base model; it's warm afterwards |
| code changes don't take effect after `deploy` | a warm container is still on the old code — `modal app stop voiceprint --yes`, then deploy again |
| `several voices exist` | pass `--voice`, or set one with `voiceprint use <name>` |
| `N words of usable prose` when your files look full | outlines, headings, code and tables don't count — only paragraphs |
| training died with a network error | it didn't; run `voiceprint resume` |

## Development

```sh
uv pip install -e ".[dev]"
pytest                       # 46 tests, no GPU or network needed
```

The load-bearing part is `voiceprint/scaffold.py` — the document format and the sampler settings.
`tests/test_scaffold.py` asserts the prompt a training pair is built from is byte-identical to the
prompt generation sends; if those drift, output quietly degrades into ordinary AI prose with
nothing visibly broken.

## Please don't

Clone your own voice, or one you have explicit permission to use. Not someone else's, not for
assignments you're submitting as your own work, not for reviews or accounts pretending to be
people. See [POLICY.md](POLICY.md).

MIT licensed.
