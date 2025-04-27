import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """标准化答案以便一致比较"""
    # 移除点和空格
    answer = re.sub(r'[.\s]', '', answer, flags=re.IGNORECASE)
    return answer.strip().upper()

def extract_option_answers(response):
    """从模型的回答中提取两个字母选项（A-F）"""
    # 首先查找'FINAL ANSWER:'格式
    final_line_match = re.search(r'FINAL\s+ANSWER\s*[:：]\s*([A-F])\s*,\s*([A-F])', response, re.IGNORECASE)
    if final_line_match:
        return [normalize_answer(final_line_match.group(1)), normalize_answer(final_line_match.group(2))]
    
    # 查找最简单的模式：两个带可选点的字母
    simple_pattern = r'([A-F])\.?\s*,?\s*([A-F])\.?'
    simple_match = re.search(simple_pattern, response, re.IGNORECASE)
    if simple_match:
        return [normalize_answer(simple_match.group(1)), normalize_answer(simple_match.group(2))]
    
    # 查找带句点的选项
    period_pattern = r'([A-F])\..*?([A-F])\.'
    period_match = re.search(period_pattern, response, re.IGNORECASE)
    if period_match:
        return [normalize_answer(period_match.group(1)), normalize_answer(period_match.group(2))]
    
    # 查找行首的选项
    line_pattern = r'(?:^|\n)([A-F])\.?.*?(?:^|\n)([A-F])\.?'
    line_match = re.search(line_pattern, response, re.IGNORECASE | re.MULTILINE)
    if line_match:
        return [normalize_answer(line_match.group(1)), normalize_answer(line_match.group(2))]
    
    # 查找中间有单词的选项
    word_pattern = r'([A-F])(?:\.|:)?\s+\S+.*?([A-F])(?:\.|:)?\s+\S+'
    word_match = re.search(word_pattern, response, re.IGNORECASE | re.DOTALL)
    if word_match:
        return [normalize_answer(word_match.group(1)), normalize_answer(word_match.group(2))]
    
    # 查找明确提及的选项
    explicit_pattern = r'(?:options|answers|choices).*?([A-F]).*?([A-F])'
    explicit_match = re.search(explicit_pattern, response, re.IGNORECASE | re.DOTALL)
    if explicit_match:
        return [normalize_answer(explicit_match.group(1)), normalize_answer(explicit_match.group(2))]
    
    # 最后手段：提取所有A-F字母，取前两个不同的
    all_options = re.findall(r'\b([A-F])\b', response, re.IGNORECASE)
    unique_options = []
    for opt in all_options:
        opt_norm = normalize_answer(opt)
        if opt_norm not in unique_options:
            unique_options.append(opt_norm)
            if len(unique_options) == 2:
                return unique_options
    
    # 如果找不到两个选项，返回已有的或空字符串
    while len(unique_options) < 2:
        unique_options.append("")
    
    return unique_options

def try_get_answer(model_name, messages, client, timeout=120, temperature=0.2):
    """尝试使用指定模型获取答案"""
    start_time = time.perf_counter()
    response = ""
    answers = ["", ""]
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            timeout=timeout,
            temperature=temperature
        ).choices[0].message.content.strip()
        
        # 提取答案
        answers = extract_option_answers(response)
        
    except Exception as e:
        print(f"  Error with model {model_name}: {e}")
    
    runtime = time.perf_counter() - start_time
    return response, answers, runtime

# 生成不同提示策略的函数
def generate_zero_shot_prompt(content, options):
    """生成零样本提示"""
    prompt = (
        "Please carefully read the following GRE sentence equivalence question and select the TWO correct answer options:\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    
    # 添加选项
    for key, value in options.items():
        prompt += f"{key}: {value}\n"
    
    prompt += "\nIMPORTANT: Your response MUST follow this EXACT format:\n"
    prompt += "Options: X, Y\n"
    prompt += "Explanation: Your explanation here\n\n"
    prompt += "Replace X and Y with the two correct option letters (e.g., A, C).\n"
    prompt += "Make sure to clearly indicate your two chosen options at the beginning of your response."
    
    return prompt

def generate_five_shot_prompt(content, options):
    """生成五样本提示"""
    five_shot_examples = (
        "Below are five examples of GRE sentence equivalence questions with two blanks. For each, ONLY the final answer is provided in EXACT format (do NOT include any additional explanation).\n\n"
        
        "Example 1:\n"
        "Question: The beauty of the scientific approach is that even when individual researchers do _____ bias or partiality, others can correct them using a framework of evidence on which everyone broadly agrees.\n"
        "Options:\n"
        "A: verreact to\n"
        "B: eviate from\n"
        "C: uccumb to\n"
        "D: ecoil from\n"
        "E: ield to\n"
        "F: hrink from\n"
        "Final Answer: C, E\n\n"
        
        "Example 2:\n"
        "Question: The reconstruct known work is beautiful and also probably _____: it is the only Hebrew verse written by a woman.\n"
        "Options:\n"
        "A: ingular\n"
        "B: nique\n"
        "C: rchaic\n"
        "D: counterfeit\n"
        "E: aluable\n"
        "F: ake\n"
        "Final Answer: A, B\n\n"
        
        "Example 3:\n"
        "Question: In a book that inclines to _____, an epilogue arguing that ballet is dead arrives simply as one more overstatement.\n"
        "Options:\n"
        "A: essimism\n"
        "B: isinterpretation\n"
        "C: mprecision\n"
        "D: agueness\n"
        "E: xaggeration\n"
        "F: yperbole\n"
        "Final Answer: E, F\n\n"
        
        "Example 4:\n"
        "Question: The political upheaval caught most people by surprise: despite the _____ warnings of some commentators, it had never seemed that imminent.\n"
        "Options:\n"
        "A: tern\n"
        "B: rescient\n"
        "C: rophetic\n"
        "D: ndifferent\n"
        "E: epeated\n"
        "F: pathetic\n"
        "Final Answer: B, C\n\n"
        
        "Example 5:\n"
        "Question: Members of the union's negotiating team insisted on several changes to the company's proposal before they would support it, making it clear that they would _____ no compromise.\n"
        "Options:\n"
        "A: isclose\n"
        "B: eject\n"
        "C: rook\n"
        "D: olerate\n"
        "E: epudiate\n"
        "F: eigh\n"
        "Final Answer: C, D\n\n"
    )
    
    prompt = (
        five_shot_examples +
        "Now, solve the following GRE sentence equivalence question and provide ONLY your final answer in EXACT format (e.g., 'X, Y') with no additional text:\n\n" +
        f"Question: {content}\n"
        "Options:\n"
    )
    for key, value in options.items():
        prompt += f"{key}: {value}\n"
    
    prompt += "\nFinal Answer:"
    
    return prompt

def generate_chain_of_thought_prompt(content, options):
    """生成思维链提示"""
    prompt = (
        "You are solving a GRE Sentence Equivalence question. Please read the question carefully and perform a step-by-step analysis. "
        "At the very beginning of your response, provide the final answer in EXACT format as follows:\n"
        "FINAL ANSWER: X, Y\n\n"
        "Question:\n"
        f"{content}\n\n"
        "Options:\n"
    )
    
    # 添加选项
    for key, value in options.items():
        prompt += f"{key}: {value}\n"
    
    prompt += (
        "\nPlease follow these steps in your analysis:\n"
        "1. Analyze the sentence structure, context, and keywords;\n"
        "2. Test each option by inserting it into the sentence to check if the sentence remains grammatically correct and retains equivalent meaning;\n"
        "3. Group options that yield equivalent meanings;\n"
        "4. Finally, choose two options and write the final answer in the first line in EXACT format: FINAL ANSWER: X, Y\n"
        "If you are unsure, please respond with 'No answer'.\n"
        "Then, provide your detailed explanation."
    )
    
    return prompt

def main():
    # 1. 加载JSON文件
    json_file = "/home/ltang24/Education/GRE verbal 2from6/GRE_Verbal_array_of_two_options_from_6_answers.json"
    with open(json_file, "r", encoding="utf-8") as f:
        all_questions = json.load(f)
    
    # 使用前100道题目确保能得到足够的有效回答
    questions = all_questions[:100]
    
    # 2. 定义模型和策略
    llama_models = ["gemini-1.5-flash"]
    strategies = ["zero-shot", "five-shot", "chain-of-thought"]
    
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
        
        # 处理问题直到达到50个有效回答
        for i, item in enumerate(questions):
            if processed_count >= 50:  # 当达到50个有效回答时停止
                break
                
            question_number = item.get("question_number")
            content = item.get("content")
            options = item.get("options")
            expected = item.get("answer")
            
            print(f"Processing question {i+1} (Q{question_number})...")
            
            # 标准化预期答案
            if isinstance(expected, str):
                # 处理答案是单个字符串的情况，如"A.B"
                expected_normalized = [part.strip() for part in re.findall(r'([A-F])', expected, re.IGNORECASE)]
            else:
                # 处理答案是列表的情况，如["A.", "B."]
                expected_normalized = [normalize_answer(e) for e in expected]
            
            # 排序预期答案以允许不同顺序
            expected_normalized.sort()
            
            # 根据策略生成提示
            if strategy == "zero-shot":
                prompt = generate_zero_shot_prompt(content, options)
            elif strategy == "five-shot":
                prompt = generate_five_shot_prompt(content, options)
            else:  # chain-of-thought
                prompt = generate_chain_of_thought_prompt(content, options)
            
            messages = [{"role": "user", "content": prompt}]
            
            # 尝试模型
            answer_found = False
            models_tried = []
            best_model = None
            best_response = None
            best_answers = ["", ""]
            is_correct = False
            runtime = 0
            
            # 依次尝试每个模型
            for model in llama_models:
                models_tried.append(model)
                print(f"  Trying model: {model}")
                
                response, answers, model_runtime = try_get_answer(
                    model, messages, client
                )
                
                # 排序答案以允许不同顺序
                answers.sort()
                
                # 检查是否提取到有效答案
                if all(a for a in answers):
                    answer_found = True
                    best_model = model
                    best_response = response
                    best_answers = answers
                    runtime = model_runtime
                    
                    # 检查是否正确
                    if (best_answers[0] == expected_normalized[0] and 
                        best_answers[1] == expected_normalized[1]):
                        is_correct = True
                    
                    break
            
            # 记录结果
            if answer_found:
                processed_count += 1
                
                if is_correct:
                    correct_count += 1
                    print(f"  ✓ Correct: {best_answers}")
                else:
                    print(f"  ✗ Incorrect: Model: {best_answers}, Expected: {expected_normalized}")
                
                details.append({
                    "question_number": question_number,
                    "expected": expected_normalized,
                    "models_tried": models_tried,
                    "model_used": best_model,
                    "model_answer": best_answers,
                    "model_response": best_response,
                    "runtime": round(runtime, 2),
                    "correct": is_correct
                })
            else:
                print(f"  ✗ No valid answer found from any model")
        
        # 计算准确率
        accuracy = correct_count / processed_count if processed_count > 0 else 0
        
        # 打印结果
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
    
    # 6. 保存综合结
    output_file = "gemini-1.5-flash_multi.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    
    print(f"\nTesting complete. Comprehensive results saved to: {output_file}")

if __name__ == "__main__":
    main()