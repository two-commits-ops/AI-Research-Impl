# Profanity/harm guardrail classifier — Qwen2.5-1.5B LoRA

Fine-tunes `mlx-community/Qwen2.5-1.5B-Instruct-4bit` via LoRA into a SAFE/UNSAFE text
classifier: profanity, slurs, harassment, and explicit harm — with explicit training on
incomplete/streaming transcripts so partial text isn't judged before evidence exists.

## Files

- `lexicon.py` — harm-detection regex used to build/verify labels (profanity, slurs,
  obfuscated spellings, serious-harm terms, direct-harassment phrasing)
- `build_verified_streaming_dataset.py` — shared helpers (PII scam examples, ToxicChat
  loader, GoEmotions loader, prefix-generation logic) imported by the builder below
- `build_final_dataset.py` — the dataset builder. Produces `final_dataset.csv` (one file,
  `split` column) plus `data/train.jsonl` / `data/valid.jsonl` for training
- `run_train.sh` — trains the LoRA adapter (`mlx_lm.lora` wrapper, exact working config)
- `evaluate.py` — evaluates a trained adapter: reads the model's own SAFE/UNSAFE logit
  probability directly (not greedy-decoded text), calibrates a decision threshold to a
  target recall, reports precision/recall/TP/TN/FP/FN
- `evaluate_shieldgemma.py` — same evaluation methodology against Google's ShieldGemma-2b
  (zero-shot baseline comparison)
- `train_data.csv` / `eval_data.csv` — the exact train/test split used for the reported
  results, with an `is_streaming` column marking incomplete-prefix examples

## Reproducing from scratch

```bash
pip install mlx mlx-lm pandas datasets scikit-learn huggingface_hub pyarrow

# 1. Build the dataset (needs balanced_profanity_guardrail_dataset.csv as input —
#    the 6-source public dataset this project started from)
python build_final_dataset.py

# 2. Train
./run_train.sh

# 3. Evaluate
python evaluate.py --adapter ./qwen_final_adapters \
  --calibrate eval_data.csv --target-recall 0.95 --eval eval_data.csv
```

## Headline results (this run)

| | Precision | Recall |
|---|---|---|
| Qwen2.5-1.5B (fine-tuned) | 0.750 | 0.951 |
| ShieldGemma-2b (zero-shot) | 0.513 | 0.951 |

**Streaming/incomplete-text false-positive rate** (the key requirement — does the model
avoid flagging inconclusive partial transcripts): **10.0%** fine-tuned vs. **37.2%**
zero-shot.

## Known limitations

- `beavertails`/`measuring_hate_speech` source data carries some residual label noise
  (~15-20% of a specific subset, per manual audit) not fully cleaned — see conversation
  history for details on what was checked and why an automated fix wasn't safe to apply.
- The `is_streaming` tag only marks the incomplete-prefix side; it does not pair each
  prefix with its own complete-sentence sibling, so streaming precision/recall (as
  opposed to just false-positive rate) isn't directly measurable yet from this split.
- Non-profanity explicit harm (jailbreaks, weapon/instructional content) has a real,
  unresolved precision gap — needs dedicated training data investment, not just more of
  the same profanity-focused data.
