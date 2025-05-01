#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import csv
import os
import traceback
from pathlib import Path

def examine_json_structure(file_path):
    """
    Examine the structure of a JSON file to understand its format
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        print(f"\nExamining structure of {file_path}")
        print(f"Top-level type: {type(data)}")
        if isinstance(data, dict):
            print(f"Top-level keys: {list(data.keys())}")
        else:
            print("  (not a dict, skipping key listing)")
    except Exception as e:
        print(f"Error examining {file_path}: {e}")

def process_json_file(file_path):
    """
    处理单个 JSON 文件，返回按模型分组的结果：
    {
      "gpt-4": {
        "zero-shot": {"correct": [...], "incorrect": [...]},
        "five-shot": {...},
        "chain-of-thought": {...}
      },
      ...
    }
    如果 JSON 顶层不是 dict，就直接跳过返回空 dict。
    """
    try:
        data = json.load(open(file_path, 'r', encoding='utf-8'))
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {}

    if not isinstance(data, dict):
        # 跳过 summary 文件或其它不符合结构的文件
        print(f"Skipping {file_path}: top-level JSON is {type(data).__name__}, expected dict.")
        return {}

    test_subject = Path(file_path).stem.split('_results')[0]
    per_model = {}

    for model_name, model_data in data.items():
        if not isinstance(model_data, dict):
            print(f"  Skipping model entry in {file_path}: '{model_name}' is type {type(model_data).__name__}")
            continue

        # 初始化模型结构
        per_model.setdefault(model_name, {
            "zero-shot": {"correct": [], "incorrect": []},
            "five-shot": {"correct": [], "incorrect": []},
            "chain-of-thought": {"correct": [], "incorrect": []}
        })

        for strategy in ("zero-shot", "five-shot", "chain-of-thought"):
            strat_block = model_data.get(strategy)
            if not isinstance(strat_block, dict):
                # 可能这个策略不存在或不是 dict
                continue

            details = strat_block.get("details", [])
            if not isinstance(details, list):
                # details 不是列表就跳过
                continue

            for q in details:
                if not isinstance(q, dict):
                    continue
                info = {
                    "Subject": test_subject,
                    "Strategy": strategy,
                    "Question_Number": q.get("number", "N/A"),
                    "Difficulty": q.get("difficulty", "N/A"),
                    "Runtime": q.get("runtime", 0),
                    "Question": q.get("question", ""),
                    "Correct_Answer": q.get("correct_answer", ""),
                    "Model_Answer": q.get("model_answer", "")
                }
                bucket = "correct" if q.get("is_correct", False) else "incorrect"
                per_model[model_name][strategy][bucket].append(info)

    return per_model

def merge_results(all_results, new_results):
    """将新文件结果合并到总结果中"""
    for model, strat_data in new_results.items():
        if model not in all_results:
            all_results[model] = strat_data
        else:
            for strat, status_data in strat_data.items():
                for status, answers in status_data.items():
                    all_results[model][strat][status].extend(answers)

def save_to_csv(all_results, output_dir):
    """
    为每个模型输出两份 CSV：
      1. <model>_results.csv: 详细的每题记录
      2. <model>_runtime_statistics.csv: 运行时统计
    """
    os.makedirs(output_dir, exist_ok=True)

    for model, strat_data in all_results.items():
        model_dir = os.path.join(output_dir, model)
        os.makedirs(model_dir, exist_ok=True)

        # —— 1. 详细结果 CSV ——
        detail_path = os.path.join(model_dir, f"{model}_results.csv")
        with open(detail_path, 'w', newline='', encoding='utf-8') as df:
            writer = csv.writer(df)
            writer.writerow([
                "Strategy", "Subject", "Question_Number", "Difficulty",
                "Runtime", "Status", "Question", "Correct_Answer", "Model_Answer"
            ])
            for strat, status_data in strat_data.items():
                for status, answers in status_data.items():
                    for ans in answers:
                        writer.writerow([
                            strat,
                            ans["Subject"],
                            ans["Question_Number"],
                            ans["Difficulty"],
                            ans["Runtime"],
                            "Correct" if status == "correct" else "Incorrect",
                            ans["Question"],
                            ans["Correct_Answer"],
                            ans["Model_Answer"]
                        ])

        # —— 2. 运行时统计 CSV ——
        stat_path = os.path.join(model_dir, f"{model}_runtime_statistics.csv")
        with open(stat_path, 'w', newline='', encoding='utf-8') as sf:
            writer = csv.writer(sf)
            writer.writerow([
                "Strategy", "Status", "Avg_Runtime", "Min_Runtime", "Max_Runtime", "Count"
            ])
            for strat, status_data in strat_data.items():
                for status, answers in status_data.items():
                    runtimes = [a["Runtime"] for a in answers]
                    if not runtimes:
                        continue
                    writer.writerow([
                        strat,
                        "Correct" if status == "correct" else "Incorrect",
                        round(sum(runtimes) / len(runtimes), 2),
                        min(runtimes),
                        max(runtimes),
                        len(runtimes)
                    ])

def find_json_files(directory):
    """
    找到指定目录下所有 JSON 结果文件（包括 .json 后缀或者名字包含 results 的 .txt）
    并返回文件路径列表
    """
    json_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.json') or (file.endswith('.txt') and 'results' in file):
                json_files.append(os.path.join(root, file))
    return json_files

def main():
    base_dir = "/home/ltang24/Education/TOFEL"
    output_dir = "/home/ltang24/Education/runtime_tofel"

    print("Searching for JSON result files...")
    files = find_json_files(base_dir)
    print(f"Found {len(files)} files.")

    all_results = {}
    for fp in files:
        try:
            per_model = process_json_file(fp)
            merge_results(all_results, per_model)
        except Exception:
            print(f"Error in {fp}:\n{traceback.format_exc()}")

    if all_results:
        save_to_csv(all_results, output_dir)
        print(f"Done! 输出在 {output_dir} 下，每个模型各自一个文件夹。")
    else:
        print("No data collected; 请检查 JSON 结构或路径设置。")

if __name__ == "__main__":
    main()
