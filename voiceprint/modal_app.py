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


@app.cls(image=serve_image, gpu=SERVE_GPU, volumes=VOLUMES, scaledown_window=600, timeout=900)
class Writer:
    """One resident base model, adapters swapped per request.

    This is the unit-economics shape from the research: the expensive thing is
    the base weights, and every voice is a ~140MB adapter hot-loaded onto them.
    """

    model: str = modal.parameter(default="Qwen/Qwen2.5-14B")

    @modal.enter()
    def start(self):
        from vllm import LLM

        self.llm = LLM(
            model=self.model,
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
