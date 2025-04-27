import json
import re
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison
    （中文注释：去除所有非字母数字字符，并转换为大写）
    """
    # 移除所有非字母数字字符（包括标点、空格等）
    answer = re.sub(r'[^\w]', '', answer)
    return answer.strip().upper()

def extract_answers(response):
    """Extract three answers from the model's response with improved parsing.
    （中文注释：使用正则表达式从模型回答中提取三个答案）
    """
    # 尝试匹配 "Final Answer:" 格式，允许答案包含空格
    final_answer_pattern = r'(?i)final\s*answer[:：\-]?\s*([a-zA-Z ]+)[,，]\s*([a-zA-Z ]+)[,，]\s*([a-zA-Z ]+)(?:\n|$)'
    match = re.search(final_answer_pattern, response)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        ans3 = match.group(3).strip()
        return [normalize_answer(ans1), normalize_answer(ans2), normalize_answer(ans3)]
    
    # 如果未匹配，则尝试从第一行以逗号分隔的格式提取
    first_line = response.split('\n')[0].strip() if response else ""
    if first_line and first_line.count(',') >= 2:
        parts = first_line.split(',')
        if len(parts) >= 3:
            ans1 = parts[0].strip()
            ans2 = parts[1].strip()
            ans3 = parts[2].strip()
            return [normalize_answer(ans1), normalize_answer(ans2), normalize_answer(ans3)]
    
    # Fallback: 尝试在整个回答中查找三个以逗号分隔的词组
    pattern = r'([a-zA-Z ]+),\s*([a-zA-Z ]+),\s*([a-zA-Z ]+)'
    match = re.search(pattern, response)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        ans3 = match.group(3).strip()
        return [normalize_answer(ans1), normalize_answer(ans2), normalize_answer(ans3)]
    
    return ["", "", ""]

# 1. Load JSON file（加载题目文件）
json_file = "/home/ltang24/Education/GRE verbal three answers/GRE_Verbal_array_of_3_answers.json"
with open(json_file, "r", encoding="utf-8") as f:
    all_questions = json.load(f)

# 2. Define main model and backup models (using only GPT models)
main_model = "gpt-4o"
backup_models = ["gpt-4", "gpt-4o-mini"]

# 3. Initialize client（初始化客户端）
client = Client()

print(f"Main Model: {main_model}")
print(f"Backup Models: {', '.join(backup_models)}")
print(f"Total questions in file: {len(all_questions)}")
print("Prompting Strategy: 5-shot (Final Answer Only, no explanation)")
print("-" * 100)

# 我们将遍历题库，直到获得50道有答案的题目
target_answered = 50
answered_count = 0
correct_count = 0
details = []
index = 0

# 定义5-shot示例（示例中只展示题目、选项及最终答案，无中间推理）
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
    "Question: Within the culture as a whole, the natural sciences have been so successful that the word “scientific” is often used in (i)_____ manner: it is often assumed that to call something “scientific” is to imply that its reliability has been (ii)_____ by methods whose results cannot reasonably be (iii)_____ .\n"
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

while answered_count < target_answered and index < len(all_questions):
    item = all_questions[index]
    index += 1  # 每处理一道题目，索引加1
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer")  # 预期答案为数组，例如 ["origin", "produce", "eaten"]
    
    print(f"Processing question {index} (Q{question_number})...")
    
    # 构造5-shot提示：示例 + 当前题目
    prompt = (
        five_shot_examples +
        "Now, solve the following GRE sentence equivalence question and provide ONLY your final answer in EXACT format (e.g., 'word1, word2, word3') with no additional text:\n\n" +
        f"Question: {content}\n"
    )
    for blank in sorted(options.keys()):
        prompt += f"{blank} options: " + "; ".join(options[blank]) + "\n"
    
    prompt += "\nFinal Answer:"
    
    messages = [{"role": "user", "content": prompt}]
    
    current_model = main_model
    response = ""
    is_correct = False
    models_tried = []
    best_answers = ["", "", ""]
    best_response = ""
    best_model = ""
    runtime = 0
    
    available_models = [main_model] + backup_models.copy()
    for model in available_models:
        models_tried.append(model)
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=120,
                temperature=0.2
            ).choices[0].message.content.strip()
            
            # 提取三个答案
            answers = extract_answers(response)
            expected_normalized = sorted([normalize_answer(e) for e in expected])
            
            if len(answers) == 3 and all(a != "" for a in answers):
                if sorted(answers) == expected_normalized:
                    is_correct = True
                best_answers = answers
            
        except Exception as e:
            print(f"Error with {model} on Q{question_number}: {e}")
            best_answers = ["", "", ""]
        
        runtime = time.perf_counter() - start_time
        
        if is_correct:
            best_model = model
            break
    
    if best_answers[0] and best_answers[1] and best_answers[2]:
        answered_count += 1
        if is_correct:
            correct_count += 1
            print(f"  ✓ Correct ({best_answers[0]}, {best_answers[1]}, {best_answers[2]})")
        else:
            print(f"  ✗ Incorrect (Model answer: {best_answers}, Expected: {expected})")
    else:
        print("  ✗ No answer provided by the model.")
    
    details.append({
        "question_number": question_number,
        "expected": sorted([normalize_answer(e) for e in expected]),
        "models_tried": models_tried,
        "model_used": best_model if best_model else current_model,
        "model_answer": best_answers if best_answers[0] and best_answers[1] and best_answers[2] else [],
        "model_response": best_response if best_response else response,
        "runtime": round(runtime, 2),
        "correct": is_correct if (best_answers[0] and best_answers[1] and best_answers[2]) else None
    })
    
    print("-" * 50)

if answered_count < target_answered:
    print(f"Only {answered_count} questions answered out of desired {target_answered}.")

final_accuracy = (correct_count / answered_count) if answered_count > 0 else 0
print(f"Overall Accuracy (only for answered questions): {final_accuracy:.2%}")
print(f"Answered Questions: {answered_count} (of {index} processed)")
print(f"Correct Answers: {correct_count}/{answered_count}")
print("-" * 100)

results = {
    "strategy": "5-shot",
    "accuracy": final_accuracy,
    "total_questions": index,
    "answered_questions": answered_count,
    "correct_count": correct_count,
    "details": details
}

output_file = "fiveshot.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")
