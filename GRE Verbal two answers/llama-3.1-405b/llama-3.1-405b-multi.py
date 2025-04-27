import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    # 移除答案前缀和特殊字符
    answer = re.sub(r'^(answer\s*[12]?\s*[:：\-]?\s*)|[""''"\']', '', answer, flags=re.IGNORECASE)
    return answer.strip().lower().replace(' ', '')

def extract_answers(response):
    """提取两个答案并返回解释"""
    # 首先检查格式化好的答案模式
    final_answer_pattern = r'(?:final\s+answers?[:：]?|answers?[:：]?)\s*([a-zA-Z]+(?:\s+[a-zA-Z]+)?)[,，]\s*([a-zA-Z]+(?:\s+[a-zA-Z]+)?)'
    match = re.search(final_answer_pattern, response, re.IGNORECASE)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        return normalize_answer(ans1), normalize_answer(ans2), response
    
    # 从第一行提取（格式: "word1, word2"）
    first_line = response.split('\n')[0].strip() if response else ""
    if first_line and ',' in first_line:
        parts = first_line.split(',', 1)
        if len(parts) == 2:
            potential_ans1 = parts[0].strip()
            potential_ans2 = parts[1].strip()
            # 提取第二个答案中的第一个词（防止附带解释）
            potential_ans2 = re.match(r'([^\s]+(?:\s+[^\s]+)?)', potential_ans2)
            if potential_ans2:
                potential_ans2 = potential_ans2.group(1)
                if len(potential_ans1) < 30 and len(potential_ans2) < 30:
                    remaining_text = response[len(first_line):].strip()
                    return normalize_answer(potential_ans1), normalize_answer(potential_ans2), remaining_text
    
    # 寻找任何格式的 "word1, word2" 模式
    answer_pattern = r'([a-zA-Z]+(?:\s+[a-zA-Z]+)?),\s*([a-zA-Z]+(?:\s+[a-zA-Z]+)?)'
    match = re.search(answer_pattern, response)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        explanation = response[match.end():].strip()
        return normalize_answer(ans1), normalize_answer(ans2), explanation
    
    # 最后尝试：找到任何可能是答案的两个词
    words = re.findall(r'\b([a-zA-Z]+)\b', response)
    if len(words) >= 2:
        return normalize_answer(words[0]), normalize_answer(words[1]), ""
    
    return "", "", ""

def try_get_answer(model_name, messages, client, timeout=120, temperature=0.2):
    """尝试使用指定模型获取答案，返回回答、解析后的答案和运行时间"""
    start_time = time.perf_counter()
    response = ""
    ans1, ans2, explanation = "", "", ""
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            timeout=timeout,
            temperature=temperature
        ).choices[0].message.content.strip()
        
        # 提取答案
        ans1, ans2, explanation = extract_answers(response)
        
    except Exception as e:
        print(f"  Error with model {model_name}: {e}")
    
    runtime = time.perf_counter() - start_time
    return response, ans1, ans2, explanation, runtime

# 生成不同提示策略的函数
def generate_zero_shot_prompt(content, options):
    """生成零样本提示"""
    prompt = (
        "Please solve this GRE sentence equivalence question:\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    
    # 添加选项
    for key in sorted(options.keys()):
        prompt += f"{key.replace('Blank', 'Blank ')} options:\n"
        for opt in options[key]:
            prompt += f"- {opt}\n"
    
    prompt += "\nIMPORTANT: Your response must follow this EXACT format:\n"
    prompt += "word1, word2\n"
    prompt += "Explanation: Your explanation here\n\n"
    prompt += "The comma between answers is essential. Do not include any other text before the answers."
    
    return prompt

def generate_three_shot_prompt(content, options):
    """生成三样本提示"""
    three_shot_examples = (
        "Below are three examples of GRE sentence equivalence questions with two blanks. For each, only the final answer is provided.\n\n"
        "Example 1:\n"
        "Question: The (i)_____ of molecular oxygen on Earth-sized planets around other stars in the universe would not be (ii)_____ sign of life.\n"
        "Options for Blank(i): dearth; presumption; detection\n"
        "Options for Blank(ii): a controversial; an unambiguous; a possible\n"
        "Final Answer: detection, an unambiguous\n\n"
        
        "Example 2:\n"
        "Question: Given the (i)_____ the committees and the (ii)_____ nature of its investigation, it would be unreasonable to gainsay the committee's conclusions at first glance.\n"
        "Options for Blank(i): sterling reputation of; lack of finding of; ad hoc existence of\n"
        "Options for Blank(ii): superficial; spontaneous; exhaustive\n"
        "Final Answer: sterling reputation of, exhaustive\n\n"
        
        "Example 3:\n"
        "Question: The economic recovery was somewhat lopsided: (i)_____ in some of the industrial economies while (ii)_____ in others.\n"
        "Options for Blank(i): unexpected; feeble; swift\n"
        "Options for Blank(ii): robust; turbulent; predictable\n"
        "Final Answer: feeble, robust\n\n"
    )
    
    prompt = (
        three_shot_examples +
        "Now, solve the following GRE sentence equivalence question and provide ONLY your final answer in EXACT format (e.g., 'word1, word2'):\n\n" +
        f"Question: {content}\n"
    )
    for blank in sorted(options.keys()):
        prompt += f"{blank} options: " + "; ".join(options[blank]) + "\n"
    
    prompt += "\nFinal Answer:"
    
    return prompt

def generate_cot_prompt(content, options):
    """生成思维链提示"""
    prompt = (
        "Please solve this GRE sentence equivalence question step by step:\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    
    # 添加选项
    for key in sorted(options.keys()):
        prompt += f"{key.replace('Blank', 'Blank ')} options:\n"
        for opt in options[key]:
            prompt += f"- {opt}\n"
    
    prompt += "\nThink about this question in these steps:\n"
    prompt += "1. Understand the overall meaning and logical structure of the passage.\n"
    prompt += "2. Identify key words or transitions that signal the logical flow.\n"
    prompt += "3. For each blank, determine what type of word would maintain the passage's coherence.\n"
    prompt += "4. Select the best option for each blank independently.\n\n"
    prompt += "IMPORTANT: Your final answer must be in EXACTLY this format:\n"
    prompt += "word1, word2\n"
    prompt += "Explanation: Your brief explanation here\n\n"
    
    prompt += "Provide just the two words first, followed by your explanation. The comma between answers is essential."
    
    return prompt

def main():
    # 1. 加载JSON文件
    json_file = "/home/ltang24/Education/GRE Verbal two answers/GRE_Verbal_array_of_2_answers.json"
    with open(json_file, "r", encoding="utf-8") as f:
        all_questions = json.load(f)
    
    # 限制题目数量
    questions = all_questions[:100]  # 处理前100题，确保能够得到至少50个有答案的题目
    
    # 2. 定义模型和策略
    llama_models = ["llama-3.1-405b", "llama-3.1-70b", "llama-3.1-8b"]
    strategies = ["zero-shot", "three-shot", "chain-of-thought"]
    
    # 3. 初始化客户端
    client = Client()
    
    # 4. 结果存储
    all_results = {}
    
    # 5. 对每个策略运行测试
    for strategy in strategies:
        print(f"\n{'='*50}\nTesting Strategy: {strategy.upper()}\n{'='*50}")
        
        processed_count = 0
        correct_count = 0
        details = []
        
        # 处理问题
        for i, item in enumerate(questions):
            # 如果已经处理了50个有答案的题目，就停止
            if processed_count >= 50:
                break
                
            question_number = item.get("question_number")
            content = item.get("content")
            options = item.get("options")
            expected = item.get("answer")
            
            print(f"Processing question {i+1} (Q{question_number})...")
            
            # 根据策略生成提示
            if strategy == "zero-shot":
                prompt = generate_zero_shot_prompt(content, options)
            elif strategy == "three-shot":
                prompt = generate_three_shot_prompt(content, options)
            else:  # chain-of-thought
                prompt = generate_cot_prompt(content, options)
            
            messages = [{"role": "user", "content": prompt}]
            
            # 尝试使用不同模型获取答案
            answer_found = False
            models_tried = []
            best_model = None
            best_response = None
            best_ans1 = ""
            best_ans2 = ""
            best_explanation = ""
            runtime = 0
            is_correct = False
            
            for model in llama_models:
                models_tried.append(model)
                print(f"  Trying model: {model}")
                
                response, ans1, ans2, explanation, model_runtime = try_get_answer(
                    model, messages, client
                )
                
                # 检查是否成功提取到答案
                if ans1 and ans2:
                    answer_found = True
                    best_model = model
                    best_response = response
                    best_ans1 = ans1
                    best_ans2 = ans2
                    best_explanation = explanation
                    runtime = model_runtime
                    
                    # 检查答案是否正确
                    expected_normalized = [normalize_answer(e) for e in expected]
                    is_correct = (
                        (ans1 == expected_normalized[0] and ans2 == expected_normalized[1]) or
                        (ans1 == expected_normalized[1] and ans2 == expected_normalized[0])
                    )
                    
                    break
            
            # 如果找到答案，记录结果
            if answer_found:
                processed_count += 1
                
                details.append({
                    "question_number": question_number,
                    "expected": expected,
                    "models_tried": models_tried,
                    "model_used": best_model,
                    "model_answer": [best_ans1, best_ans2],
                    "model_explanation": best_explanation,
                    "model_response": best_response,
                    "runtime": round(runtime, 2),
                    "correct": is_correct
                })
                
                if is_correct:
                    correct_count += 1
                    print(f"  ✓ Correct ({best_ans1}, {best_ans2})")
                else:
                    print(f"  ✗ Incorrect (Model: [{best_ans1}, {best_ans2}], Expected: {expected})")
            else:
                print(f"  ✗ No answer found from any model")
        
        # 计算准确率
        accuracy = correct_count / processed_count if processed_count > 0 else 0
        
        print(f"\n{strategy.upper()} Strategy Results:")
        print(f"Questions with answers: {processed_count}")
        print(f"Accuracy: {accuracy:.2%}")
        print(f"Correct Answers: {correct_count}/{processed_count}")
        
        # 保存策略结果
        all_results[strategy] = {
            "accuracy": accuracy,
            "correct_count": correct_count,
            "total_questions_processed": processed_count,
            "details": details
        }
    
    # 6. 保存综合结果
    output_file = "GRE_Verbal_Two_Answers_Llama_Multi_Strategy_Results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    
    print(f"\nTesting complete. Comprehensive results saved to: {output_file}")

if __name__ == "__main__":
    main()