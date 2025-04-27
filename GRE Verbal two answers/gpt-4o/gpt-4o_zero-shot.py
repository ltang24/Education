import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    # Remove answer prefixes and special characters
    answer = re.sub(r'^(answer\s*[12]?\s*[:：\-]?\s*)|[""''"\']', '', answer, flags=re.IGNORECASE)
    return answer.strip().lower().replace(' ', '')

def extract_answers(response):
    """Extract answers using improved pattern matching"""
    # First check for the exact format we requested
    # Look for "word1, word2" at the start of the response
    first_line = response.split('\n')[0].strip() if response else ""
    
    # Simple split by comma for the first line
    if first_line and ',' in first_line:
        parts = first_line.split(',', 1)
        if len(parts) == 2:
            potential_ans1 = parts[0].strip()
            # For the second answer, stop at the first space after words
            potential_ans2 = re.match(r'([^\s]+(?:\s+[^\s]+)?)', parts[1].strip())
            if potential_ans2:
                potential_ans2 = potential_ans2.group(1)
                
                # Check if these look like valid answers (not explanations)
                if len(potential_ans1) < 30 and len(potential_ans2) < 30:
                    remaining_text = response[len(first_line):].strip()
                    return normalize_answer(potential_ans1), normalize_answer(potential_ans2), remaining_text
    
    # If the simple approach fails, try regex patterns
    # Try to find "word1, word2" pattern anywhere in the response
    answer_pattern = r'([a-zA-Z]+(?:\s+[a-zA-Z]+)?),\s*([a-zA-Z]+(?:\s+[a-zA-Z]+)?)'
    match = re.search(answer_pattern, response)
    
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        # The explanation is everything after the match
        explanation = response[match.end():].strip()
        return normalize_answer(ans1), normalize_answer(ans2), explanation
    
    # Last resort: look for any two words that might be answers
    words = re.findall(r'\b([a-zA-Z]+)\b', response)
    if len(words) >= 2:
        return normalize_answer(words[0]), normalize_answer(words[1]), ""
    
    return "", "", ""

# 1. Load JSON file
json_file = "/home/ltang24/Education/GRE_Verbal_array_of_2_answers.json"
with open(json_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Limit to first 50 questions
questions = questions[:50]

# 2. Define main model and backup models (only GPT models)
main_model = "gpt-4o"
backup_models = ["gpt-4", "gpt-3.5-turbo","gpt-4o-mini"]

# 3. Initialize client
client = Client()

results = {}

# 4. Test with main model first, then fallback to backup models if needed
print(f"Testing with main model: {main_model}")
total = len(questions)
correct_count = 0
details = []

for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer")
    
    print(f"Processing question {i+1}/{total} (Q{question_number})...")
    
    # Construct improved prompt
    prompt = (
        "Please carefully read the following GRE sentence equivalence question and respond accordingly:\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    
    # Add options in English format
    for key in sorted(options.keys()):
        prompt += f"{key.replace('Blank', 'Blank ')} options:\n"
        for opt in options[key]:
            prompt += f"- {opt}\n"
    
    prompt += "\nIMPORTANT: Your response must follow this EXACT format:\n"
    prompt += "answer1, answer2\n"
    prompt += "Explanation: Your explanation here\n\n"
    prompt += "The comma between answers is essential. Do not include any other text before the answers."
    prompt += "Make sure there's a clear space between the two answers and the explanation."
    
    messages = [{"role": "user", "content": prompt}]
    
    # Try with main model first
    current_model = main_model
    response = ""
    is_correct = False
    model_tried = []
    
    while not is_correct and (current_model == main_model or backup_models):
        model_tried.append(current_model)  # Track which models we've tried
        
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=messages,
                timeout=60
            ).choices[0].message.content.strip()
            
            # Extract answers
            ans1, ans2, explanation = extract_answers(response)
            
            # Normalize expected answers
            expected_normalized = [normalize_answer(e) for e in expected]
            
            # Check for correct answers regardless of order
            answers_match = (
                (ans1 == expected_normalized[0] and ans2 == expected_normalized[1]) or
                (ans1 == expected_normalized[1] and ans2 == expected_normalized[0])
            )
            
            # If we have answers but they're not correct, try backup
            if ans1 and ans2:
                is_correct = answers_match
            else:
                # If we couldn't extract answers, we need to try another model
                pass
                
        except Exception as e:
            print(f"Error with {current_model} on Q{question_number}: {e}")
            ans1, ans2, explanation = "", "", ""
        
        runtime = time.perf_counter() - start_time
        
        # If not correct and we have backup models, try the next one
        if not is_correct and backup_models:
            current_model = backup_models.pop(0)
            print(f"  Trying backup model: {current_model}")
        else:
            break
    
    if is_correct:
        correct_count += 1
    
    # Record details
    details.append({
        "question_number": question_number,
        "expected": expected,
        "models_tried": model_tried,
        "model_used": current_model,
        "model_answer": [ans1, ans2] if ans1 and ans2 else [],
        "model_explanation": explanation,
        "model_response": response,
        "runtime": round(runtime, 2),
        "correct": is_correct
    })

accuracy = correct_count / total if total > 0 else 0
print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct answers: {correct_count}/{total}")
print("-" * 100)

results = {
    "accuracy": accuracy,
    "total_questions": total,
    "correct_count": correct_count,
    "details": details
}

# 5. Save results
output_file = "GRE_Verbal_array_of_2_answers_result.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print("Testing completed. Results saved to:", output_file)