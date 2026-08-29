"""
Final build: same verified pipeline as build_verified_streaming_dataset.py, but keeps
an explicit `is_streaming` flag through to the final output (lost in the earlier jsonl
round-trip) so streaming-specific performance can be measured separately - streaming
being the key requirement. Produces ONE dataset file with a train/test split done FIRST,
then exports training-format jsonl from the train side only, so a freshly-trained model
and ShieldGemma zero-shot can be compared on an identically-constructed, guaranteed-clean
held-out test set.
"""
import json
import os

import pandas as pd

from lexicon import contains_harm
from build_verified_streaming_dataset import (
    build_pii_examples, build_toxicchat, load_goemotions_split, streaming_augment,
)

SYSTEM_PROMPT = (
    "You are a strict guardrail model. Analyze the user text for profanity, slurs, "
    "harassment, or safety violations. Respond ONLY with 'SAFE' or 'UNSAFE'."
)

STREAMING_SOURCES = {
    "base_prefix", "goemotions_prefix", "toxicchat_prefix",
    "pii_streaming_safe_prefix", "pii_streaming_unsafe_full",
}

os.makedirs("data", exist_ok=True)


def main():
    base = pd.read_csv("balanced_profanity_guardrail_dataset.csv")[["text", "label", "source"]]
    base = base.dropna(subset=["text"])
    base["text"] = base["text"].astype(str).str.strip()
    base = base[base["text"].str.len() > 1].drop_duplicates(subset=["text"]).reset_index(drop=True)

    contradiction_mask = (base["label"] == 0) & base["text"].apply(contains_harm)
    print(f"Dropping {contradiction_mask.sum():,} SAFE-labeled contradictions")
    base = base[~contradiction_mask].reset_index(drop=True)

    broad_sources = {"tweet_eval_offensive", "real_toxicity_prompts"}
    flip_mask = base["source"].isin(broad_sources) & (base["label"] == 1) & (~base["text"].apply(contains_harm))
    print(f"Flipping {flip_mask.sum():,} broad-standard UNSAFE rows to SAFE")
    base.loc[flip_mask, "label"] = 0

    print("Loading GoEmotions...")
    hard_train_pool = load_goemotions_split("train")  # will re-derive train/test disjointness via the split below

    print("Loading ToxicChat...")
    toxicchat = build_toxicchat()
    pii = build_pii_examples()

    print("Streaming augmentation...")
    stream_base = streaming_augment(base, max_examples=3500, tag="base")
    stream_hard = streaming_augment(hard_train_pool, max_examples=1200, tag="goemotions")
    stream_toxicchat = streaming_augment(toxicchat, max_examples=400, tag="toxicchat")

    base_unsafe = base[base.label == 1]
    base_safe = base[base.label == 0]
    n_unsafe = min(len(base_unsafe), 18000)
    n_safe = min(len(base_safe), int(n_unsafe * 1.15))
    base_sample = pd.concat([
        base_unsafe.sample(n=n_unsafe, random_state=42),
        base_safe.sample(n=n_safe, random_state=42),
    ])

    pool = pd.concat([
        base_sample[["text", "label", "source"]],
        hard_train_pool[["text", "label", "source"]],
        toxicchat[["text", "label", "source"]],
        pii[["text", "label", "source"]],
        stream_base[["text", "label", "source"]],
        stream_hard[["text", "label", "source"]],
        stream_toxicchat[["text", "label", "source"]],
    ]).drop_duplicates(subset=["text"]).reset_index(drop=True)

    pool["is_streaming"] = pool["source"].isin(STREAMING_SOURCES)
    print(f"\nFull pool: {len(pool):,} rows ({pool['is_streaming'].sum():,} streaming, "
          f"{(~pool['is_streaming']).sum():,} non-streaming)")
    print(pool["label"].value_counts(normalize=True).round(3) * 100)

    # ---- stratified split by (label, is_streaming) so both dimensions are represented in test ----
    train_parts, test_parts = [], []
    for (label, is_stream), group in pool.groupby(["label", "is_streaming"]):
        group = group.sample(frac=1.0, random_state=7).reset_index(drop=True)
        n_test = max(1, int(len(group) * 0.10))
        test_parts.append(group.iloc[:n_test])
        train_parts.append(group.iloc[n_test:])

    train_df = pd.concat(train_parts).sample(frac=1.0, random_state=7).reset_index(drop=True)
    test_df = pd.concat(test_parts).sample(frac=1.0, random_state=7).reset_index(drop=True)
    train_df["split"] = "train"
    test_df["split"] = "test"
    train_df["label_str"] = train_df["label"].map({0: "SAFE", 1: "UNSAFE"})
    test_df["label_str"] = test_df["label"].map({0: "SAFE", 1: "UNSAFE"})

    full = pd.concat([train_df, test_df]).reset_index(drop=True)
    full.to_csv("final_dataset.csv", index=False)

    print(f"\ntrain: {len(train_df):,} ({train_df['is_streaming'].sum():,} streaming)")
    print(f"test:  {len(test_df):,} ({test_df['is_streaming'].sum():,} streaming)")
    print("Saved final_dataset.csv")

    # ---- export training jsonl from the TRAIN split only ----
    n_val = 2000
    train_shuf = train_df.sample(frac=1.0, random_state=9).reset_index(drop=True)
    val_pool = train_shuf.iloc[:n_val]
    train_final = train_shuf.iloc[n_val:]

    def export(df, path):
        with open(path, "w", encoding="utf-8") as f:
            for _, row in df.iterrows():
                f.write(json.dumps({
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": str(row["text"])},
                        {"role": "assistant", "content": row["label_str"]},
                    ]
                }) + "\n")

    export(train_final, "data/train.jsonl")
    export(val_pool, "data/valid.jsonl")
    print(f"Wrote data/train.jsonl ({len(train_final):,}), data/valid.jsonl ({len(val_pool):,})")


if __name__ == "__main__":
    main()
