#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理 Ghidra 导出的 C 文件。
逐函数交给 LLM4Decompile 优化，处理一个写回一个，支持断点续跑。
如果输出文件已存在，从输出文件中恢复已处理状态，跳过已标记函数。
"""

import re
import sys
import argparse
from pathlib import Path

from transformers import AutoTokenizer, AutoModelForCausalLM
import torch


REFINED_MARKER = "/* [LLM4Decompile REFINED] */"
MAX_INPUT_TOKENS = 4096
MAX_NEW_TOKENS = 4096


def load_model(model_path: str, use_8bit: bool = False):
    """加载 LLM4Decompile 模型。"""
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    kwargs = {
        "torch_dtype": torch.float16,
        "device_map": "auto",
    }
    if use_8bit:
        kwargs["load_in_8bit"] = True

    model = AutoModelForCausalLM.from_pretrained(model_path, **kwargs)
    return tokenizer, model


def extract_functions(source: str):
    """
    从 C 文件中提取函数。
    返回 [(func_name, func_body, start_pos, end_pos), ...]
    """
    pattern = re.compile(
        r'([a-zA-Z_][a-zA-Z0-9_\s*]*\s+)'
        r'([a-zA-Z_][a-zA-Z0-9_]*)'
        r'\s*\([^)]*\)\s*\{'
    )

    functions = []
    pos = 0
    while True:
        match = pattern.search(source, pos)
        if not match:
            break

        func_name = match.group(2)
        start = match.start()

        brace_count = 0
        end = match.end() - 1
        for i in range(end, len(source)):
            if source[i] == '{':
                brace_count += 1
            elif source[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break

        func_body = source[start:end]
        functions.append((func_name, func_body, start, end))
        pos = end

    return functions


def get_refined_func_names(source: str) -> set:
    """从已存在的输出文件中提取已被优化过的函数名。"""
    refined = set()
    pattern = re.compile(
        re.escape(REFINED_MARKER) + r'\s*\n'
        r'([a-zA-Z_][a-zA-Z0-9_\s*]*\s+)'
        r'([a-zA-Z_][a-zA-Z0-9_]*)'
        r'\s*\([^)]*\)\s*\{'
    )
    for match in pattern.finditer(source):
        refined.add(match.group(2))
    return refined


def build_prompt(func_body: str) -> str:
    """包装为 LLM4Decompile 的输入格式。"""
    return f"# This is the assembly code:\n{func_body.strip()}\n# What is the source code?\n"


def refine_function(tokenizer, model, func_body: str, max_new_tokens: int = MAX_NEW_TOKENS):
    """调用模型优化单个函数。"""
    prompt = build_prompt(func_body)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    input_len = inputs.input_ids.shape[1]
    if input_len > MAX_INPUT_TOKENS:
        print(f"  Skip: input too long ({input_len} tokens)")
        return None

    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)

    refined = tokenizer.decode(outputs[0][len(inputs[0]):-1], skip_special_tokens=True)
    return refined.strip()


def refine_file(tokenizer, model, input_path: Path, output_path: Path = None):
    """处理整个 C 文件，逐函数写回。"""
    if output_path is None:
        output_path = input_path.with_suffix(".refined.c")

    # 如果输出文件已存在，读取它以恢复已处理状态
    if output_path.exists():
        current_source = output_path.read_text(encoding="utf-8")
        refined_names = get_refined_func_names(current_source)
        print(f"Output file exists. Found {len(refined_names)} already refined functions.")
    else:
        current_source = input_path.read_text(encoding="utf-8")
        refined_names = set()

    # 从当前源文件（输出文件或输入文件）提取所有函数
    functions = extract_functions(current_source)
    print(f"Found {len(functions)} functions in total.")

    refined_count = 0
    skipped_count = 0
    already_count = 0

    for idx, (func_name, func_body, start, end) in enumerate(functions, 1):
        if func_name in refined_names:
            print(f"[{idx}/{len(functions)}] {func_name}: already refined, skip.")
            already_count += 1
            continue

        print(f"[{idx}/{len(functions)}] {func_name}: refining ...", end=" ", flush=True)

        refined_body = refine_function(tokenizer, model, func_body)
        if refined_body is None:
            print("failed (too long or error), skip.")
            skipped_count += 1
            continue

        # 在优化后的函数前添加标记注释
        marked_body = f"{REFINED_MARKER}\n{refined_body}"

        # 立即替换并写回文件
        current_source = current_source[:start] + marked_body + current_source[end:]
        output_path.write_text(current_source, encoding="utf-8")

        # 更新 refined_names，避免同一函数被重复处理
        refined_names.add(func_name)

        # 重新读取文件并重新提取函数，更新后续函数的索引
        current_source = output_path.read_text(encoding="utf-8")
        functions = extract_functions(current_source)

        print("done.")
        refined_count += 1

    print(f"\nFinal output saved to: {output_path}")
    print(f"Refined: {refined_count}, Already done: {already_count}, Skipped: {skipped_count}, Total: {len(functions)}")


def main():
    parser = argparse.ArgumentParser(description="Batch refine Ghidra C output with LLM4Decompile")
    parser.add_argument("input", type=Path, help="Input C file from Ghidra export")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output file path")
    parser.add_argument("-m", "--model", type=str, default="./llm4decompile-6.7b-v2",
                        help="Model path or HuggingFace repo")
    parser.add_argument("--8bit", action="store_true", help="Use 8-bit quantization to save VRAM")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: file not found: {args.input}")
        sys.exit(1)

    print("Loading model...")
    tokenizer, model = load_model(args.model, use_8bit=getattr(args, "8bit"))
    print("Model loaded.")

    refine_file(tokenizer, model, args.input, args.output)


if __name__ == "__main__":
    main()
