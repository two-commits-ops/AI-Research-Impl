#!/bin/bash
# Trains a fresh LoRA adapter on data/train.jsonl + data/valid.jsonl (produced by
# build_final_dataset.py) using the exact configuration that produced the final
# result in this project: val loss 0.024, precision 0.750 / recall 0.951 overall,
# and a 10% false-positive rate on incomplete/streaming text vs. 37.2% zero-shot.
#
# Usage:
#   ./run_train.sh                    # fresh run into ./qwen_final_adapters
#   ./run_train.sh --resume PATH      # continue training from an existing adapter

set -e

ADAPTER_PATH="./qwen_final_adapters"
RESUME_FLAG=""

if [ "$1" == "--resume" ]; then
  RESUME_FLAG="--resume-adapter-file $2"
fi

mlx_lm.lora \
  --model mlx-community/Qwen2.5-1.5B-Instruct-4bit \
  --train \
  --data ./data \
  --adapter-path "$ADAPTER_PATH" \
  $RESUME_FLAG \
  --mask-prompt \
  --batch-size 8 \
  --num-layers 16 \
  --iters 2500 \
  --learning-rate 1e-4 \
  --max-seq-length 128 \
  --val-batches 20 \
  --steps-per-report 20 \
  --steps-per-eval 250 \
  --save-every 250 \
  --seed 5
