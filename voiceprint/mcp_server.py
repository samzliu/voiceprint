"""MCP server — the surface that matters.

The tools are deliberately dumb. They do one thing: turn a brief into prose that
sounds like the user. The planning, the research, the section order and the
fact-checking are the calling agent's job, and the descriptions here say so,
because an agent reads tool descriptions even when it hasn't loaded SKILL.md.
"""

from __future__ import annotations

from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from voiceprint import corpus, engine, models, registry, remote, train
from voiceprint.scaffold import DEFAULT_N

INSTRUCTIONS = """Voiceprint writes in the user's own voice, learned from their writing.

It is a voice, not a writer. It cannot plan, research, or keep facts straight — you do that. Pick
one of three workflows:

  completion  The user already has prose. Pass it as preceding_text and continue it. No planning.
  outline     The user knows what they want to say. Draft an outline, show it, get a yes, then
              generate section by section, passing the tail of the previous section as
              preceding_text so sections connect and don't repeat.
  interview   The user has a topic and nothing else. Ask 4-8 real questions — what they actually
              believe, who it's for, the specific example they have in mind — then turn their
              answers into notes and follow the outline workflow.

Interview is not just for the blank page: it is how facts get in. Every name, number, date and URL
must appear in `notes`, or the model will invent one. That is inherent to the sampling that makes
the prose read human, and it cannot be prompted away.

Before writing, identify the delivery mode:

  raw     Return adapter prose verbatim. Warn that it best preserves the learned voice but can
          contain factual, grammatical, or structural errors.
  edited  Correct only false facts, spelling, grammar, broken syntax, and accidental repetition.
          Do not smooth transitions, replace sound metaphors, reorder paragraphs, tighten the
          rhythm, or otherwise perform a general AI polish. Warn that even limited AI edits may
          score as more AI-like. Your correction draft is private: finish every narrow change with
          edit_span, or a whole corrected draft with revoice, and return only Voiceprint's result.

After assembling, verify every specific against the sources. Score the exact final artifact, never
an earlier candidate. A stylometry score measures voice similarity, not AI detection. Pangram is an
optional single-detector check and does not guarantee what other detectors will report. If an edited
artifact loses the desired score, run the affected prose back through Voiceprint, verify its facts
again, and score that exact result before delivery."""

server = MCPServer(name="voiceprint", instructions=INSTRUCTIONS)


@server.tool()
def setup_status() -> dict:
    """Where the user is in setup. Call this first, before anything else.

    Returns the next step to take, if any. The steps are: a free Modal account
    (`modal token new`, which the user must run themselves — it opens a browser),
    then `voiceprint deploy`, then training a voice from a folder of their
    writing. Walk them through whichever is outstanding; don't assume.
    """
    authenticated, deployed = remote.probe()
    voices = registry.list_names()

    if not authenticated:
        step = "run `modal token new` — a free Modal account, opens a browser, one time only"
    elif not deployed:
        step = "run `voiceprint deploy` — builds the GPU images into their account, ~4 minutes"
    elif not voices:
        step = "train a voice: they put 1-2k words of their own writing in a folder, then train_voice"
    else:
        step = ""

    return {
        "modal_account": authenticated,
        "deployed": deployed,
        "voices": voices,
        "default_voice": registry.get_default(),
        "next_step": step,
        "ready": bool(voices),
    }


@server.tool()
def deploy() -> dict:
    """Deploy the GPU app into the user's Modal workspace. Just run it.

    This is a setup step you perform for them, not one you read out. It takes
    about four minutes the first time (it builds two GPU images) and is a no-op
    afterwards, so say what you're doing and then do it. Requires a Modal
    account to already exist — check setup_status first.
    """
    code = remote.deploy()
    if code != 0:
        raise RuntimeError(f"`voiceprint deploy` failed with exit code {code}")
    return {"deployed": True}


@server.tool()
def list_voices() -> list[dict]:
    """List the voices this user has trained. Call this first if no voice is named."""
    return [
        {"name": v.name, "words": v.words, "model": models.label(v.model),
         "default": v.name == registry.get_default(), "trained_at": v.trained_at}
        for v in registry.load_all()
    ]


@server.tool()
def inspect_corpus(path: str, hosted: bool = False) -> dict:
    """Check whether a writing corpus is ready before training or payment.

    This is a deterministic local check and never starts a GPU. It reports usable
    prose, ignored documents, exact duplicate passages, blocking reasons, and
    warnings. Set hosted=true before offering the managed $20 training purchase;
    that gate requires more material than the self-hosted CLI minimum.
    """
    documents = corpus.read_path(path)
    report = corpus.inspect_hosted(documents) if hosted else corpus.inspect(documents)
    return asdict(report)


@server.tool()
def write_in_my_style(
    notes: list[str] | None = None,
    preceding_text: str = "",
    length: str = "medium",
    voice: str | None = None,
    candidates: int = DEFAULT_N,
) -> dict:
    """Write a passage in the user's voice. One call per section, not per document.

    notes: the brief, as bullets — the *material* of the passage, never instructions about it.
        Put EVERY fact, name, number and URL you want in the output here; anything absent will be
        invented. Despite the chat format, this adapter has been trained away from following
        instructions and towards writing prose: a bullet like "do not mention any companies" is
        content it writes up, not a rule it obeys, and makes the thing more likely to appear.
        Constraints belong in your choice of facts, not in notes.
        If a passage comes back wrong twice, fix the notes or move on — do not loop.
    preceding_text: prose the passage should continue from. For a continuation, this is the user's
        own text. For section N of a long piece, pass the last paragraph or two of section N-1.
        Supplying it is what keeps sections connected and stops them repeating each other.
    length: "short" (a reply or a post), "medium" (a section), "long" (a whole piece). This is a
        trained control, so use it rather than asking for a word count in the notes.
    candidates: the *cap* on drafts sampled, not the number drawn. Each draft is checked by an
        AI detector and the first one that passes is returned, so the usual cost is one or two.

    Returns raw adapter prose, its style score, and the detector's reading of the exact text
    returned. It has not been fact-checked or edited.
    """
    draft = engine.write(
        notes=notes,
        preceding_text=preceding_text,
        length=length,
        voice_name=voice,
        n=candidates,
    )
    return {
        "text": draft.text,
        "style_score": round(draft.score, 3),
        "p_human": round(draft.p_human, 3),
        "candidates_drawn": draft.draws,
        "mode": "raw",
        "warning": (
            "no candidate passed the detector; this is the closest. Change the notes and call "
            "again — do NOT edit this text to improve it, which reliably makes it worse."
            if draft.soft_failed
            else "raw adapter output; verify facts and grammar before publishing"
        ),
        "final_writer": "voiceprint",
        "finalized_by_adapter": True,
    }


@server.tool()
def rewrite_in_my_style(text: str, voice: str | None = None) -> dict:
    """Rewrite existing text so it sounds like the user, keeping its content.

    Use this when the words already exist and only the voice is wrong — an AI-sounding draft, or
    the user's own rough dump. Code blocks, headings, tables and quotes pass through untouched.
    Do not use it to write something new; use write_in_my_style for that.
    """
    return {
        "text": engine.revoice(text, voice_name=voice),
        "final_writer": "voiceprint",
        "finalized_by_adapter": True,
    }


@server.tool()
def revoice(text: str, voice: str | None = None) -> dict:
    """Make Voiceprint the final writer of an existing draft.

    Use after a human or general LLM has planned factual or mechanical changes.
    Never expose that intermediate draft: return only this adapter-authored text.
    """
    return {
        "text": engine.revoice(text, voice_name=voice),
        "final_writer": "voiceprint",
        "finalized_by_adapter": True,
    }


@server.tool()
def edit_span(
    text: str,
    start: int,
    end: int,
    replacement_draft: str,
    voice: str | None = None,
) -> dict:
    """Apply one precise edit while preserving Voiceprint as the final writer.

    start/end are Python character offsets into `text`. A planning model may
    prepare `replacement_draft`, but it is private intermediate material. This
    tool revoices that replacement and preserves all text outside the span.
    """
    return {
        "text": engine.edit_span(text, start, end, replacement_draft, voice_name=voice),
        "edited_span": {"start": start, "end": end},
        "final_writer": "voiceprint",
        "finalized_by_adapter": True,
    }


@server.tool()
def score_final_text(
    text: str,
    voice: str | None = None,
    scorer: str = "stylometry",
) -> dict:
    """Score the exact final artifact after all edits.

    scorer: "stylometry" measures similarity to the user's corpus locally. "binoculars" returns
        the self-hosted detector's human probability — the same one that gates generation.
        "pangram" returns Pangram's estimate and requires PANGRAM_API_KEY. Either detector is
        one detector, not a guarantee about every detector.

    Never reuse a raw candidate's score for an edited version. Pass the complete text that will
    actually be delivered or published.
    """
    value = engine.score_text(text, voice_name=voice, scorer_name=scorer)
    return {
        "scorer": scorer,
        "score": round(value, 3),
        "meaning": (
            "human_probability" if scorer in ("pangram", "binoculars") else "style_similarity"
        ),
        "artifact": "exact_input",
    }


@server.tool()
def train_voice(path: str, name: str, model: str = models.DEFAULT_MODEL) -> dict:
    """Start training a new voice from a file or folder of the user's writing.

    Takes several minutes, so this returns a job_id immediately — poll check_training with it.
    Needs ~1-2k words of prose the user actually wrote; it refuses below 300 words.
    model: a preset name or any Hugging Face *instruct/chat* model id. The base must have a chat
        template — the adapter is trained and served through it, and that match is the technique.
    """
    return {
        "job_id": train.spawn(path, name, model),
        "note": "training runs on the user's own Modal account; poll check_training",
    }


@server.tool()
def check_training(job_id: str) -> dict:
    """Check a training job. Returns status 'running' until the voice is ready to write with."""
    voice = train.collect(job_id)
    if voice is None:
        return {"status": "running"}
    return {
        "status": "ready",
        "voice": voice.name,
        "words": voice.words,
        "pairs": voice.pairs,
    }


def run() -> None:
    server.run("stdio")
