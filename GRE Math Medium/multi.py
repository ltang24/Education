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
    # For multiple choice multiple, sort the letters to ensure consistent format
    if ',' in answer:
        letters = [c for c in re.sub(r'[^a-zA-Z,]', '', answer).upper().split(',') if c]
        return ','.join(sorted(letters))
    # For numeric answers, keep only the numbers
    if re.match(r'^\d+$', re.sub(r'[^0-9]', '', answer)):
        return re.sub(r'[^0-9]', '', answer)
    # For single letter answers, convert to uppercase
    return re.sub(r'[^a-zA-Z0-9]', '', answer).upper()

def extract_answer(response, question_type):
    """
    Extract the final answer from the model's response based on question type.
    """
    # Try to extract using "Answer: X" format first
    answer_pattern = re.search(r'Answer:\s*([A-Za-z0-9,\s]+)', response)
    if answer_pattern:
        raw_answer = answer_pattern.group(1).strip()
        
        if question_type == "multiple_choice_multiple":
            # For multiple choice with multiple answers, extract all letters
            letters = re.findall(r'[A-Ea-e]', raw_answer)
            return ','.join(sorted([l.upper() for l in letters]))
        elif question_type == "numeric_entry":
            # For numeric entry, extract the first number
            num_match = re.search(r'\d+', raw_answer)
            return num_match.group(0) if num_match else raw_answer
        else:
            # For multiple choice single and quantitative comparison, extract the first letter
            letter_match = re.search(r'[A-Ea-e]', raw_answer)
            return letter_match.group(0).upper() if letter_match else raw_answer
    
    # If "Answer: X" format is not found, try to find the answer in the response
    if question_type == "multiple_choice_multiple":
        # Look for comma-separated letters
        match = re.search(r'\b([A-Ea-e](,\s*[A-Ea-e])+)\b', response)
        if match:
            return normalize_answer(match.group(1))
        # Try to find multiple letters mentioned
        letters = re.findall(r'\b[A-Ea-e]\b', response)
        if letters:
            return ','.join(sorted([l.upper() for l in letters]))
    elif question_type == "numeric_entry":
        # Find the last mentioned number in the response
        numbers = re.findall(r'\b\d+\b', response)
        return numbers[-1] if numbers else ""
    else:
        # For multiple choice single and quantitative comparison
        # Try to find a clear statement with a single letter
        match = re.search(r'\b(option|answer|choice|select)\s+([A-Ea-e])\b', response.lower())
        if match:
            return match.group(2).upper()
        # Otherwise, find the last standalone letter mentioned
        letters = re.findall(r'\b[A-Ea-e]\b', response)
        return letters[-1].upper() if letters else ""
    
    return ""

# ---- Prompting Strategy ----

def generate_zero_shot_prompt(question_type):
    """Generate a zero-shot prompt based on question type"""
    if question_type == "multiple_choice_single":
        return ("Please analyze the GRE math question in the image and select the best answer choice. "
                "Provide only your final answer in the format 'Answer: X', where X is a single letter (A, B, C, D, or E).")
    elif question_type == "multiple_choice_multiple":
        return ("Please analyze the GRE math question in the image and select all correct answer choices. "
                "Provide only your final answer in the format 'Answer: X,Y,Z', listing all correct options.")
    elif question_type == "numeric_entry":
        return ("Please solve the GRE math question in the image and determine the correct numerical value. "
                "Provide only your final answer in the format 'Answer: X', where X is the numerical solution.")
    elif question_type == "quantitative_comparison":
        return ("Please analyze the GRE quantitative comparison question in the image. "
                "Compare Quantity A and Quantity B, then provide only your final answer in the format 'Answer: X', "
                "where X is one of the following: "
                "A (if Quantity A is greater), "
                "B (if Quantity B is greater), "
                "C (if the two quantities are equal), or "
                "D (if the relationship cannot be determined).")

def generate_cot_prompt(question_type):
    """Generate a chain-of-thought prompt based on question type"""
    base = ("Please solve the GRE math question in the image step-by-step. "
            "Show your reasoning process clearly, then provide your final answer. ")
    
    if question_type == "multiple_choice_single":
        return base + ("After your reasoning, conclude with 'Answer: X', "
                      "where X is a single letter (A, B, C, D, or E) representing the correct answer choice.")
    elif question_type == "multiple_choice_multiple":
        return base + ("After your reasoning, conclude with 'Answer: X,Y,Z', "
                      "listing all letters that represent correct answer choices.")
    elif question_type == "numeric_entry":
        return base + ("After your reasoning, conclude with 'Answer: X', "
                      "where X is the numerical solution.")
    elif question_type == "quantitative_comparison":
        return base + ("After your reasoning, conclude with 'Answer: X', where X is one of the following: "
                      "A (if Quantity A is greater), "
                      "B (if Quantity B is greater), "
                      "C (if the two quantities are equal), or "
                      "D (if the relationship cannot be determined).")

def generate_few_shot_prompt(question_type):
    """Generate a few-shot prompt with examples based on question type"""
    if question_type == "multiple_choice_single":
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
    elif question_type == "multiple_choice_multiple":
        return (
            "Here are some examples of how to solve GRE questions with multiple correct answers:\n\n"
            "Example 1:\n"
            "For a question asking which of the following numbers are prime, I would check each option:\n"
            "A: 15 = 3 × 5, not prime\n"
            "B: 17 is prime\n"
            "C: 21 = 3 × 7, not prime\n"
            "D: 23 is prime\n"
            "E: 27 = 3³, not prime\n"
            "Answer: B,D\n\n"
            "Example 2:\n"
            "For a question asking which functions are differentiable at x = 0, I'd check each option and select all that apply.\n"
            "Answer: A,C,E\n\n"
            "Now, please solve the GRE math question in the image. Analyze each option and select all correct answers, listing them in the format 'Answer: X,Y,Z'"
        )
    elif question_type == "numeric_entry":
        return (
            "Here are some examples of how to solve GRE numeric entry questions:\n\n"
            "Example 1:\n"
            "For a question asking to find the area of a triangle with base 6 and height 4, I'd calculate:\n"
            "Area = (1/2) × base × height = (1/2) × 6 × 4 = 12\n"
            "Answer: 12\n\n"
            "Example 2:\n"
            "For a question about finding the probability as a fraction in lowest terms, if I get 3/8, I'd write:\n"
            "Answer: 3/8\n\n"
            "Now, please solve the GRE math question in the image. Calculate the answer step-by-step and provide your numerical solution in the format 'Answer: X'"
        )
    elif question_type == "quantitative_comparison":
        return (
            "Here are some examples of how to solve GRE quantitative comparison questions:\n\n"
            "Example 1:\n"
            "Quantity A: 2^5\n"
            "Quantity B: 5^2\n"
            "I calculate: Quantity A = 2^5 = 32, Quantity B = 5^2 = 25\n"
            "Since 32 > 25, Quantity A is greater.\n"
            "Answer: A\n\n"
            "Example 2:\n"
            "Quantity A: The area of a circle with radius 4\n"
            "Quantity B: The area of a square with side length 7\n"
            "I calculate:\n"
            "Quantity A = πr² = π(4)² = 16π ≈ 50.27\n"
            "Quantity B = s² = 7² = 49\n"
            "Since 50.27 > 49, Quantity A is greater.\n"
            "Answer: A\n\n"
            "Now, please solve the GRE quantitative comparison question in the image. Compare Quantity A and Quantity B, and provide your answer as:\n"
            "A (if Quantity A is greater)\n"
            "B (if Quantity B is greater)\n"
            "C (if the two quantities are equal)\n"
            "D (if the relationship cannot be determined from the information given)\n"
            "Format your final answer as 'Answer: X'"
        )

def get_prompt_messages(prompt_style, qtype, base64_image):
    """Generate the appropriate prompt messages based on style and question type"""
    if prompt_style == "zeroshot":
        text = generate_zero_shot_prompt(qtype)
    elif prompt_style == "cot":
        text = generate_cot_prompt(qtype)
    elif prompt_style == "fiveshot":
        text = generate_few_shot_prompt(qtype)
    else:
        text = f"Please analyze this GRE math question and provide your answer in the format 'Answer: X'."
    
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
    # Define models and prompt styles to test
    models = ["gpt-4", "gpt-4o", "gpt-4o-mini", "llama-3.1-8b", "llama-3.1-70b", "llama-3.1-405b", "gemini-1.5-flash", "command r"]
    prompt_styles = ["zeroshot", "cot", "fiveshot"]
    
    client = Client()
    
    # Load question data
    json_file = "/home/ltang24/Education/GRE Math Medium/gre_math_categorized.json"
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        questions_data = data["GRE Math Medium.json"]
    
    # Initialize results structure
    results = {
        "total_questions": len(questions_data),
        "questions": [],
        "accuracy": {}
    }
    
    question_types = ["quantitative_comparison", "multiple_choice_single", "multiple_choice_multiple", "numeric_entry"]
    for qtype in question_types:
        results["accuracy"][qtype] = {}
        for model in models:
            results["accuracy"][qtype][model] = {}
            for prompt in prompt_styles:
                results["accuracy"][qtype][model][prompt] = {"correct": 0, "total": 0}
    
    print(f"Processing {len(questions_data)} GRE Math questions using multiple models and prompting techniques...")
    print("-" * 100)
    
    # Process each question
    for q in questions_data:
        if not isinstance(q, dict):
            print("Skipping invalid entry:", q)
            continue
    
        question_number = q.get("question_number")
        raw_image_path = q.get("image")
        expected_answer = q.get("answer", "").strip()
        qtype = q.get("question_type")
        
        # Correct the image path
        image_path = f"/home/ltang24/Education/GRE Math Medium/{question_number}.png"
        
        print(f"Processing question {question_number} of type {qtype} ...")
        
        if not os.path.exists(image_path):
            print(f"  Image not found: {image_path}")
            continue
    
        try:
            base64_image = encode_image_to_base64(image_path)
        except Exception as e:
            print(f"  Error encoding image: {e}")
            continue
    
        question_result = {
            "question_number": question_number,
            "question_type": qtype,
            "expected": expected_answer,
            "results": []
        }
    
        for model in models:
            for prompt_style in prompt_styles:
                prompt_messages = get_prompt_messages(prompt_style, qtype, base64_image)
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
                    extracted_answer = extract_answer(response_text, qtype)
                    
                    # Normalize both answers for comparison
                    norm_extracted = normalize_answer(extracted_answer)
                    norm_expected = normalize_answer(expected_answer)
                    correct = (norm_extracted == norm_expected)
                    
                    # Debug print
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
                
                results["accuracy"][qtype][model][prompt_style]["total"] += 1
                if correct:
                    results["accuracy"][qtype][model][prompt_style]["correct"] += 1
                
                print(f"  Model: {model}, Prompt: {prompt_style}, Answer: {extracted_answer}, Expected: {expected_answer}, Correct: {correct}, Time: {runtime}s")
        
        results["questions"].append(question_result)
        print("-" * 50)
    
    # Calculate accuracy percentages
    for qtype in results["accuracy"]:
        for model in results["accuracy"][qtype]:
            for prompt in results["accuracy"][qtype][model]:
                data_stat = results["accuracy"][qtype][model][prompt]
                total = data_stat["total"]
                correct = data_stat["correct"]
                data_stat["accuracy"] = round((correct / total) * 100, 2) if total > 0 else 0
    
    # Add overall accuracy across all question types
    results["overall_accuracy"] = {}
    for model in models:
        results["overall_accuracy"][model] = {}
        for prompt in prompt_styles:
            total_correct = 0
            total_questions = 0
            for qtype in question_types:
                total_correct += results["accuracy"][qtype][model][prompt]["correct"]
                total_questions += results["accuracy"][qtype][model][prompt]["total"]
            
            results["overall_accuracy"][model][prompt] = {
                "correct": total_correct,
                "total": total_questions,
                "accuracy": round((total_correct / total_questions) * 100, 2) if total_questions > 0 else 0
            }
    
    # Save results to file
    output_file = "/home/ltang24/Education/GRE Math Medium/GRE_Math_Medium_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    
    # Print overall results
    print("\n" + "=" * 100)
    print("TESTING COMPLETE - OVERALL RESULTS")
    print("=" * 100)
    
    # Print table of results
    print("\nOverall Accuracy by Model and Prompt Style:")
    print("-" * 60)
    print(f"{'Model':<15} | {'Zero-Shot':<10} | {'CoT':<10} | {'Few-Shot':<10}")
    print("-" * 60)
    
    for model in models:
        zs_acc = f"{results['overall_accuracy'][model]['zeroshot']['accuracy']}%"
        cot_acc = f"{results['overall_accuracy'][model]['cot']['accuracy']}%"
        fs_acc = f"{results['overall_accuracy'][model]['fiveshot']['accuracy']}%"
        print(f"{model:<15} | {zs_acc:<10} | {cot_acc:<10} | {fs_acc:<10}")
    
    print("\n" + "=" * 100)
    print(f"Detailed results saved to: {output_file}")

if __name__ == "__main__":
    main()