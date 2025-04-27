import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """标准化答案以便一致比较"""
    # 移除点和空格
    answer = re.sub(r'[.\s]', '', answer, flags=re.IGNORECASE)
    return answer.strip().upper()

def extract_mc_answer(response):
    """从模型回答中提取多选题的单个选项（A-E）"""
    # 查找明确的答案格式，如 "Answer: X" 或 "The answer is X"
    explicit_pattern = r'(?:answer|option|choice|final\s*answer)(?:is|:|\s)\s*([A-E])'
    explicit_match = re.search(explicit_pattern, response, re.IGNORECASE)
    if explicit_match:
        return normalize_answer(explicit_match.group(1))
    
    # 查找独立的选项答案，例如 "A." 或 "A)"
    standalone_pattern = r'\b([A-E])\.(?!\w)'
    standalone_match = re.search(standalone_pattern, response, re.IGNORECASE)
    if standalone_match:
        return normalize_answer(standalone_match.group(1))
    
    # 查找行首的选项
    line_pattern = r'(?:^|\n)\s*([A-E])[\.\s)]'
    line_match = re.search(line_pattern, response, re.IGNORECASE)
    if line_match:
        return normalize_answer(line_match.group(1))
    
    # 最后尝试查找任何可能的选项
    all_options = re.findall(r'\b([A-E])\b', response, re.IGNORECASE)
    if all_options:
        return normalize_answer(all_options[0])
    
    return ""

def extract_select_in_passage_answer(response, valid_sentences):
    """从回答中提取选取的句子（针对 select-in-passage 类型）"""
    # 先尝试匹配 "Selected Sentence: " 格式
    selected_pattern = r'Selected\s+Sentence\s*:\s*"([^"]+)"'
    selected_match = re.search(selected_pattern, response, re.IGNORECASE)
    if selected_match:
        selected_text = selected_match.group(1).strip()
        for sentence in valid_sentences:
            clean_sentence = re.sub(r'\s+', ' ', sentence).strip()
            # 比较选择的文本和有效句子
            if clean_sentence == selected_text or (
                len(selected_text) > 10 and 
                (selected_text in clean_sentence or clean_sentence in selected_text)
            ):
                return sentence
    
    # 尝试匹配引号中的内容
    quote_pattern = r'"([^"]+)"'
    quote_matches = re.findall(quote_pattern, response)
    
    for quote in quote_matches:
        clean_quote = re.sub(r'\s+', ' ', quote).strip()
        if len(clean_quote) < 5:  # 忽略太短的引号内容
            continue
            
        for sentence in valid_sentences:
            clean_sentence = re.sub(r'\s+', ' ', sentence).strip()
            # 完全匹配或部分重叠
            if clean_sentence == clean_quote or (
                len(clean_quote) > 10 and 
                (clean_quote in clean_sentence or clean_sentence in clean_quote)
            ):
                return sentence
    
    # 在整个响应中搜索有效句子
    response_clean = re.sub(r'\s+', ' ', response)
    for sentence in valid_sentences:
        clean_sentence = re.sub(r'\s+', ' ', sentence).strip()
        if clean_sentence in response_clean:
            return sentence
    
    # 基于单词重叠的匹配方法
    max_overlap = 0
    best_match = ""
    for sentence in valid_sentences:
        sentence_words = set(re.findall(r'\b\w+\b', sentence.lower()))
        if not sentence_words:  # 如果句子没有有效单词，跳过
            continue
            
        response_words = set(re.findall(r'\b\w+\b', response.lower()))
        overlap = len(sentence_words.intersection(response_words))
        overlap_ratio = overlap / len(sentence_words)
        
        if overlap > max_overlap and overlap_ratio > 0.5:  # 至少需要50%的单词重叠
            max_overlap = overlap
            best_match = sentence
    
    return best_match

def try_get_answer(model_name, messages, question_type, valid_sentences=None, timeout=120, client=None, temperature=0.2):
    """尝试使用指定模型获取答案，返回回答、答案和运行时间"""
    start_time = time.perf_counter()
    response = ""
    answer = ""
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            timeout=timeout,
            temperature=temperature
        ).choices[0].message.content.strip()
        
        # 提取答案
        if "Multiple-choice" in question_type:
            answer = extract_mc_answer(response)
        elif "Select-in-Passage" in question_type:
            answer = extract_select_in_passage_answer(response, valid_sentences)
        
    except Exception as e:
        print(f"  Error with model {model_name}: {e}")
    
    runtime = time.perf_counter() - start_time
    return response, answer, runtime

# 生成不同提示策略的函数
def generate_zero_shot_prompt(passage_content, question_text, options, question_type):
    """生成零样本提示"""
    if "Multiple-choice" in question_type:
        prompt = (
            f"Please carefully analyze the following reading passage and answer the question. Choose one correct option from the provided choices.\n\n"
            f"Reading Passage:\n{passage_content}\n\n"
            f"Question: {question_text}\n"
        )
        
        # 添加选项
        for option in options:
            prompt += f"{option}\n"
        
        prompt += "\nIMPORTANT: Your response MUST include the correct answer letter in this format:\n"
        prompt += "Answer: X\n"
        prompt += "Explanation: Your detailed explanation here\n\n"
        prompt += "Replace X with the correct option letter (e.g., A).\n"
        prompt += "Be sure to justify your answer with specific evidence from the passage."
    
    elif "Select-in-Passage" in question_type:
        prompt = (
            f"Please carefully analyze the following reading passage and answer the select-in-passage question.\n\n"
            f"Reading Passage:\n{passage_content}\n\n"
            f"Question: {question_text}\n\n"
            f"IMPORTANT: For this question, you need to select the exact sentence from the passage that best answers the question. "
            f"In your response, please include the following:\n\n"
            f"Selected Sentence: \"Copy and paste the EXACT sentence from the passage that answers the question.\"\n"
            f"Explanation: Explain why this sentence answers the question.\n\n"
            f"Make sure to use quotation marks around the selected sentence and copy it exactly as it appears in the passage."
        )
    
    return prompt

def generate_five_shot_prompt(passage_content, question_text, options, question_type):
    """生成五样本提示"""
    # 多选题的 5-shot 示例
    five_shot_mc = """Example 1:
Reading Passage:
"Social learning in fish has been observed in various species."
Question: What is the primary focus of the passage?
Options:
A. The failure of social learning
B. A study on social learning in fish
C. The natural habitat of fish
D. The comparison of fish species
E. None of the above
Answer: B
Explanation: The passage discusses evidence of social learning in fish.

Example 2:
Reading Passage:
"Studies show that the social environment impacts foraging behavior in guppies."
Question: What variable was manipulated in the study?
Options:
A. Water temperature
B. Group density
C. Food quantity
D. Light exposure
E. Tank size
Answer: B
Explanation: The study varied group density to observe its effect on foraging.

Example 3:
Reading Passage:
"Experimental findings indicate that fish raised in smaller groups locate food faster."
Question: What is the key finding of the study?
Options:
A. Larger groups lead to faster learning.
B. Smaller groups lead to faster food location.
C. Food quantity is the main factor.
D. The study was inconclusive.
E. None of the above.
Answer: B
Explanation: The result clearly shows that smaller groups perform better in foraging.

Example 4:
Reading Passage:
"Social learning is a well-documented phenomenon in aquatic species."
Question: What does the passage primarily describe?
Options:
A. A failure of social learning
B. The benefits of social learning in fish
C. A comparison between species
D. The natural environment of fish
E. An unrelated topic
Answer: B
Explanation: The passage emphasizes the role and benefits of social learning.

Example 5:
Reading Passage:
"Research in controlled environments suggests that early social interactions enhance learning."
Question: What does the study imply about social interactions?
Options:
A. They hinder learning.
B. They have no effect on learning.
C. They enhance learning.
D. They are detrimental to development.
E. They are irrelevant.
Answer: C
Explanation: The study concludes that early social interactions improve learning outcomes.
"""

    # Select-in-passage 类型的 5-shot 示例
    five_shot_select = """Example 1:
Reading Passage:
"Although many studies exist, few have considered the impact of social context on learning."
Question: Select the sentence that explains the effect of social context.
Answer: "Few have considered the impact of social context on learning."
Explanation: This sentence directly addresses the effect of social context.

Example 2:
Reading Passage:
"Research indicates that isolation can impair social learning significantly."
Question: Select the sentence that identifies the impact of isolation.
Answer: "Isolation can impair social learning significantly."
Explanation: The sentence explicitly states the effect of isolation.

Example 3:
Reading Passage:
"Studies reveal that early social interactions are crucial for cognitive development."
Question: Select the sentence that highlights the importance of early interactions.
Answer: "Early social interactions are crucial for cognitive development."
Explanation: It clearly points out the significance of early interactions.

Example 4:
Reading Passage:
"Experimental evidence suggests that group size influences learning efficiency."
Question: Select the sentence that discusses group size's effect on learning.
Answer: "Group size influences learning efficiency."
Explanation: The sentence focuses on the relationship between group size and learning.

Example 5:
Reading Passage:
"Data shows that consistent social engagement is linked to improved problem-solving skills."
Question: Select the sentence that connects social engagement with cognitive skills.
Answer: "Consistent social engagement is linked to improved problem-solving skills."
Explanation: The sentence makes a clear connection between engagement and cognitive outcomes.
"""

    if "Multiple-choice" in question_type:
        prompt = five_shot_mc + "\n---\n"
        prompt += "Now, answer the following question based on the reading passage.\n\n"
        prompt += f"Reading Passage:\n{passage_content}\n\n"
        prompt += f"Question: {question_text}\n"
        for option in options:
            prompt += f"{option}\n"
        prompt += "\nIMPORTANT: Your response MUST include the correct answer letter in this format:\n"
        prompt += "Answer: X\n"
        prompt += "Explanation: Your detailed explanation here\n\n"
        prompt += "Replace X with the correct option letter (e.g., A).\n"
        prompt += "Be sure to justify your answer with specific evidence from the passage."
    
    elif "Select-in-Passage" in question_type:
        prompt = five_shot_select + "\n---\n"
        prompt += "Now, answer the following select-in-passage question based on the reading passage.\n\n"
        prompt += f"Reading Passage:\n{passage_content}\n\n"
        prompt += f"Question: {question_text}\n\n"
        prompt += "IMPORTANT: For this question, you need to select the EXACT sentence from the passage that best answers the question.\n"
        prompt += "In your response, include:\n"
        prompt += "Selected Sentence: \"Copy and paste the EXACT sentence from the passage that answers the question.\"\n"
        prompt += "Explanation: Explain why this sentence answers the question.\n\n"
        prompt += "Make sure to use quotation marks around the selected sentence and copy it exactly as it appears in the passage."
    
    return prompt

def generate_chain_of_thought_prompt(passage_content, question_text, options, question_type):
    """生成思维链提示"""
    passage_analysis_instructions = (
        "Please briefly analyze the passage. Focus on the main ideas, tone, structure, and key details."
    )
    
    if "Multiple-choice" in question_type:
        prompt = (
            f"You are solving a GRE Reading Comprehension question using step-by-step analysis.\n"
            f"Reading Passage:\n{passage_content}\n\n"
            f"{passage_analysis_instructions}\n"
            f"Question: {question_text}\n"
        )
        for option in options:
            prompt += f"{option}\n"
        prompt += (
            "\nFollow these steps to answer the question:\n"
            "1. Identify what the question is asking for\n"
            "2. Locate the relevant information in the passage\n"
            "3. Evaluate each option based on the passage content\n"
            "4. Eliminate incorrect options and select the best answer\n\n"
            "Provide your final answer on the first line in EXACT format as follows:\n"
            "FINAL ANSWER: X\n"
            "Then explain your reasoning, analyzing why your choice is correct and why the other options are incorrect."
        )
    
    elif "Select-in-Passage" in question_type:
        prompt = (
            f"You are solving a GRE Reading Comprehension 'Select-in-Passage' question using step-by-step analysis.\n"
            f"Reading Passage:\n{passage_content}\n\n"
            f"{passage_analysis_instructions}\n"
            f"Question: {question_text}\n\n"
            "Follow these steps to select the correct sentence:\n"
            "1. Identify what the question is asking for\n"
            "2. Scan the passage for sentences that address this specific point\n"
            "3. Evaluate each potential sentence based on how directly it answers the question\n"
            "4. Choose the most relevant sentence from the passage\n\n"
            "Provide your selected sentence on the first line in EXACT format as follows:\n"
            'SELECTED SENTENCE: "exact sentence from the passage"\n'
            "Then explain why this sentence best answers the question."
        )
    
    return prompt

def main():
    # 1. 加载 JSON 文件
    json_file = "/home/ltang24/Education/GRE RC/GRE_RC_questions.json"
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. 定义模型和策略
    llama_models = ["command-r"]
    strategies = ["zero-shot", "five-shot", "chain-of-thought"]
    
    # 3. 初始化客户端
    client = Client()
    
    # 4. 限制 passage 数量，确保获得足够的有效回答
    passage_limit = 50
    passages = data["passages"][:passage_limit]
    
    # 5. 结果存储
    all_results = {}
    
    # 6. 对每个策略运行测试
    for strategy in strategies:
        print(f"\n{'='*50}\nTesting Strategy: {strategy.upper()}\n{'='*50}")
        
        processed_count = 0
        correct_count = 0
        details = []
        passage_stats = {}
        
        # 处理问题直到达到50个有效回答
        for passage in passages:
            if processed_count >= 50:  # 当达到50个有效回答时停止
                break
                
            passage_number = passage.get("passage_number", 0)
            passage_content = passage.get("passage_content", "")
            questions = passage.get("questions", [])
            
            print(f"Processing Passage {passage_number} with {len(questions)} questions...")
            
            # 初始化当前 passage 的统计信息
            passage_stats[passage_number] = {
                "total_questions": len(questions),
                "answered_questions": 0,
                "correct_count": 0
            }
            
            for question in questions:
                question_text = question.get("question", "Unknown")
                question_type = question.get("question_type", "")
                options = question.get("options", [])
                correct_answer = question.get("correct_answer", "")
                
                print(f"  Processing question {question_text} ({question_type})...")
                
                # 跳过不支持的问题类型
                if "Multiple-choice" not in question_type and "Select-in-Passage" not in question_type:
                    print(f"  Skipping unknown question type: {question_type}")
                    continue
                
                # 针对 select-in-passage 类型，简单句子切分
                valid_sentences = []
                if "Select-in-Passage" in question_type:
                    valid_sentences = re.split(r'(?<=[.!?])\s+', passage_content)
                    valid_sentences = [s.strip() for s in valid_sentences if s.strip()]
                
                # 根据策略生成提示
                if strategy == "zero-shot":
                    prompt = generate_zero_shot_prompt(passage_content, question_text, options, question_type)
                elif strategy == "five-shot":
                    prompt = generate_five_shot_prompt(passage_content, question_text, options, question_type)
                else:  # chain-of-thought
                    prompt = generate_chain_of_thought_prompt(passage_content, question_text, options, question_type)
                
                messages = [{"role": "user", "content": prompt}]
                
                # 尝试模型
                answer_found = False
                models_tried = []
                best_model = None
                best_response = None
                best_answer = ""
                is_correct = False
                runtime = 0
                
                # 依次尝试每个模型
                for model in llama_models:
                    models_tried.append(model)
                    print(f"  Trying model: {model}")
                    
                    response, answer, model_runtime = try_get_answer(
                        model, messages, question_type, valid_sentences, client=client
                    )
                    
                    # 检查是否提取到有效答案
                    if answer:
                        answer_found = True
                        best_model = model
                        best_response = response
                        best_answer = answer
                        runtime = model_runtime
                        
                        # 检查是否正确
                        if "Multiple-choice" in question_type:
                            if normalize_answer(best_answer) == normalize_answer(correct_answer):
                                is_correct = True
                        elif "Select-in-Passage" in question_type:
                            clean_answer = re.sub(r'\s+', ' ', best_answer).strip()
                            clean_correct = re.sub(r'\s+', ' ', correct_answer).strip()
                            if clean_answer == clean_correct:
                                is_correct = True
                        
                        break
                
                # 记录结果
                if answer_found:
                    processed_count += 1
                    passage_stats[passage_number]["answered_questions"] += 1
                    
                    if is_correct:
                        correct_count += 1
                        passage_stats[passage_number]["correct_count"] += 1
                        print(f"  ✓ Correct: {best_answer}")
                    else:
                        print(f"  ✗ Incorrect: Model: {best_answer}, Expected: {correct_answer}")
                    
                    details.append({
                        "passage_number": passage_number,
                        "question_text": question_text,
                        "question_type": question_type,
                        "expected": correct_answer,
                        "models_tried": models_tried,
                        "model_used": best_model,
                        "model_answer": best_answer,
                        "model_response": best_response,
                        "runtime": round(runtime, 2),
                        "correct": is_correct
                    })
                else:
                    print(f"  ✗ No valid answer found from any model")
        
        # 计算准确率
        accuracy = correct_count / processed_count if processed_count > 0 else 0
        
        # 计算每个passage的准确率 - 只考虑有答案的passage
        valid_passages = 0
        passage_correct = 0
        passage_answered = 0
        
        for p_num, stats in passage_stats.items():
            if stats["answered_questions"] > 0:
                valid_passages += 1
                passage_answered += stats["answered_questions"]
                passage_correct += stats["correct_count"]
        
        # 只计算有回答问题的passage的整体准确率
        passage_accuracy = passage_correct / passage_answered if passage_answered > 0 else 0
        
        # 打印结果
        print(f"\n{strategy.upper()} Strategy Results:")
        print(f"Questions with answers: {processed_count}")
        print(f"Accuracy: {accuracy:.2%}")
        print(f"Correct Answers: {correct_count}/{processed_count}")
        print(f"Valid Passages: {valid_passages}")
        print(f"Passage Accuracy: {passage_accuracy:.2%} ({passage_correct}/{passage_answered})")
        
        # 保存策略结果
        all_results[strategy] = {
            "accuracy": accuracy,
            "correct_count": correct_count,
            "total_questions_processed": processed_count,
            "passage_accuracy": passage_accuracy,
            "valid_passages": valid_passages,
            "passage_stats": passage_stats,
            "details": details
        }
    
    # 7. 保存综合结果
    output_file = "command-r_multi.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    
    print(f"\nTesting complete. Comprehensive results saved to: {output_file}")

if __name__ == "__main__":
    main()