import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """标准化答案以便一致比较"""
    # 移除答案前缀和特殊字符
    answer = re.sub(r'^(answer\s*[123]?\s*[:：\-]?\s*)|[""''"\']', '', answer, flags=re.IGNORECASE)
    # 对于多词短语，保留空格但标准化
    return answer.strip().lower()

def extract_answers(response):
    """从模型的回答中提取三个答案"""
    # 首先尝试从第一行提取，通常只包含答案
    first_line = response.split('\n')[0].strip() if response else ""
    
    # 尝试简单的逗号分隔格式
    if ',' in first_line and first_line.count(',') >= 2:
        parts = first_line.split(',')
        if len(parts) >= 3:
            # 取前三项，忽略之后的内容
            ans1 = parts[0].strip()
            ans2 = parts[1].strip()
            # 对于第三个答案，在第一个非字母数字字符前停止
            ans3_match = re.match(r'([^,]+?)(?:\s+[^a-zA-Z0-9].*)?$', parts[2].strip())
            ans3 = ans3_match.group(1) if ans3_match else parts[2].strip()
            
            # 检查这些是否看起来像有效的答案（不是解释）
            if len(ans1) < 30 and len(ans2) < 30 and len(ans3) < 30:
                return [normalize_answer(ans1), normalize_answer(ans2), normalize_answer(ans3)]
    
    # 如果上面方法失败，尝试更复杂的模式匹配
    
    # 模式1: "Final Answer:"格式
    final_answer_pattern = r'(?i)final\s*answer[:：\-]?\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)[,，]\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)[,，]\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(final_answer_pattern, response)
    if match:
        return [normalize_answer(match.group(1)), normalize_answer(match.group(2)), normalize_answer(match.group(3))]
    
    # 模式2: 寻找三个用逗号分隔的词
    pattern1 = r'([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)\s*,\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)\s*,\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(pattern1, response)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        ans3 = match.group(3).strip()
        
        # 清理第三个答案，删除后面的非单词字符
        ans3_clean = re.match(r'([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)', ans3)
        if ans3_clean:
            ans3 = ans3_clean.group(1)
            
        return [normalize_answer(ans1), normalize_answer(ans2), normalize_answer(ans3)]
    
    # 模式3: 寻找编号答案
    pattern2 = r'(?:1\.?\s*|\(i\)\s*|\(1\)\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:2\.?\s*|\(ii\)\s*|\(2\)\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:3\.?\s*|\(iii\)\s*|\(3\)\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(pattern2, response, re.DOTALL)
    if match:
        return [normalize_answer(match.group(1)), normalize_answer(match.group(2)), normalize_answer(match.group(3))]
    
    # 模式4: 寻找空格特定答案
    pattern3 = r'(?:blank\s*\(?i\)?\s*|\(i\)\s*|first\s+blank\s*[:：]?\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:blank\s*\(?ii\)?\s*|\(ii\)\s*|second\s+blank\s*[:：]?\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:blank\s*\(?iii\)?\s*|\(iii\)\s*|third\s+blank\s*[:：]?\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(pattern3, response, re.DOTALL | re.IGNORECASE)
    if match:
        return [normalize_answer(match.group(1)), normalize_answer(match.group(2)), normalize_answer(match.group(3))]
    
    # 如果以上模式都不成功，查找频繁出现的词
    stopwords = ['the', 'and', 'for', 'blank', 'answer', 'first', 'second', 'third', 'explanation', 
                 'that', 'with', 'this', 'from', 'not', 'are', 'has', 'have', 'been', 'word', 'context']
    
    words = [word for word in re.findall(r'\b([a-zA-Z\-]+)\b', response) 
             if word.lower() not in stopwords and len(word) > 2]
    
    # 过滤出现在回答中的词
    if words:
        # 计算出现次数
        word_counts = {}
        for word in words:
            if word.lower() not in word_counts:
                word_counts[word.lower()] = 1
            else:
                word_counts[word.lower()] += 1
        
        # 获取出现频率最高的3个词
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_words) >= 3:
            return [sorted_words[0][0], sorted_words[1][0], sorted_words[2][0]]
    
    return ["", "", ""]

def try_get_answer(model_name, messages, client, timeout=120, temperature=0.2):
    """尝试使用指定模型获取答案，返回回答和解析后的答案"""
    start_time = time.perf_counter()
    response = ""
    answers = ["", "", ""]
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            timeout=timeout,
            temperature=temperature
        ).choices[0].message.content.strip()
        
        # 提取答案
        answers = extract_answers(response)
        
    except Exception as e:
        print(f"  Error with model {model_name}: {e}")
    
    runtime = time.perf_counter() - start_time
    return response, answers, runtime

# 创建三种不同的提示生成函数
def generate_zero_shot_prompt(content, options):
    """生成普通提示（零样本）"""
    prompt = (
        "Please carefully read the following GRE text completion question and provide the three correct answers:\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    
    # 添加选项
    for key in sorted(options.keys()):
        prompt += f"{key}:\n"
        for opt in options[key]:
            prompt += f"- {opt}\n"
    
    prompt += "\nIMPORTANT: Your response MUST follow this EXACT format:\n"
    prompt += "answer1, answer2, answer3\n"
    prompt += "Explanation: Your explanation here\n\n"
    prompt += "Make sure to separate your three answers with commas and place them on their own line at the beginning of your response.\n"
    prompt += "Do NOT include any extra words or punctuation with the answers.\n"
    prompt += "Provide your explanation on a separate line after the answers."
    
    return prompt

def generate_five_shot_prompt(content, options):
    """生成五样本提示"""
    five_shot_examples = (
        "Below are five examples of GRE sentence equivalence questions with three blanks. For each, ONLY the final answer is provided in EXACT format (do NOT include any additional text).\n\n"
        
        "Example 1:\n"
        "Question: The skin of the poison dart frog contains deadly poisons called batrachotoxins. But the (i)_____ of the toxins has remained an enigma, as the frog does not (ii)_____ them. Now an analysis suggests that the melyrid beetle is the source. Collected beetle specimens all contained batrachotoxins, suggesting that these beetles are (iii)_____ by the frogs.\n"
        "Options for Blank(i): effect; presumption; origin\n"
        "Options for Blank(ii): pressure; produce; suffer from\n"
        "Options for Blank(iii): eaten; neutralized; poisoned\n"
        "Final Answer: origin, produce, eaten\n\n"
        
        "Example 2:\n"
        "Question: Now that photographic prints have become a popular field for collecting, auctions are becoming more (i)_____. It is not just the entry of new collectors into the field that is causing this intensification. Established collectors' interests are also becoming more (ii)_____. Those who once concentrated on the work of either the nineteenth-century pioneers or the twentieth-century modernists are now keen to have (iii)_____ collections.\n"
        "Options for Blank(i): competitive; tedious; exclusive\n"
        "Options for Blank(ii): fickle; wide-ranging; antiquarian\n"
        "Options for Blank(iii): comprehensive; legitimate; impressive\n"
        "Final Answer: competitive, wide-ranging, comprehensive\n\n"
        
        "Example 3:\n"
        "Question: Most capuchin monkey conflict involves such a (i)_____ repertoire of gestural and vocal signals that it is difficult for researchers to tease apart the meanings of the individual signals. This (ii)_____ is (iii)_____ by the fact that many signals seem to shift in meaning according to the context in which they are produced and the developmental stage of the individuals producing them.\n"
        "Options for Blank(i): precise; rich; straightforward\n"
        "Options for Blank(ii): problem; opportunity; oversight\n"
        "Options for Blank(iii): augmented; ameliorated; anticipated\n"
        "Final Answer: rich, problem, augmented\n\n"
        
        "Example 4:\n"
        "Question: Within the culture as a whole, the natural sciences have been so successful that the word 'scientific' is often used in (i)_____ manner: it is often assumed that to call something 'scientific' is to imply that its reliability has been (ii)_____ by methods whose results cannot reasonably be (iii)_____ .\n"
        "Options for Blank(i): an ironic; a literal; an honorific\n"
        "Options for Blank(ii): maligned; challenged; established\n"
        "Options for Blank(iii): exaggerated; anticipated; disputed\n"
        "Final Answer: an honorific, established, disputed\n\n"
        
        "Example 5:\n"
        "Question: In 1998, observations of a (i)____________ in the growth of atmospheric methane, a potent greenhouse gas, suggested that many of the scenarios for global warming provided in a 1995 assessment may have been overly (ii)____________. Celebration was, however, premature: subsequent research has established that the observed phenomena were likely caused by (iii)____________ declines in industrial and natural emissions.\n"
        "Options for Blank(i): spike; slowdown; fluctuation\n"
        "Options for Blank(ii): gloomy; detailed; ambitious\n"
        "Options for Blank(iii): massive; persistent; temporary\n"
        "Final Answer: slowdown, gloomy, temporary\n\n"
    )
    
    prompt = (
        five_shot_examples +
        "Now, solve the following GRE text completion question and provide ONLY your final answer in EXACT format (e.g., 'word1, word2, word3') with no additional text:\n\n" +
        f"Question: {content}\n"
    )
    for blank in sorted(options.keys()):
        prompt += f"{blank} options: " + "; ".join(options[blank]) + "\n"
    
    prompt += "\nFinal Answer:"
    
    return prompt

def generate_chain_of_thought_prompt(content, options):
    """生成思维链提示"""
    prompt = (
        "Please solve this GRE Text Completion question step by step:\n\n"
        f"Passage: {content}\n"
        "Options:\n"
    )
    
    # 添加选项
    for key in sorted(options.keys()):
        prompt += f"{key}:\n"
        for opt in options[key]:
            prompt += f"- {opt}\n"
    
    prompt += "\nThink briefly about this question:\n"
    prompt += "1. Understand the overall meaning and logical flow of the passage.\n"
    prompt += "2. Identify key words or transitions that signal relationships between ideas.\n"
    prompt += "3. For each blank, determine what meaning would fit logically and grammatically.\n\n"
    
    prompt += "IMPORTANT: Your final answer must be in EXACTLY this format:\n"
    prompt += "answer1, answer2, answer3\n"
    prompt += "Explanation: Your brief explanation here\n\n"
    
    prompt += "Provide just the three answers first on their own line, separated by commas, then your explanation."
    
    return prompt

def main():
    # 1. 加载JSON文件
    json_file = "/home/ltang24/Education/GRE verbal three answers/GRE_Verbal_array_of_3_answers.json"
    with open(json_file, "r", encoding="utf-8") as f:
        all_questions = json.load(f)
    
    # 限制题目数量 - 使用前100题确保能得到足够的有效回答
    questions = all_questions[:100]
    
    # 2. 定义模型和策略
    llama_models = ["command-r"]
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
            best_answers = ["", "", ""]
            is_correct = False
            runtime = 0
            
            # 依次尝试每个模型
            for model in llama_models:
                models_tried.append(model)
                print(f"  Trying model: {model}")
                
                response, answers, model_runtime = try_get_answer(
                    model, messages, client
                )
                
                # 检查是否提取到有效答案
                if all(a for a in answers):
                    answer_found = True
                    best_model = model
                    best_response = response
                    best_answers = answers
                    runtime = model_runtime
                    
                    # 标准化预期答案
                    expected_normalized = [normalize_answer(e) for e in expected]
                    
                    # 检查是否正确（顺序必须匹配）
                    if (best_answers[0] == expected_normalized[0] and
                        best_answers[1] == expected_normalized[1] and
                        best_answers[2] == expected_normalized[2]):
                        is_correct = True
                    
                    break
            
            # 记录结果
            if answer_found:
                processed_count += 1
                
                if is_correct:
                    correct_count += 1
                    print(f"  ✓ Correct: {best_answers}")
                else:
                    print(f"  ✗ Incorrect: Model: {best_answers}, Expected: {expected}")
                
                details.append({
                    "question_number": question_number,
                    "expected": expected,
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
    
    # 6. 保存综合结果
    output_file = "command-r_multi.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    
    print(f"\nTesting complete. Comprehensive results saved to: {output_file}")

if __name__ == "__main__":
    main()