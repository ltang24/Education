#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import csv
import os
import traceback
from pathlib import Path

# 根目录，根据需要修改
BASE_DIR = "/home/ltang24/Education/GMAT/Verbal"

def examine_json_structure(file_path):
    """
    Examine the structure of a JSON file to understand its format.
    (可选调试函数，不影响主流程)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"\nExamining {file_path}: top-level {type(data).__name__}")
        if isinstance(data, dict):
            print("  keys:", list(data.keys()))
    except Exception as e:
        print(f"Error examining {file_path}: {e}")

def process_json_file(file_path):
    """
    兼容两种结构的 JSON：
      A) 顶层 dict -> model -> strategy -> details: [...]
      B) 顶层 list -> 直接题目列表，model/strategy 从路径或文件名推断
    返回格式：
      {
        model_name: {
          strategy_name: {"correct": [...], "incorrect": [...]},
          ...
        },
        ...
      }
    """
    p = Path(file_path)
    try:
        data = json.load(open(file_path, 'r', encoding='utf-8'))
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {}

    per_model = {}

    # Case A: 原始格式
    if isinstance(data, dict):
        subject = p.stem.split('_results')[0]
        for model_name, model_data in data.items():
            if not isinstance(model_data, dict):
                continue
            per_model.setdefault(model_name, {
                "zero-shot": {"correct": [], "incorrect": []},
                "five-shot": {"correct": [], "incorrect": []},
                "chain-of-thought": {"correct": [], "incorrect": []}
            })
            for strat in ("zero-shot", "five-shot", "chain-of-thought"):
                block = model_data.get(strat)
                if not isinstance(block, dict):
                    continue
                details = block.get("details", [])
                if not isinstance(details, list):
                    continue
                for q in details:
                    if not isinstance(q, dict):
                        continue
                    num       = q.get("number", q.get("question_id", "N/A"))
                    diff      = q.get("difficulty", "N/A")
                    run       = q.get("runtime", 0)
                    corr_ans  = q.get("correct_answer", q.get("expected", ""))
                    mod_ans   = q.get("model_answer", q.get("model_response", ""))
                    if "is_correct" in q:
                        is_corr = bool(q["is_correct"])
                    elif "correct" in q:
                        is_corr = bool(q["correct"])
                    else:
                        is_corr = (corr_ans == mod_ans)
                    info = {
                        "Subject": subject,
                        "Strategy": strat,
                        "Question_Number": num,
                        "Difficulty": diff,
                        "Runtime": run,
                        "Question": q.get("question", ""),
                        "Correct_Answer": corr_ans,
                        "Model_Answer": mod_ans
                    }
                    bucket = "correct" if is_corr else "incorrect"
                    per_model[model_name][strat][bucket].append(info)
        return per_model

    # Case B: 新格式
    if isinstance(data, list):
        parent = p.parent.name
        grand  = p.parent.parent.name
        if parent in ("zero-shot", "five-shot", "chain-of-thought"):
            strat = parent
            model_name = grand
        else:
            parts = p.stem.split('_')
            model_name = parts[0]
            strat = parts[1] if len(parts) > 1 else "unknown"
        per_model.setdefault(model_name, {
            "zero-shot": {"correct": [], "incorrect": []},
            "five-shot": {"correct": [], "incorrect": []},
            "chain-of-thought": {"correct": [], "incorrect": []}
        })
        for q in data:
            if not isinstance(q, dict):
                continue
            num      = q.get("question_id", "N/A")
            diff     = q.get("difficulty", "N/A")
            run      = q.get("runtime", 0)
            corr_ans = q.get("expected", "")
            mod_ans  = q.get("model_answer", q.get("model_response", ""))
            is_corr  = bool(q.get("correct", False))
            info = {
                "Subject": Path(BASE_DIR).name,
                "Strategy": strat,
                "Question_Number": num,
                "Difficulty": diff,
                "Runtime": run,
                "Question": "",
                "Correct_Answer": corr_ans,
                "Model_Answer": mod_ans
            }
            bucket = "correct" if is_corr else "incorrect"
            per_model[model_name][strat][bucket].append(info)
        return per_model

    # 其他情况跳过
    print(f"Skipping {file_path}: unsupported top-level {type(data).__name__}")
    return {}

def merge_results(all_results, new_results):
    for model, strat_data in new_results.items():
        if model not in all_results:
            all_results[model] = strat_data
        else:
            for strat, status_data in strat_data.items():
                for status, answers in status_data.items():
                    all_results[model][strat][status].extend(answers)

def save_to_csv(all_results, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for model, strat_data in all_results.items():
        model_dir = os.path.join(output_dir, model)
        os.makedirs(model_dir, exist_ok=True)
        # 1. 详细结果
        detail_path = os.path.join(model_dir, f"{model}_results.csv")
        with open(detail_path, 'w', newline='', encoding='utf-8') as df:
            writer = csv.writer(df)
            writer.writerow([
                "Strategy","Subject","Question_Number","Difficulty",
                "Runtime","Status","Question","Correct_Answer","Model_Answer"
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
                            "Correct" if status=="correct" else "Incorrect",
                            ans["Question"],
                            ans["Correct_Answer"],
                            ans["Model_Answer"]
                        ])
        # 2. 运行时统计
        stat_path = os.path.join(model_dir, f"{model}_runtime_statistics.csv")
        with open(stat_path, 'w', newline='', encoding='utf-8') as sf:
            writer = csv.writer(sf)
            writer.writerow([
                "Strategy","Status","Avg_Runtime","Min_Runtime","Max_Runtime","Count"
            ])
            for strat, status_data in strat_data.items():
                for status, answers in status_data.items():
                    runtimes = [a["Runtime"] for a in answers]
                    if not runtimes:
                        continue
                    writer.writerow([
                        strat,
                        "Correct" if status=="correct" else "Incorrect",
                        round(sum(runtimes)/len(runtimes),2),
                        min(runtimes),
                        max(runtimes),
                        len(runtimes)
                    ])

def find_json_files(directory):
    json_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.json') or (file.endswith('.txt') and 'results' in file):
                json_files.append(os.path.join(root, file))
    return json_files

def main():
    base_dir   = BASE_DIR
    output_dir = "/home/ltang24/Education/runtime_GMAT"
    print("Searching for JSON files...")
    files = find_json_files(base_dir)
    print(f"Found {len(files)} files.")
    all_results = {}
    for fp in files:
        try:
            per = process_json_file(fp)
            merge_results(all_results, per)
        except Exception:
            print(f"Error in {fp}:\n{traceback.format_exc()}")
    if all_results:
        save_to_csv(all_results, output_dir)
        print(f"Done! 结果保存在 {output_dir}，每个模型独立文件夹。")
    else:
        print("No data collected; 请检查 JSON 结构或路径。")

if __name__ == "__main__":
    main()
