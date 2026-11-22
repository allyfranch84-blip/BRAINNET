"""Treinamento isolado; não importar pelo kernel BRAINNET."""

import argparse
import json
import random
from pathlib import Path

from distill_data_generator import ROLES_PROMPT, PIPELINE_PROMPT

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="/content/dataset_distill.jsonl")
    parser.add_argument("--base", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--output", default="/content/qwen_brainnet_adapter")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-length", type=int, default=1536)
    args = parser.parse_args()

    import torch
    from peft import (
        LoraConfig,
        get_peft_model,
        prepare_model_for_kbit_training,
    )
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    if not torch.cuda.is_available() or torch.version.hip:
        raise SystemExit(
            "Este script requer NVIDIA/CUDA compatível com bitsandbytes. "
            "A RX 580 via Vulkan/Ollama não atende a esse requisito."
        )

    set_seed(42)
    rows = [
        json.loads(line)
        for line in Path(args.dataset).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) < 50:
        raise ValueError("Dataset insuficiente: mínimo de 50 comandos.")

    commands = [row["comando"] for row in rows]
    if len(set(commands)) != len(commands):
        raise ValueError("Existem comandos duplicados no dataset.")

    random.Random(42).shuffle(rows)
    split = max(1, int(len(rows) * 0.1))
    validation_rows, training_rows = rows[:split], rows[split:]

    tokenizer = AutoTokenizer.from_pretrained(
        args.base, revision=args.revision
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    def encode_rows(source):
        examples = []

        for row in source:
            for instruction, answer in (
                (ROLES_PROMPT, row["roles"]),
                (PIPELINE_PROMPT, row["json_perfeito"]),
            ):
                messages = [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": row["comando"]},
                ]
                prompt_ids = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                )
                full_ids = tokenizer.apply_chat_template(
                    messages + [{
                        "role": "assistant",
                        "content": json.dumps(
                            answer, ensure_ascii=False, separators=(",", ":")
                        ),
                    }],
                    tokenize=True,
                    add_generation_prompt=False,
                )

                if full_ids[:len(prompt_ids)] != prompt_ids:
                    raise ValueError("Template incompatível com máscara do prompt.")

                if len(full_ids) > args.max_length:
                    raise ValueError(
                        "Exemplo excede max-length; aumente o limite. "
                        "O JSON não será truncado."
                    )

                examples.append({
                    "input_ids": full_ids,
                    "attention_mask": [1] * len(full_ids),
                    "labels": [-100] * len(prompt_ids)
                              + full_ids[len(prompt_ids):],
                })

        return examples

    training = encode_rows(training_rows)
    validation = encode_rows(validation_rows)

    class Examples(torch.utils.data.Dataset):
        def __init__(self, data):
            self.data = data

        def __len__(self):
            return len(self.data)

        def __getitem__(self, index):
            return self.data[index]

    def collate(batch):
        length = max(len(item["input_ids"]) for item in batch)
        result = {"input_ids": [], "attention_mask": [], "labels": []}

        for item in batch:
            padding = length - len(item["input_ids"])
            result["input_ids"].append(
                item["input_ids"] + [tokenizer.pad_token_id] * padding
            )
            result["attention_mask"].append(
                item["attention_mask"] + [0] * padding
            )
            result["labels"].append(item["labels"] + [-100] * padding)

        return {
            key: torch.tensor(value, dtype=torch.long)
            for key, value in result.items()
        }

    bf16 = torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if bf16 else torch.float16

    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        revision=args.revision,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        ),
        device_map={"": 0},
        torch_dtype=compute_dtype,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model)

    model = get_peft_model(
        model,
        LoraConfig(
            task_type="CAUSAL_LM",
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        ),
    )

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(Path(args.output) / "checkpoints"),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=1,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=16,
            learning_rate=1e-4,
            warmup_ratio=0.05,
            weight_decay=0.01,
            gradient_checkpointing=True,
            bf16=bf16,
            fp16=not bf16,
            optim="adamw_torch",
            logging_steps=10,
            save_strategy="epoch",
            save_total_limit=2,
            report_to="none",
            seed=42,
        ),
        train_dataset=Examples(training),
        eval_dataset=Examples(validation),
        data_collator=collate,
    )

    trainer.train()
    metrics = trainer.evaluate()
    model.save_pretrained(args.output, safe_serialization=True)
    tokenizer.save_pretrained(args.output)

    manifest = {
        "base": args.base,
        "revision_requested": args.revision,
        "revision_resolved": getattr(model.config, "_commit_hash", None),
        "training_commands": len(training_rows),
        "validation_commands": len(validation_rows),
        "metrics": metrics,
    }
    Path(args.output, "training_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()