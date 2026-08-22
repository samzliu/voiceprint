"""Voiceprint — train a model on your writing, then draft in your voice."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from voiceprint import corpus, engine, models, prep, registry, remote, scorers, stylometry, train
from voiceprint.scaffold import DEFAULT_N, DEFAULT_TEMPERATURE, LENGTHS


def main() -> int:
    parser = argparse.ArgumentParser(prog="voiceprint", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_deploy = sub.add_parser("deploy", help="deploy the GPU app to your own Modal workspace")
    p_deploy.set_defaults(run=cmd_deploy)

    p_train = sub.add_parser("train", help="train a voice on a file or folder of your writing")
    p_train.add_argument("path", help="file or folder of .md/.txt you wrote")
    p_train.add_argument("--name", required=True, help="what to call this voice")
    p_train.add_argument(
        "--model",
        default=models.DEFAULT_MODEL,
        help=f"preset ({', '.join(models.MODEL_PRESETS)}) or any Hugging Face instruct-model id",
    )
    p_train.set_defaults(run=cmd_train)

    p_inspect = sub.add_parser(
        "inspect-corpus", help="check corpus readiness without training or using a GPU"
    )
    p_inspect.add_argument("path", help="file or folder of .md/.txt you wrote")
    p_inspect.add_argument(
        "--hosted",
        action="store_true",
        help="apply the stricter readiness gate used by the paid hosted product",
    )
    p_inspect.set_defaults(run=cmd_inspect_corpus)

    p_resume = sub.add_parser("resume", help="finish collecting a training job")
    p_resume.add_argument("job_id", nargs="?", help="defaults to the most recent unfinished job")
    p_resume.set_defaults(run=cmd_resume)

    p_write = sub.add_parser("write", help="draft in your voice")
    p_write.add_argument("notes", nargs="*", help="a bullet of the brief; repeat for more")
    p_write.add_argument("--notes-file", help="file of bullets, or - for stdin")
    p_write.add_argument("--continue-from", help="file whose text the draft should continue")
    p_write.add_argument("--length", default="medium", choices=list(LENGTHS))
    p_write.add_argument("--candidates", type=int, default=DEFAULT_N)
    p_write.add_argument(
        "--temp", type=float, default=None, help=f"override the sampler (default {DEFAULT_TEMPERATURE})"
    )
    p_write.add_argument("--voice")
    p_write.add_argument("--scorer", default="stylometry", choices=list(scorers.SCORERS))
    p_write.add_argument(
        "--detector",
        default=scorers.DEFAULT_DETECTOR,
        choices=list(scorers.DETECTORS),
        help="gate candidates on P(human); 'none' returns the first draw ungated",
    )
    p_write.add_argument("--all", action="store_true", help="show every candidate with its score")
    p_write.set_defaults(run=cmd_write)

    p_rewrite = sub.add_parser("rewrite", help="say this in my voice (stdin or a file)")
    p_rewrite.add_argument("path", nargs="?", help="file to rewrite; omit to read stdin")
    p_rewrite.add_argument("--candidates", type=int, default=4)
    p_rewrite.add_argument("--temp", type=float, default=None)
    p_rewrite.add_argument("--voice")
    p_rewrite.add_argument("--scorer", default="stylometry", choices=list(scorers.SCORERS))
    p_rewrite.add_argument(
        "--detector", default=scorers.DEFAULT_DETECTOR, choices=list(scorers.DETECTORS)
    )
    p_rewrite.set_defaults(run=cmd_rewrite)

    p_score = sub.add_parser("score", help="score the exact final text (stdin or a file)")
    p_score.add_argument("path", nargs="?", help="file to score; omit to read stdin")
    p_score.add_argument("--voice")
    p_score.add_argument("--scorer", default="stylometry", choices=list(scorers.SCORERS))
    p_score.set_defaults(run=cmd_score)

    p_voices = sub.add_parser("voices", help="list trained voices")
    p_voices.set_defaults(run=cmd_voices)

    p_use = sub.add_parser("use", help="set the voice used when you don't pass --voice")
    p_use.add_argument("name")
    p_use.set_defaults(run=cmd_use)

    p_delete = sub.add_parser("delete", help="forget a voice and drop its adapter")
    p_delete.add_argument("name")
    p_delete.add_argument("--keep-adapter", action="store_true")
    p_delete.set_defaults(run=cmd_delete)

    p_models = sub.add_parser("models", help="list base-model presets")
    p_models.set_defaults(run=cmd_models)

    p_eval = sub.add_parser("eval", help="does it sound like you, and is it reciting?")
    p_eval.add_argument("voice", nargs="?")
    p_eval.add_argument("--samples", type=int, default=5)
    p_eval.add_argument("--scorer", default="stylometry", choices=list(scorers.SCORERS))
    p_eval.set_defaults(run=cmd_eval)

    p_check = sub.add_parser("check", help="is everything set up?")
    p_check.set_defaults(run=cmd_check)

    p_status = sub.add_parser("status", help="what Voiceprint is running and storing in your Modal account")
    p_status.set_defaults(run=cmd_status)

    p_stop = sub.add_parser("stop", help="shut down warm GPU containers now")
    p_stop.set_defaults(run=cmd_stop)

    p_uninstall = sub.add_parser("uninstall", help="remove Voiceprint from your Modal account")
    p_uninstall.add_argument(
        "--keep-cache", action="store_true", help="leave the downloaded model weights in place"
    )
    p_uninstall.add_argument("--yes", action="store_true")
    p_uninstall.set_defaults(run=cmd_uninstall)

    p_mcp = sub.add_parser("mcp", help="run the MCP server on stdio")
    p_mcp.set_defaults(run=cmd_mcp)

    args = parser.parse_args()
    try:
        return args.run(args)
    except (
        corpus.CorpusTooSmall,
        models.NotAnInstructModel,
        engine.WrongFormat,
        registry.VoiceNotFound,
        remote.NotDeployed,
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def cmd_deploy(_args) -> int:
    return remote.deploy()


def cmd_train(args) -> int:
    chunks, warning = train.prepare(args.path)
    words = sum(c.words for c in chunks)
    print(f"{words} words, {len(chunks)} chunks from {args.path}")
    if warning:
        print(f"warning: {warning}")

    hint = models.base_model_warning(models.resolve(args.model))
    if hint:
        print(f"warning: {hint}")

    job_id = train.start(chunks, args.name, args.model)
    print(f"training '{args.name}' on {models.resolve(args.model)} — a few minutes. job {job_id}")
    print(f"safe to interrupt; pick it back up with:  voiceprint resume {job_id}")
    return _await_training(job_id)


def cmd_inspect_corpus(args) -> int:
    documents = corpus.read_path(args.path)
    report = corpus.inspect_hosted(documents) if args.hosted else corpus.inspect(documents)
    print(f"status           {report.status}")
    print(f"documents        {report.usable_documents}/{report.documents} usable")
    print(f"words            {report.usable_words} usable / {report.raw_words} read")
    print(f"chunks           {report.chunks}")
    if report.duplicate_chunks:
        print(
            f"duplicates       {report.duplicate_chunks} passages / "
            f"{report.duplicate_words} words removed"
        )
    for reason in report.reasons:
        print(f"blocked          {reason}")
    for warning in report.warnings:
        print(f"warning          {warning}")
    return 0 if report.ready else 1


def cmd_resume(args) -> int:
    job_id = args.job_id
    if not job_id:
        jobs = train.pending_jobs()
        if not jobs:
            print("no training jobs waiting to be collected")
            return 0
        job_id, name = jobs[-1]
        print(f"resuming '{name}' (job {job_id})")
    return _await_training(job_id)


def _await_training(job_id: str) -> int:
    voice = train.wait(job_id, on_tick=lambda: print(".", end="", flush=True))
    print(f"\ndone: {voice.pairs} pairs from {voice.words} words -> {voice.adapter_path}")
    print(f'\nwrite with:  voiceprint write --voice {voice.name} "your first bullet"')
    return 0


def cmd_write(args) -> int:
    notes = list(args.notes)
    if args.notes_file:
        notes += _read_bullets(args.notes_file)
    preceding = Path(args.continue_from).read_text(encoding="utf-8") if args.continue_from else ""
    if not notes and not preceding and not sys.stdin.isatty():
        notes += _read_bullets("-")

    draft = engine.write(
        notes=notes or None,
        preceding_text=preceding,
        length=args.length,
        voice_name=args.voice,
        n=args.candidates,
        temperature=args.temp,
        scorer_name=args.scorer,
        detector_name=args.detector,
    )

    if args.all:
        for rank, (text, score) in enumerate([(draft.text, draft.score)] + draft.alternates, 1):
            print(f"--- candidate {rank}  {args.scorer}={score:.3f}\n{text}\n")
        return 0

    print(draft.text)
    print(_verdict(args, draft), file=sys.stderr)
    if draft.soft_failed:
        print(
            "warning: no candidate cleared the detector. Change the notes and regenerate — "
            "editing this text by hand will not help, and usually makes the score worse.",
            file=sys.stderr,
        )
    return 0


def _verdict(args, draft) -> str:
    """What the run cost and what the detector thought, on stderr so that piping
    stdout to a file still gets clean prose."""
    parts = [f"{args.scorer} {draft.score:.3f}"]
    if draft.gated:
        parts.append(f"p_human {draft.p_human:.3f}")
        parts.append(f"{draft.draws} drawn")
    else:
        parts.append(f"best of {len(draft.alternates) + 1}")
    return "\n[" + ", ".join(parts) + "]"


def cmd_rewrite(args) -> int:
    text = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
    if not text.strip():
        raise ValueError("nothing to rewrite")
    print(
        engine.rewrite(
            text,
            voice_name=args.voice,
            n=args.candidates,
            temperature=args.temp,
            scorer_name=args.scorer,
            detector_name=args.detector,
        )
    )
    return 0


def cmd_score(args) -> int:
    text = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
    score = engine.score_text(text, voice_name=args.voice, scorer_name=args.scorer)
    label = "human probability" if args.scorer in ("pangram", "binoculars") else "style match"
    print(f"{args.scorer} {score:.3f}  ({label}; exact input)")
    return 0


def cmd_voices(_args) -> int:
    voices = registry.load_all()
    if not voices:
        print("no voices yet — voiceprint train <path-to-your-writing> --name me")
        return 0

    default = registry.get_default()
    for voice in voices:
        marker = "*" if voice.name == default else " "
        print(
            f"{marker} {voice.name:<16} {models.label(voice.model):<12} {voice.words:>6} words  "
            f"{voice.pairs:>3} pairs  {voice.trained_at}"
            # Only worth the column when it is the answer to "why did that fail".
            + ("  [document format — retrain]" if voice.format != registry.FORMAT_CHAT else "")
        )
    if len(voices) > 1 and not default:
        print("\npick a default with:  voiceprint use <name>")
    return 0


def cmd_use(args) -> int:
    registry.set_default(args.name)
    print(f"default voice is now '{args.name}'")
    return 0


def cmd_delete(args) -> int:
    voice = registry.forget(args.name)
    if args.keep_adapter:
        print(f"removed '{voice.name}' locally; adapter left at {voice.adapter_path}")
        return 0
    dropped = remote.delete_adapter(voice.name)
    print(f"removed '{voice.name}'" + (" and its adapter" if dropped else "; no adapter was stored"))
    return 0


def cmd_status(_args) -> int:
    """What this tool is running and storing inside someone else's cloud account.

    The model cache is the surprising one: base weights are tens of gigabytes and
    they sit in a volume being billed until somebody removes them.
    """
    if not remote.is_deployed():
        print(remote.DEPLOY_HINT)
        return 1

    print(f"app              '{remote.APP_NAME}' deployed to your Modal workspace")
    stored = remote.stored()
    print(f"adapters         {len(stored.adapters)} ({_size(stored.adapter_bytes)})")
    for name, size in stored.adapters:
        known = "" if name in registry.list_names() else "   (no local record — voiceprint delete won't find it)"
        print(f"  {name:<16} {_size(size)}{known}")
    print(f"model cache      {_size(stored.cache_bytes)} of base weights, billed as volume storage")
    print("\nGPU containers shut down 10 minutes after the last draft.")
    print("  voiceprint stop        shut them down now")
    print("  voiceprint uninstall   remove all of it from your account")
    return 0


def cmd_stop(_args) -> int:
    return remote.stop()


def cmd_uninstall(args) -> int:
    drop_cache = not args.keep_cache
    if not args.yes:
        stored = remote.stored()
        print("This removes Voiceprint from your Modal account:")
        print(f"  - the '{remote.APP_NAME}' app and any running containers")
        if drop_cache:
            print(f"  - {_size(stored.cache_bytes)} of cached model weights")
            print(f"  - {len(stored.adapters)} trained adapter(s), {_size(stored.adapter_bytes)}")
        print("\nYour writing and your local voice records are untouched.")
        print("Re-run with --yes to go ahead (--keep-cache keeps the weights and adapters).")
        return 0

    for line in remote.uninstall(drop_cache=drop_cache):
        print(line)
    return 0


def _size(num_bytes: int) -> str:
    if num_bytes >= 1e9:
        return f"{num_bytes / 1e9:.1f} GB"
    return f"{num_bytes / 1e6:.0f} MB"


def cmd_models(_args) -> int:
    print("presets:")
    for preset, model in models.MODEL_PRESETS.items():
        default = "  (default)" if preset == models.DEFAULT_MODEL else ""
        print(f"  {preset:<12} {model}{default}")
    print("\nOr pass any Hugging Face instruct/chat model id to --model. The base needs a chat")
    print("template: Voiceprint trains and generates through it, and that match is the trick.")
    return 0


def cmd_eval(args) -> int:
    """Continue held-out passages the model never saw, then ask three questions:
    does it sound like the author, is it reciting, and how does that compare to
    the author's own unseen writing."""
    voice = engine.resolve(args.voice)
    if not voice.holdout:
        raise RuntimeError(f"'{voice.name}' has no held-out corpus to evaluate against")

    scorer = scorers.build(args.scorer, voice.profile)
    drafts = []
    for chunk in voice.holdout[: args.samples]:
        head, tail = prep.continuation_split(chunk)
        if not head or not tail:
            continue
        draft = engine.write(
            preceding_text=head + " ",
            length="medium",
            voice_name=voice.name,
            n=1,
            scorer_name=args.scorer,
            # Ungated on purpose. Eval asks how the adapter writes on average;
            # letting the detector throw candidates away would measure the
            # filter instead, and bill for the redraws.
            detector_name=None,
        )
        drafts.append(draft.text)
        print(".", end="", flush=True)
    print()

    if not drafts:
        raise RuntimeError("held-out passages were too short to continue")

    generated = sum(scorer.score(d) for d in drafts) / len(drafts)
    human = sum(scorer.score(h) for h in voice.holdout) / len(voice.holdout)
    novel = sum(stylometry.novelty(d, voice.training) for d in drafts) / len(drafts)

    print(f"\nvoice: {voice.name}  ({len(drafts)} drafts continuing held-out passages)")
    print(f"  {args.scorer:<12} {generated:.3f}   (your own unseen writing: {human:.3f})")
    print(f"  novelty      {novel:.3f}   (1.000 = nothing lifted from the training text)")
    if novel < 0.95:
        print("  ^ that is low: it is reciting your corpus, not writing in your voice")
    return 0


def cmd_check(_args) -> int:
    """Answer "why isn't this working" without spending a GPU minute on it."""
    import shutil

    ok = True

    authenticated, deployed = remote.probe()
    if authenticated:
        print("modal account    ok")
    else:
        ok = False
        print("modal account    MISSING — run: modal token new")

    if deployed:
        print("deployed app     ok")
    else:
        ok = False
        print("deployed app     MISSING — run: voiceprint deploy")

    voices = registry.load_all()
    if voices:
        default = registry.get_default() or (voices[0].name if len(voices) == 1 else None)
        print(f"voices           {len(voices)} ({', '.join(v.name for v in voices)})")
        print(f"default voice    {default or 'not set — voiceprint use <name>'}")
    else:
        print("voices           none yet — voiceprint train <your-writing> --name me")

    if shutil.which("claude"):
        print("\nwire it into your agent:")
        print(f"  claude mcp add voiceprint -- {Path(sys.argv[0]).resolve()} mcp")
    return 0 if ok else 1


def cmd_mcp(_args) -> int:
    from voiceprint.mcp_server import run

    run()
    return 0


def _read_bullets(source: str) -> list[str]:
    """A notes file is one bullet per line. A leading -, * or 1. is optional."""
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    lines = (re.sub(r"^[-*•]\s*|^\d+[.)]\s*", "", line.strip()) for line in raw.splitlines())
    return [line for line in lines if line]


if __name__ == "__main__":
    raise SystemExit(main())
