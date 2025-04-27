import os
import re
import json
import time
import base64
from g4f.client import Client
from PIL import Image

# ----- Helper Functions -----

def encode_image_to_base64(image_path):
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def normalize_answer(answer):
    """Normalize answer by removing spaces, converting to lowercase, and keeping only alphanumeric characters"""
    return re.sub(r'[^a-zA-Z0-9]', '', answer).upper()

def extract_answer(response):
    """
    Extract the final answer from the model's response for multiple_choice_single question type.
    """
    # Try to extract using "Answer: X" format first
    answer_pattern = re.search(r'Answer:\s*([A-Ea-e])', response)
    if answer_pattern:
        return answer_pattern.group(1).upper()
    
    # Try to find a clear statement with a single letter
    match = re.search(r'\b(option|answer|choice|select)\s+([A-Ea-e])\b', response.lower())
    if match:
        return match.group(2).upper()
    
    # Otherwise, find the last standalone letter mentioned
    letters = re.findall(r'\b[A-Ea-e]\b', response)
    return letters[-1].upper() if letters else ""

# ---- Prompting Strategy ----

def generate_zero_shot_prompt():
    """Generate a zero-shot prompt for multiple_choice_single question type"""
    return ("Please analyze the GRE math question in the image and select the best answer choice. "
            "Provide only your final answer in the format 'Answer: X', where X is a single letter (A, B, C, D, or E).")

def generate_cot_prompt():
    """Generate a chain-of-thought prompt for multiple_choice_single question type"""
    return ("Please solve the GRE math question in the image step-by-step. "
            "Show your reasoning process clearly, then provide your final answer. "
            "After your reasoning, conclude with 'Answer: X', "
            "where X is a single letter (A, B, C, D, or E) representing the correct answer choice.")

def generate_few_shot_prompt():
    """Generate a few-shot prompt with examples for multiple_choice_single question type"""
    return (
        "Here are some examples of how to solve GRE multiple-choice questions:\n\n"
        "Example 1:\n"
        "For a question asking to solve 3x + 2 = 11, I would calculate:\n"
        "3x + 2 = 11\n"
        "3x = 9\n"
        "x = 3\n"
        "Looking at the options, if the answer is C, I'd write: Answer: C\n\n"
        "Example 2:\n"
        "For a probability question about selecting 2 red balls from 3 red and 4 blue balls, I'd calculate:\n"
        "Total ways to select 2 balls = C(7,2) = 21\n"
        "Ways to select 2 red balls = C(3,2) = 3\n"
        "Probability = 3/21 = 1/7\n"
        "If option D matches 1/7, I'd write: Answer: D\n\n"
        "Now, please solve the GRE math question in the image. Analyze the problem step-by-step and provide the correct answer choice as a single letter in the format 'Answer: X'"
    )

def get_prompt_messages(prompt_style, base64_image):
    """Generate the appropriate prompt messages based on style for multiple_choice_single questions"""
    if prompt_style == "zeroshot":
        text = generate_zero_shot_prompt()
    elif prompt_style == "cot":
        text = generate_cot_prompt()
    elif prompt_style == "fiveshot":
        text = generate_few_shot_prompt()
    else:
        text = "Please analyze this GRE math question and provide your answer in the format 'Answer: X'."
    
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ]

# ----- Main Process -----

def main():
    # 只使用这三个模型
    models = ["gpt-4", "gpt-4o", "gpt-4o-mini"]
    prompt_styles = ["zeroshot", "cot", "fiveshot"]
    
    client = Client()
    
    # 加载问题数据
    json_file_path = "/home/ltang24/Education/GRE Math Medium/gre_math_categorized.json"
    
    # 如果文件路径不正确，可能需要调整
    if not os.path.exists(json_file_path):
        print(f"Error: JSON file not found at {json_file_path}")
        print("Please enter the correct path to your GRE Math Medium JSON file:")
        json_file_path = input().strip()
    
    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        all_questions = data["GRE Math Medium.json"]
    
    # 只筛选multiple_choice_single类型的问题
    questions_data = [q for q in all_questions if q.get("question_type") == "multiple_choice_single"]
    
    print(f"Found {len(questions_data)} multiple_choice_single questions out of {len(all_questions)} total questions")
    
    # 初始化结果结构
    results = {
        "total_questions": len(questions_data),
        "questions": [],
        "accuracy": {}
    }
    
    # 为每个模型和提示策略初始化准确率统计
    for model in models:
        results["accuracy"][model] = {}
        for prompt in prompt_styles:
            results["accuracy"][model][prompt] = {"correct": 0, "total": 0, "accuracy": 0}
    
    print(f"Processing {len(questions_data)} GRE Math multiple_choice_single questions...")
    print("-" * 100)
    
    # 处理每个问题
    for q in questions_data:
        question_number = q.get("question_number")
        expected_answer = q.get("answer", "").strip()
        
        # 修正图片路径
        image_path = f"/home/ltang24/Education/GRE Math Medium/{question_number}.png"
        
        print(f"Processing question {question_number}...")
        
        if not os.path.exists(image_path):
            print(f"  Image not found: {image_path}")
            
            # 尝试查找可能的图片位置
            image_dir = "/home/ltang24/Education/GRE Math Medium"
            if os.path.exists(image_dir):
                print(f"  Looking for image in directory: {image_dir}")
                found_files = [f for f in os.listdir(image_dir) if f.startswith(question_number)]
                if found_files:
                    print(f"  Found potential match(es): {found_files}")
                    image_path = os.path.join(image_dir, found_files[0])
                else:
                    print(f"  No matching files found for question {question_number}")
                    continue
            else:
                print(f"  Directory not found: {image_dir}")
                print("  Please enter the correct path to the image directory:")
                image_dir = input().strip()
                image_path = os.path.join(image_dir, f"{question_number}.png")
                if not os.path.exists(image_path):
                    print(f"  Image still not found. Skipping question {question_number}")
                    continue
    
        try:
            base64_image = encode_image_to_base64(image_path)
        except Exception as e:
            print(f"  Error encoding image: {e}")
            continue
    
        question_result = {
            "question_number": question_number,
            "expected": expected_answer,
            "results": []
        }
    
        for model in models:
            for prompt_style in prompt_styles:
                prompt_messages = get_prompt_messages(prompt_style, base64_image)
                start_time = time.perf_counter()
                response_text = ""
                extracted_answer = ""
                correct = False
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=prompt_messages,
                        timeout=120
                    ).choices[0].message.content.strip()
                    response_text = response
                    extracted_answer = extract_answer(response_text)
                    
                    # 规范化两个答案以进行比较
                    norm_extracted = normalize_answer(extracted_answer)
                    norm_expected = normalize_answer(expected_answer)
                    correct = (norm_extracted == norm_expected)
                    
                    # 调试打印
                    print(f"  Normalized: Extracted '{norm_extracted}', Expected '{norm_expected}'")
                except Exception as e:
                    response_text = f"Error: {e}"
                
                runtime = round(time.perf_counter() - start_time, 2)
                single_result = {
                    "model": model,
                    "prompt_style": prompt_style,
                    "response": response_text,
                    "extracted_answer": extracted_answer,
                    "correct": correct,
                    "runtime": runtime
                }
                question_result["results"].append(single_result)
                
                results["accuracy"][model][prompt_style]["total"] += 1
                if correct:
                    results["accuracy"][model][prompt_style]["correct"] += 1
                
                print(f"  Model: {model}, Prompt: {prompt_style}, Answer: {extracted_answer}, Expected: {expected_answer}, Correct: {correct}, Time: {runtime}s")
        
        results["questions"].append(question_result)
        print("-" * 50)
    
    # 计算准确率百分比
    for model in results["accuracy"]:
        for prompt in results["accuracy"][model]:
            data_stat = results["accuracy"][model][prompt]
            total = data_stat["total"]
            correct = data_stat["correct"]
            data_stat["accuracy"] = round((correct / total) * 100, 2) if total > 0 else 0
    
    # 保存结果到文件
    output_file = "/home/ltang24/Education/GRE Math Medium/GRE_Math_Multiple_Choice_Single_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    
    # 打印总体结果
    print("\n" + "=" * 100)
    print("TESTING COMPLETE - OVERALL RESULTS")
    print("=" * 100)
    
    # 打印结果表格
    print("\nAccuracy for Multiple Choice Single Questions by Model and Prompt Style:")
    print("-" * 60)
    print(f"{'Model':<15} | {'Zero-Shot':<10} | {'CoT':<10} | {'Few-Shot':<10}")
    print("-" * 60)
    
    for model in models:
        zs_acc = f"{results['accuracy'][model]['zeroshot']['accuracy']}%"
        cot_acc = f"{results['accuracy'][model]['cot']['accuracy']}%"
        fs_acc = f"{results['accuracy'][model]['fiveshot']['accuracy']}%"
        print(f"{model:<15} | {zs_acc:<10} | {cot_acc:<10} | {fs_acc:<10}")
    
    print("\n" + "=" * 100)
    print(f"Detailed results saved to: {output_file}")

if __name__ == "__main__":
    main()