# voiceprint

Train a small model on a little of your writing, then draft in your voice — from the terminal, or
from inside any agent that speaks MCP.

```
$ voiceprint train ~/writing --name me
8793 words, 40 chunks from ~/writing
training 'me' on 14b — a few minutes. job fc-01M06S0G6DENM38AZ295W72W5K
..........
done: 102 pairs from 8793 words -> /voices/me

$ voiceprint write "agents forget everything between sessions" "memory should be a wiki, not a log"
```

Everything runs in **your own Modal account**. There is no service behind this, no signup, no
account with us, and nothing to pay us for. Your writing stays on your machine; the chunks it
derives go to your GPU container and nowhere else.

## Why it works

A LoRA adapter trained on ~1–2k words of your prose, applied to a base model — not an instruct
model — and prompted as a plain document rather than a chat turn. Two details carry the whole
result:

- **Never a chat template.** The same base model given the same brief as a chat instruction is
  caught by AI detectors 100% of the time. Formatted as a document, it reads human.
- **min-p sampling at high temperature.** Low temperature collapses the variance that makes prose
  sound like a person. Top-p is the worst of the three options.

More data doesn't help. The curve is flat above ~700 words: the base model already knows how to
write, and the adapter only installs *how you sound*.

## The honest boundary

The high-variance sampling that makes this read human also makes it unreliable on specifics. **It
will invent URLs, dates, names and numbers.** That is not a bug to be patched — it's the same knob.

So: put every fact you care about into the notes, and check the specifics before you publish. This
is a first-draft engine in your voice. You keep it honest.

## Install

```sh
pip install voiceprint      # or: uvx voiceprint
modal token new             # once — a free Modal account
voiceprint deploy           # deploys the GPU app into your workspace
```

`deploy` is a real step, not ceremony: it's what keeps a container warm between calls, so your
second draft doesn't wait on a cold 14B load.

## Train

```sh
voiceprint train ~/my-writing --name me     # a folder of .md/.txt you wrote
voiceprint train post.md --name me          # or one file
```

- **~1–2k words is enough.** Below 300 it refuses; below 700 it warns.
- Prose *you* wrote. Not transcripts, not things you co-edited, not your company's blog voice.
- Code blocks, headings, tables, quotes and bulleted outlines are stripped — a notes app is half
  thinking-out-loud, and training on fragments gets you a model that writes in fragments.
- **If you want good short-form, feed it short-form.** `--length short` is a trained control, so it
  is only as good as the number of genuinely short pieces in your corpus. A folder of essays
  teaches it essays.
- `--model 7b` for a cheaper, faster, less-tested tier.

Training is spawned, not held open on a connection, so closing your laptop can't throw away a GPU
job you paid for:

```sh
voiceprint resume            # pick the run back up
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
# -> Nope, my focus this month is on writing that book and finishing up other
#    open loops. Can I catch up with you in March?

# say this in my voice; code and headings pass through untouched
pbpaste | voiceprint rewrite
```

Useful flags: `--all` shows all eight candidates with scores, `--candidates N` changes how many,
`--temp` is the polish-vs-variance dial (1.2 cleaner, 1.8 more human and more glitchy), `--voice`
picks between voices, `--scorer pangram` swaps the ranker if you have a key.

## Use it from an agent

This is the surface that matters. The model is a *voice*, not a writer — it can't plan, research,
or keep facts straight. An agent that can do those things drives it:

```sh
claude mcp add voiceprint -- uvx voiceprint mcp
```

Then ask your agent to write something. It reads `SKILL.md`, picks one of three workflows —
continue what you have, outline first, or interview you until it knows what you actually think —
and calls the voice model section by section.

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

Those are real numbers from a real 8.8k-word corpus, and they come with a caveat worth stating:
best-of-N *selects* for the style score, so scoring above your own baseline means "picked from
eight tries", not "more you than you are." Novelty is the number to actually trust.

The defaults were set by measuring, not guessing. At 8 epochs the training loss reached 0.000 and
the adapter began ignoring its input on rewrites — handing back corpus-flavoured prose instead of
your text in your voice. At 3, novelty went to 1.000, the style score went *up*, and rewrites
started preserving content.

## What it costs

| | |
|---|---|
| Train a voice | a few minutes of one A100, once per voice |
| Store an adapter | ~140 MB in your Modal volume |
| A draft | a few GPU-seconds, warm; a cold container loads 14B first |

Nothing is charged by us. You are paying Modal for your own GPU time.

## Please don't

Clone your own voice, or one you have explicit permission to use. Not someone else's, not for
assignments you're submitting as your own work, not for reviews or accounts pretending to be
people. See [POLICY.md](POLICY.md).

MIT licensed.
