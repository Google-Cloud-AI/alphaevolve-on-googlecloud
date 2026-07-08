Optimize LoRA fine-tuning hyperparameters for Gemma 4 E2B (5.1B params
with embeddings) on a function-calling dataset
(NousResearch/hermes-function-calling-v1).

The goal is to minimize evaluation loss (maximize neg_eval_loss) after 100
training steps. The get_training_config() function returns a dict with:

GPU: NVIDIA A100 40GB VRAM. The base model in bf16 uses ~10 GB, leaving
~28 GB for LoRA adapters, optimizer states, and activations. This is generous
but batch_size * max_seq_length must stay within 4096 to avoid OOM.

LoRA configuration (target_modules is fixed to "all-linear" in the trainer):
- lora_r: Rank of LoRA decomposition (4-64). Higher = more capacity but more memory.
- lora_alpha: Scaling factor (8-128). Effective scale = alpha/r.
- lora_dropout: Dropout on LoRA layers (0.0-0.2).

Optimizer and learning rate:
- learning_rate: Most impactful parameter (1e-5 to 1e-3).
- lr_scheduler_type: "cosine", "linear", "constant", or "constant_with_warmup".
- warmup_ratio: Fraction of steps for warmup (0.0-0.1).
- weight_decay: L2 regularization (0.0-0.1).
- optim: "adamw_torch", "adamw_8bit", or "adafactor".
- max_grad_norm: Gradient clipping threshold (0.1-5.0).

Batch and data:
- per_device_train_batch_size: Batch size per GPU (1-8).
- gradient_accumulation_steps: Effective batch = batch * accumulation (1-16).
- max_seq_length: Sequence truncation length (256-1024).
- batch_size * max_seq_length MUST NOT exceed 4096.

Precision:
- bf16: Whether to use bfloat16 mixed precision (True/False). Keep True.
