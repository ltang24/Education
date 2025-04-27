import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """
    Normalize answers by removing dots and spaces.
    （中文注释：将答案中的点号和空格去除，并转换为大写）
    """
    answer = re.sub(r'[.\s]', '', answer, flags=re.IGNORECASE)
    return answer.strip().upper()

def extract_mc_answer(response):
    """
    Extract a single letter option (A-E) from the model's response for single-answer multiple-choice questions.
    （中文注释：从模型回答中提取单选题的答案，返回一个字母）
    """
    # 优先从标准格式 "FINAL ANSWER: X" 中提取
    explicit_pattern = r'FINAL\s+ANSWER\s*:\s*([A-E])'
    explicit_match = re.search(explicit_pattern, response, re.IGNORECASE)
    if explicit_match:
        return normalize_answer(explicit_match.group(1))
    
    # 备用方式：查找独立的字母及句点
    standalone_pattern = r'\b([A-E])\.(?!\w)'
    standalone_match = re.search(standalone_pattern, response, re.IGNORECASE)
    if standalone_match:
        return normalize_answer(standalone_match.group(1))
    
    # 进一步查找行首字母
    line_pattern = r'(?:^|\n)\s*([A-E])\.?'
    line_match = re.search(line_pattern, response, re.IGNORECASE)
    if line_match:
        return normalize_answer(line_match.group(1))
    
    all_options = re.findall(r'\b([A-E])\b', response, re.IGNORECASE)
    if all_options:
        return normalize_answer(all_options[0])
    
    return ""

def extract_multiple_mc_answers(response):
    """
    Extract multiple letter options (A-E) from the model's response for multiple-answer questions.
    （中文注释：从模型回答中提取多选题的答案，返回一个排序后的答案列表）
    """
    # 优先从标准格式 "FINAL ANSWERS: X, Y" 中提取
    explicit_pattern = r'FINAL\s+ANSWERS\s*:\s*([A-E](?:\s*,\s*[A-E])+)'
    explicit_match = re.search(explicit_pattern, response, re.IGNORECASE)
    if explicit_match:
        answers_str = explicit_match.group(1)
        answers = [normalize_answer(a) for a in re.split(r'\s*,\s*', answers_str)]
        return sorted(answers)
    
    # 备用方式：查找所有独立字母
    standalone_pattern = r'\b([A-E])\.(?!\w)'
    standalone_matches = re.findall(standalone_pattern, response, re.IGNORECASE)
    if standalone_matches:
        return sorted([normalize_answer(m) for m in standalone_matches])
    
    line_pattern = r'(?:^|\n)\s*([A-E])\.?'
    line_matches = re.findall(line_pattern, response, re.IGNORECASE | re.MULTILINE)
    if line_matches:
        return sorted([normalize_answer(m) for m in line_matches])
    
    all_options = re.findall(r'\b([A-E])\b', response, re.IGNORECASE)
    if all_options:
        unique_options = []
        for opt in all_options:
            norm = normalize_answer(opt)
            if norm not in unique_options:
                unique_options.append(norm)
        return sorted(unique_options)
    
    return []

def extract_select_in_passage_answer(response, valid_sentences):
    """
    Extract the selected sentence from the passage for select-in-passage questions.
    （中文注释：从模型回答中提取选句题的答案，返回完整的句子）
    """
    # 优先从标准格式 "SELECTED SENTENCE: "exact sentence"" 中提取
    selected_pattern = r'SELECTED\s+SENTENCE\s*:\s*"([^"]+)"'
    selected_match = re.search(selected_pattern, response, re.IGNORECASE)
    if selected_match:
        candidate = selected_match.group(1).strip()
        for sentence in valid_sentences:
            if candidate in sentence or sentence in candidate:
                return sentence
    
    # 如果没有采用标准格式，则尝试匹配回答中与 passage 句子相似的部分
    for sentence in valid_sentences:
        if sentence in response:
            return sentence
    
    return ""

# 1. Load JSON file（加载 JSON 文件）
json_file = "/home/ltang24/Education/GRE RC/GRE_RC_questions.json"
with open(json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# 2. Define main model and backup models（定义主模型和备用模型）
main_model = "gpt-4o"
backup_models = ["gpt-4", "gpt-4o-mini"]

# 3. Initialize client（初始化客户端）
client = Client()

# 4. Limit to first 50 passages（仅处理前50个 passage）
passage_limit = 50
passages = data["passages"][:passage_limit]

print(f"Main model: {main_model}")
print(f"Backup models: {', '.join(backup_models)}")
print(f"Processing the first {len(passages)} passages...")
print("-" * 100)

total_questions = 0
correct_count = 0
results = {"passages": []}

# 遍历每个 passage
for passage in passages:
    passage_number = passage.get("passage_number", 0)
    passage_content = passage.get("passage_content", "")
    questions = passage.get("questions", [])
    
    print(f"Processing Passage {passage_number} with {len(questions)} questions...")
    
    passage_results = {
        "passage_number": passage_number,
        "total_questions": len(questions),
        "correct_count": 0,
        "questions": []
    }
    
    # 简单的 passage 分析提示，尽量简洁
    passage_analysis_instructions = (
        "Please briefly analyze the passage. Focus on the main ideas, tone, structure, and key details."
    )
    
    for question in questions:
        question_number = question.get("question", "Unknown")
        question_type = question.get("question_type", "")
        options = question.get("options", [])
        correct_answer = question.get("correct_answer", "")
        
        print(f"  Processing question {question_number} ({question_type})...")
        total_questions += 1
        
        # 根据题型构造不同的提示信息
        if "Multiple-choice" in question_type and "Select One or More" not in question_type:
            # 单选题提示模板：要求模型在第一行严格给出 "FINAL ANSWER: X"
            prompt = (
                f"You are solving a GRE Reading Comprehension question.\n"
                f"Reading Passage:\n{passage_content}\n\n"
                f"{passage_analysis_instructions}\n"
                f"Question: {question_number}\n"
            )
            for option in options:
                prompt += f"{option}\n"
            prompt += (
                "\nProvide your final answer on the first line in EXACT format as follows:\n"
                "FINAL ANSWER: X\n"
                "Then, in one or two brief sentences, explain your reasoning."
            )
        
        elif "Multiple-choice" in question_type and "Select One or More" in question_type:
            # 多选题提示模板：要求模型在第一行严格给出 "FINAL ANSWERS: X, Y"
            prompt = (
                f"You are solving a GRE Reading Comprehension 'Select One or More' question.\n"
                f"Reading Passage:\n{passage_content}\n\n"
                f"{passage_analysis_instructions}\n"
                f"Question: {question_number}\n"
            )
            for option in options:
                prompt += f"{option}\n"
            prompt += (
                "\nProvide your final answers on the first line in EXACT format as follows:\n"
                "FINAL ANSWERS: X, Y\n"
                "Then, in one or two brief sentences, explain your reasoning."
            )
        
        elif "Select-in-Passage" in question_type:
            # 选句题提示模板：要求模型在第一行严格给出 "SELECTED SENTENCE: "exact sentence""
            prompt = (
                f"You are solving a GRE Reading Comprehension 'Select-in-Passage' question.\n"
                f"Reading Passage:\n{passage_content}\n\n"
                f"{passage_analysis_instructions}\n"
                f"Question: {question_number}\n\n"
                "Provide your selected sentence on the first line in EXACT format as follows:\n"
                'SELECTED SENTENCE: "exact sentence"\n'
                "Then, in one or two brief sentences, explain your reasoning."
            )
        else:
            print(f"  Skipping unknown question type: {question_type}")
            continue
        
        messages = [{"role": "user", "content": prompt}]
        
        response = ""
        is_correct = False
        models_tried = []
        best_answer = ""
        best_response = ""
        best_model = ""
        runtime = 0
        
        valid_sentences = []
        if "Select-in-Passage" in question_type:
            # 对于选句题，从 passage 中拆分出完整句子列表
            valid_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', passage_content)
            valid_sentences = [s.strip() for s in valid_sentences if s.strip()]
        
        available_models = [main_model] + backup_models
        for model in available_models:
            models_tried.append(model)
            start_time = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=120  # 针对阅读理解题目设置较长超时
                ).choices[0].message.content.strip()
                
                if "Multiple-choice" in question_type and "Select One or More" not in question_type:
                    answer = extract_mc_answer(response)
                    if answer:
                        current_is_correct = normalize_answer(answer) == normalize_answer(correct_answer)
                        if current_is_correct:
                            is_correct = True
                            best_answer = answer
                            best_response = response
                            best_model = model
                            runtime = time.perf_counter() - start_time
                            break
                        elif not best_answer:
                            best_answer = answer
                            best_response = response
                            best_model = model
                
                elif "Multiple-choice" in question_type and "Select One or More" in question_type:
                    answers = extract_multiple_mc_answers(response)
                    if answers:
                        if isinstance(correct_answer, str):
                            correct_answers = [normalize_answer(a) for a in re.findall(r'([A-E])', correct_answer)]
                        else:
                            correct_answers = [normalize_answer(a) for a in correct_answer]
                        correct_answers.sort()
                        current_is_correct = (
                            len(answers) == len(correct_answers) and
                            all(a == b for a, b in zip(answers, correct_answers))
                        )
                        if current_is_correct:
                            is_correct = True
                            best_answer = ", ".join(answers)
                            best_response = response
                            best_model = model
                            runtime = time.perf_counter() - start_time
                            break
                        elif not best_answer:
                            best_answer = ", ".join(answers)
                            best_response = response
                            best_model = model
                
                elif "Select-in-Passage" in question_type:
                    answer = extract_select_in_passage_answer(response, valid_sentences)
                    if answer:
                        answer_clean = re.sub(r'\s+', ' ', answer).strip()
                        correct_clean = re.sub(r'\s+', ' ', correct_answer).strip()
                        current_is_correct = (answer_clean == correct_clean)
                        if current_is_correct:
                            is_correct = True
                            best_answer = answer
                            best_response = response
                            best_model = model
                            runtime = time.perf_counter() - start_time
                            break
                        elif not best_answer:
                            best_answer = answer
                            best_response = response
                            best_model = model
                
            except Exception as e:
                print(f"  Error with {model} on question {question_number}: {e}")
            
            runtime = time.perf_counter() - start_time
        
        if is_correct:
            correct_count += 1
            passage_results["correct_count"] += 1
        
        question_result = {
            "question_number": question_number,
            "question_type": question_type,
            "expected": correct_answer,
            "models_tried": models_tried,
            "model_used": best_model,
            "model_answer": best_answer,
            "model_response": best_response,
            "runtime": round(runtime, 2),
            "correct": is_correct
        }
        passage_results["questions"].append(question_result)
    
    results["passages"].append(passage_results)

accuracy = correct_count / total_questions if total_questions > 0 else 0
results["total_questions"] = total_questions
results["correct_count"] = correct_count
results["accuracy"] = accuracy

print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct answers: {correct_count}/{total_questions}")
print("-" * 100)

output_file = "GRE_RC_questions_results_cot_modified.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")
