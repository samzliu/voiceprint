"""The GPU side: one function that trains a voice, one class that writes with it.

Deployed once into the user's own Modal workspace (`voiceprint deploy`), so their
writing is processed by their account and warm containers survive between CLI
calls. Nothing here talks to any service of ours, because there isn't one.
"""

# No `from __future__ import annotations` in this module: Modal inspects the real
# type object of a class parameter to pick a serializer, and stringized
# annotations turn `base: str` into the string "str", which it cannot resolve.

import modal

APP_NAME = "voiceprint"

VOICES_VOLUME = "voiceprint-voices"
CACHE_VOLUME = "voiceprint-cache"

PREP_MODEL = "Qwen/Qwen2.5-7B-Instruct"
PUBLIC_DEMO_MODEL = "Qwen/Qwen2.5-14B"
PUBLIC_DEMO_VOICE = "default"

# Fits every supported base model in bf16 with room for a KV cache. If you ever
# want a base too big for 80GB, change this and redeploy.
TRAIN_GPU = "A100-80GB"
SERVE_GPU = "A100-80GB"

LORA_RANK = 16
LORA_ALPHA = 32
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
LEARNING_RATE = 1e-4
# 8 epochs drove training loss to 0.000 and the adapter started ignoring the
# input on rewrites, handing back corpus-flavoured prose instead of the user's
# text in their voice. 3 keeps the voice and leaves the input load-bearing.
EPOCHS = 3
GRAD_ACCUM = 2
MAX_SEQ_LEN = 2048

app = modal.App(APP_NAME)

voices_volume = modal.Volume.from_name(VOICES_VOLUME, create_if_missing=True)
cache_volume = modal.Volume.from_name(CACHE_VOLUME, create_if_missing=True)

# `add_local_python_source` has to come last in each chain: Modal refuses build
# steps after local files are added, so that a code edit doesn't rebuild the image.
_base_image = modal.Image.debian_slim(python_version="3.12").env({"HF_HOME": "/cache/hf"})

train_image = _base_image.pip_install(
    "torch==2.13.0",
    "transformers==4.57.6",
    "peft==0.20.0",
    "accelerate>=1.0",
    "huggingface_hub",
).add_local_python_source("voiceprint")

# Serving needs a CUDA *devel* base, not debian_slim: vLLM's flashinfer backend
# JIT-compiles kernels at engine start and dies without nvcc on the box.
serve_image = (
    modal.Image.from_registry("nvidia/cuda:13.0.1-devel-ubuntu24.04", add_python="3.12")
    .env({"HF_HOME": "/cache/hf"})
    .pip_install("vllm==0.27.1", "huggingface_hub")
    .add_local_python_source("voiceprint")
)

web_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi[standard]", "numpy>=1.26")
    .add_local_python_source("voiceprint")
)

VOLUMES = {"/voices": voices_volume, "/cache": cache_volume}



@app.function(image=train_image, gpu=TRAIN_GPU, volumes=VOLUMES, timeout=3600)
def train_voice(name: str, chunks: list[dict], model: str) -> dict:
    """Chunks in, adapter in the volume out.

    Two model loads in one container: the instruct model writes the training
    briefs, then the base model learns to write bodies from them. The instruct
    model is used here and only here — its own prose is the thing we are
    training away from.
    """
    import time

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from voiceprint.corpus import Chunk
    from voiceprint.prep import degrade_request, notes_request, pairs_for_chunk, parse_notes

    started = time.time()
    restored = [Chunk(**chunk) for chunk in chunks]

    print(f"[prep] {len(restored)} chunks -> briefs and degradations")
    prep_tokenizer = AutoTokenizer.from_pretrained(PREP_MODEL)
    prep_model = AutoModelForCausalLM.from_pretrained(
        PREP_MODEL, torch_dtype=torch.bfloat16, device_map="cuda"
    )

    prep_tokenizer.padding_side = "left"
    if prep_tokenizer.pad_token is None:
        prep_tokenizer.pad_token = prep_tokenizer.eos_token

    def ask(requests: list[str], max_new_tokens: int, batch_size: int = 8) -> list[str]:
        answers = []
        for start in range(0, len(requests), batch_size):
            prompts = [
                prep_tokenizer.apply_chat_template(
                    [{"role": "user", "content": request}],
                    tokenize=False,
                    add_generation_prompt=True,
                )
                for request in requests[start : start + batch_size]
            ]
            batch = prep_tokenizer(prompts, return_tensors="pt", padding=True).to("cuda")
            with torch.no_grad():
                out = prep_model.generate(
                    **batch,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=prep_tokenizer.pad_token_id,
                )
            answers.extend(
                prep_tokenizer.decode(row[batch["input_ids"].shape[1] :], skip_special_tokens=True)
                for row in out
            )
            print(f"[prep] {len(answers)}/{len(requests)}")
        return answers

    notes_raw = ask([notes_request(c.text) for c in restored], max_new_tokens=200)
    degraded = ask([degrade_request(c.text) for c in restored], max_new_tokens=700)

    del prep_model
    torch.cuda.empty_cache()

    pairs = []
    for chunk, raw, degradation in zip(restored, notes_raw, degraded):
        pairs.extend(pairs_for_chunk(chunk, parse_notes(raw), degradation))
    if not pairs:
        raise RuntimeError("prep produced no usable training pairs")
    print(f"[prep] {len(pairs)} pairs: " + ", ".join(
        f"{kind}={sum(p.kind == kind for p in pairs)}" for kind in ("write", "continue", "rewrite")
    ))

    print(f"[train] {model}")
    tokenizer = AutoTokenizer.from_pretrained(model)
    network = AutoModelForCausalLM.from_pretrained(
        model, torch_dtype=torch.bfloat16, device_map="cuda"
    )
    network.gradient_checkpointing_enable()
    network.enable_input_require_grads()
    network = get_peft_model(
        network,
        LoraConfig(
            r=LORA_RANK,
            lora_alpha=LORA_ALPHA,
            lora_dropout=0.05,
            target_modules=LORA_TARGETS,
            task_type="CAUSAL_LM",
        ),
    )
    network.print_trainable_parameters()

    examples = []
    for pair in pairs:
        prompt_ids = tokenizer(pair.prompt, add_special_tokens=False).input_ids
        completion_ids = tokenizer(pair.completion, add_special_tokens=False).input_ids
        completion_ids = completion_ids + [tokenizer.eos_token_id]
        if len(prompt_ids) + len(completion_ids) > MAX_SEQ_LEN:
            continue
        examples.append(
            {
                "input_ids": prompt_ids + completion_ids,
                # Loss on the body only. The prompt is scaffolding, not the voice.
                "labels": [-100] * len(prompt_ids) + completion_ids,
            }
        )
    if not examples:
        raise RuntimeError(f"every pair exceeded {MAX_SEQ_LEN} tokens — chunks are too long")

    optimizer = torch.optim.AdamW(
        [p for p in network.parameters() if p.requires_grad], lr=LEARNING_RATE
    )
    total_steps = max(1, (len(examples) * EPOCHS) // GRAD_ACCUM)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_steps)

    network.train()
    generator = torch.Generator().manual_seed(0)
    step = 0
    for epoch in range(EPOCHS):
        order = torch.randperm(len(examples), generator=generator).tolist()
        for index, position in enumerate(order):
            example = examples[position]
            input_ids = torch.tensor([example["input_ids"]], device="cuda")
            labels = torch.tensor([example["labels"]], device="cuda")
            loss = network(input_ids=input_ids, labels=labels).loss / GRAD_ACCUM
            loss.backward()
            if (index + 1) % GRAD_ACCUM == 0:
                torch.nn.utils.clip_grad_norm_(
                    [p for p in network.parameters() if p.requires_grad], 1.0
                )
                optimizer.step()
                schedule.step()
                optimizer.zero_grad()
                step += 1
        print(f"[train] epoch {epoch + 1}/{EPOCHS} loss={loss.item() * GRAD_ACCUM:.3f}")

    adapter_path = f"/voices/{name}"
    network.save_pretrained(adapter_path)
    voices_volume.commit()

    elapsed = round(time.time() - started, 1)
    print(f"[done] {adapter_path} in {elapsed}s over {step} optimizer steps")
    return {
        "adapter_path": adapter_path,
        "pairs": len(pairs),
        "examples": len(examples),
        "steps": step,
        "seconds": elapsed,
        "model": model,
    }


@app.cls(
    image=serve_image,
    gpu=SERVE_GPU,
    volumes=VOLUMES,
    scaledown_window=600,
    timeout=900,
    # Warm-on-demand: a container stays warm for 10 min after each request, so
    # only the first request after a lull cold-starts. No 24/7 GPU cost.
    # A public demo must never turn a traffic spike into a fleet of A100s.
    # Excess requests queue behind this one container.
    max_containers=1,
)
class Writer:
    """One resident base model, adapters swapped per request.

    This is the unit-economics shape from the research: the expensive thing is
    the base weights, and every voice is a ~140MB adapter hot-loaded onto them.
    """

    @modal.enter()
    def start(self):
        from vllm import LLM

        self.llm = LLM(
            model=PUBLIC_DEMO_MODEL,
            enable_lora=True,
            max_lora_rank=LORA_RANK,
            max_model_len=4096,
            gpu_memory_utilization=0.90,
        )

    @modal.method()
    def generate(
        self,
        adapter_path: str,
        prompt: str,
        n: int,
        temperature: float,
        min_p: float,
        max_tokens: int,
        stop: list[str],
    ) -> list[str]:
        from vllm import SamplingParams
        from vllm.lora.request import LoRARequest

        voices_volume.reload()
        name = adapter_path.rstrip("/").split("/")[-1]
        request = LoRARequest(name, abs(hash(name)) % 1_000_000 + 1, adapter_path)
        params = SamplingParams(
            n=n, temperature=temperature, min_p=min_p, max_tokens=max_tokens, stop=stop
        )
        result = self.llm.generate([prompt], params, lora_request=request)[0]
        return [
            {"text": output.text.strip(), "finish_reason": output.finish_reason}
            for output in result.outputs
        ]


def parse_demo_brief(value: object) -> list[str]:
    """Validate the deliberately small public surface before it reaches a GPU."""
    if not isinstance(value, str):
        raise ValueError("brief must be text")
    brief = value.strip()
    if len(brief) < 20:
        raise ValueError("add a little more detail (at least 20 characters)")
    if len(brief) > 1_200:
        raise ValueError("brief is too long (1,200 characters maximum)")

    notes = []
    for raw in brief.splitlines():
        note = raw.strip().lstrip("-*• ").strip()
        if note:
            notes.append(note)
    if not notes:
        raise ValueError("brief must contain at least one note")
    if len(notes) > 8:
        raise ValueError("use no more than 8 notes")
    return notes


def _run_demo_job(item: dict) -> dict:
    from voiceprint.scaffold import (
        DEFAULT_MIN_P,
        DEFAULT_TEMPERATURE,
        build_write_prompt,
        stop_for,
        trim_to_sentence,
    )

    notes = parse_demo_brief(item.get("brief"))

    length = item.get("length", "medium")
    if length not in {"short", "medium"}:
        raise ValueError("length must be short or medium")

    prompt = build_write_prompt(notes, length)
    results = Writer().generate.remote(
        adapter_path=f"/voices/{PUBLIC_DEMO_VOICE}",
        prompt=prompt,
        n=2,
        temperature=DEFAULT_TEMPERATURE,
        min_p=DEFAULT_MIN_P,
        max_tokens=200 if length == "short" else 600,
        stop=stop_for(length),
    )
    drafts = [
        trim_to_sentence(result["text"])
        if result["finish_reason"] == "length"
        else result["text"]
        for result in results
        if result["text"].strip()
    ]
    if not drafts:
        raise RuntimeError("the model returned no draft")
    return {"drafts": drafts, "voice": PUBLIC_DEMO_VOICE, "length": length}


@app.function(image=web_image, timeout=900, max_containers=2)
def demo_job(item: dict) -> dict:
    """A queued generation, allowed to outlive any individual HTTP request."""
    return _run_demo_job(item)


@app.function(image=web_image, timeout=60, max_containers=2)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def demo_start(item: dict) -> dict:
    """Validate and enqueue a bounded public-demo generation."""
    from fastapi import HTTPException

    try:
        parse_demo_brief(item.get("brief"))
        if item.get("length", "medium") not in {"short", "medium"}:
            raise ValueError("length must be short or medium")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    call = demo_job.spawn(item)
    return {"call_id": call.object_id}


@app.function(image=web_image, timeout=60, max_containers=2)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def demo_result(item: dict):
    """Poll a queued generation without holding a long-lived proxy request."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    call_id = item.get("call_id")
    if not isinstance(call_id, str) or not call_id.startswith("fc-"):
        raise HTTPException(status_code=400, detail="invalid job id")
    try:
        return modal.FunctionCall.from_id(call_id).get(timeout=0)
    except TimeoutError:
        return JSONResponse(status_code=202, content={"status": "pending"})


HOSTED_MODELS = {PUBLIC_DEMO_MODEL}
HOSTED_MIN_WORDS = 1_000


def parse_hosted_training(item: object) -> tuple[str, list[dict], str]:
    """Validate paid training before a queued job can reserve a GPU."""
    if not isinstance(item, dict):
        raise ValueError("request must be an object")
    name = item.get("name")
    if not isinstance(name, str) or not name.startswith("model_") or len(name) > 96:
        raise ValueError("invalid model name")
    model = item.get("model", PUBLIC_DEMO_MODEL)
    if model not in HOSTED_MODELS:
        raise ValueError("unsupported base model")
    incoming = item.get("chunks")
    if not isinstance(incoming, list) or len(incoming) > 500:
        raise ValueError("chunks must be a list of no more than 500 passages")

    chunks = []
    total_words = 0
    for index, value in enumerate(incoming):
        if not isinstance(value, dict):
            raise ValueError(f"chunk {index + 1} must be an object")
        text = value.get("text")
        source = value.get("source", f"document-{index + 1}")
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
            raise ValueError(f"chunk {index + 1} has invalid text")
        words = len(text.split())
        if words < 25:
            raise ValueError(f"chunk {index + 1} is too short")
        if not isinstance(source, str):
            source = f"document-{index + 1}"
        length = "short" if words <= 120 else "medium" if words <= 500 else "long"
        chunks.append({"text": text.strip(), "words": words, "length": length, "source": source[:240]})
        total_words += words
    if total_words < HOSTED_MIN_WORDS:
        raise ValueError(f"at least {HOSTED_MIN_WORDS:,} usable words are required")
    return name, chunks, model


def parse_training_callback(item: object) -> tuple[str, str, str] | None:
    """Validate the Worker-owned completion callback metadata."""
    if not isinstance(item, dict):
        raise ValueError("request must be an object")
    values = (item.get("callback_url"), item.get("callback_secret"), item.get("job_id"))
    if all(value is None for value in values):
        return None
    callback_url, callback_secret, job_id = values
    if not isinstance(callback_url, str) or not callback_url.startswith("https://") or len(callback_url) > 500:
        raise ValueError("invalid callback URL")
    if not isinstance(callback_secret, str) or len(callback_secret) < 16:
        raise ValueError("invalid callback secret")
    if not isinstance(job_id, str) or not job_id.startswith("job_") or len(job_id) > 96:
        raise ValueError("invalid callback job id")
    return callback_url, callback_secret, job_id


def parse_hosted_generation(item: object) -> dict:
    """Bound every user-controlled generation field before loading an adapter."""
    if not isinstance(item, dict):
        raise ValueError("request must be an object")
    adapter_path = item.get("adapter_path")
    model = item.get("provider_model", PUBLIC_DEMO_MODEL)
    shared_voice_path = f"/voices/{PUBLIC_DEMO_VOICE}"
    if (
        not isinstance(adapter_path, str)
        or ".." in adapter_path
        or len(adapter_path) > 120
        or not (adapter_path.startswith("/voices/model_") or adapter_path == shared_voice_path)
    ):
        raise ValueError("invalid adapter path")
    if model not in HOSTED_MODELS:
        raise ValueError("unsupported base model")
    operation = item.get("operation", "write")
    if operation not in {"write", "continue", "rewrite", "edit_span", "revoice"}:
        raise ValueError("operation must be write, continue, rewrite, edit_span, or revoice")
    length = item.get("length", "medium")
    if length not in {"short", "medium", "long"}:
        raise ValueError("length must be short, medium, or long")

    notes = item.get("notes", [])
    if not isinstance(notes, list) or len(notes) > 12 or any(not isinstance(note, str) for note in notes):
        raise ValueError("notes must contain no more than 12 text items")
    notes = [note.strip()[:500] for note in notes if note.strip()]
    preceding = item.get("preceding_text", "")
    draft = item.get("text", "")
    replacement_draft = item.get("replacement_draft", "")
    text_before = item.get("text_before")
    text_after = item.get("text_after")
    if not isinstance(preceding, str) or len(preceding) > 30_000:
        raise ValueError("preceding_text is too long")
    if not isinstance(draft, str) or len(draft) > 30_000:
        raise ValueError("text is too long")
    if not isinstance(replacement_draft, str) or len(replacement_draft) > 30_000:
        raise ValueError("replacement_draft is too long")
    if operation == "write" and not notes:
        raise ValueError("write requires at least one factual note")
    if operation == "continue" and not notes and not preceding.strip():
        raise ValueError("continue requires notes or preceding text")
    if operation in {"rewrite", "revoice"} and not draft.strip():
        raise ValueError(f"{operation} requires source text")
    selection_start = item.get("selection_start")
    selection_end = item.get("selection_end")
    if operation == "edit_span":
        if (
            not isinstance(selection_start, int)
            or isinstance(selection_start, bool)
            or not isinstance(selection_end, int)
            or isinstance(selection_end, bool)
            or selection_start < 0
            or selection_end <= selection_start
            or selection_end > len(draft)
        ):
            raise ValueError("edit_span requires valid selection_start and selection_end offsets")
        if not replacement_draft.strip():
            raise ValueError("edit_span requires a replacement_draft")
        if text_before is not None or text_after is not None:
            if not isinstance(text_before, str) or not isinstance(text_after, str):
                raise ValueError("edit_span context must be text")
            if len(text_before) + len(text_after) > 30_000:
                raise ValueError("edit_span context is too long")
        else:
            text_before = draft[:selection_start]
            text_after = draft[selection_end:]
    profile = item.get("style_profile")
    if profile is not None and not isinstance(profile, dict):
        raise ValueError("style profile must be an object")
    return {
        "adapter_path": adapter_path,
        "provider_model": model,
        "operation": operation,
        "length": length,
        "notes": notes,
        "preceding_text": preceding.strip(),
        "text": draft if operation == "edit_span" else draft.strip(),
        "replacement_draft": replacement_draft.strip(),
        "selection_start": selection_start,
        "selection_end": selection_end,
        "text_before": text_before,
        "text_after": text_after,
        "style_profile": profile,
        "mode": "edited" if item.get("mode") == "edited" else "raw",
    }


@app.function(image=web_image, timeout=3700, max_containers=4)
def hosted_train_job(item: dict) -> dict:
    """Fit the profile and adapter in a durable queued job."""
    from voiceprint import stylometry

    name, chunks, model = parse_hosted_training(item)
    # Preserve an honest held-out slice, matching local training behavior.
    training = [chunk for index, chunk in enumerate(chunks) if index % 7] or chunks
    profile = stylometry.fit([chunk["text"] for chunk in training]).to_dict()
    result = {
        **train_voice.remote(name=name, chunks=training, model=model),
        "profile": profile,
        "usable_words": sum(chunk["words"] for chunk in chunks),
    }
    callback = parse_training_callback(item)
    if callback:
        import json
        from urllib.request import Request, urlopen

        callback_url, callback_secret, job_id = callback
        try:
            callback = Request(
                callback_url,
                data=json.dumps({"job_id": job_id, "result": result}).encode(),
                headers={
                    "Authorization": f"Bearer {callback_secret}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urlopen(callback, timeout=30) as response:
                response.read()
        except Exception as error:  # Polling remains an idempotent delivery fallback.
            print(f"training callback delivery failed: {error}")
    return result


@app.function(image=web_image, timeout=60, max_containers=4)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def hosted_train_start(item: dict) -> dict:
    from fastapi import HTTPException

    try:
        parse_hosted_training(item)
        parse_training_callback(item)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    call = hosted_train_job.spawn(item)
    return {"call_id": call.object_id}


@app.function(image=web_image, timeout=60, max_containers=4)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def hosted_train_result(item: dict):
    return _hosted_result(item)


@app.function(image=web_image, timeout=1000, max_containers=8)
def hosted_generate_job(item: dict) -> dict:
    from voiceprint.scaffold import (
        DEFAULT_MIN_P,
        DEFAULT_TEMPERATURE,
        MAX_TOKENS,
        build_rewrite_prompt,
        build_write_prompt,
        stop_for,
        trim_to_sentence,
    )
    from voiceprint.stylometry import Profile, score

    request = parse_hosted_generation(item)
    rewrite_source = (
        request["replacement_draft"]
        if request["operation"] == "edit_span"
        else request["text"]
    )
    prompt = (
        build_rewrite_prompt(rewrite_source)
        if request["operation"] in {"rewrite", "revoice", "edit_span"}
        else build_write_prompt(
            request["notes"],
            request["length"],
            preceding_text=request["preceding_text"] if request["operation"] == "continue" else "",
        )
    )
    candidates = Writer().generate.remote(
        adapter_path=request["adapter_path"],
        prompt=prompt,
        n=8,
        temperature=DEFAULT_TEMPERATURE,
        min_p=DEFAULT_MIN_P,
        max_tokens=MAX_TOKENS[request["length"]],
        stop=stop_for(request["length"]),
    )
    raw_profile = request.get("style_profile")
    texts = [
        trim_to_sentence(candidate["text"])
        if candidate["finish_reason"] == "length"
        else candidate["text"].strip()
        for candidate in candidates
        if candidate.get("text", "").strip()
    ]
    if not texts:
        raise RuntimeError("the model returned no draft")
    if request["operation"] == "edit_span":
        texts = [f'{request["text_before"]}{text}{request["text_after"]}' for text in texts]
    if raw_profile:
        profile = Profile.from_dict(raw_profile)
        ranked = sorted(((text, score(profile, text)) for text in texts), key=lambda pair: -pair[1])
    else:
        ranked = [(text, 0.0) for text in texts]
    return {
        "drafts": [text for text, _value in ranked],
        "style_scores": [round(value, 4) for _text, value in ranked],
        "mode": request["mode"],
        "operation": request["operation"],
        "warning": (
            "Voiceprint wrote the final edited text; verify facts and re-score this exact artifact."
            if request["operation"] in {"rewrite", "revoice", "edit_span"} or request["mode"] == "edited"
            else "Raw adapter output; verify facts and grammar."
        ),
        "final_writer": "voiceprint",
        "finalized_by_adapter": True,
    }


@app.function(image=web_image, timeout=60, max_containers=8)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def hosted_generate_start(item: dict) -> dict:
    from fastapi import HTTPException

    try:
        parse_hosted_generation(item)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    call = hosted_generate_job.spawn(item)
    return {"call_id": call.object_id}


@app.function(image=web_image, timeout=60, max_containers=8)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def hosted_generate_result(item: dict):
    return _hosted_result(item)


def _hosted_result(item: object):
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    call_id = item.get("call_id") if isinstance(item, dict) else None
    if not isinstance(call_id, str) or not call_id.startswith("fc-"):
        raise HTTPException(status_code=400, detail="invalid job id")
    try:
        return modal.FunctionCall.from_id(call_id).get(timeout=0)
    except TimeoutError:
        return JSONResponse(status_code=202, content={"status": "pending"})
