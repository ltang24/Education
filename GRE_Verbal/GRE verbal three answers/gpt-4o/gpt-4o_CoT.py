import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    # Remove answer prefixes and special characters
    answer = re.sub(r'^(answer\s*[123]?\s*[:：\-]?\s*)|[""''"\']', '', answer, flags=re.IGNORECASE)
    # For multi-word phrases, keep spaces but normalize them
    return answer.strip().lower()

def extract_answers(response):
    """Extract three answers from the model's response with improved parsing"""
    # First, try to extract from the first line which often contains just the answers
    lines = response.strip().split('\n')
    first_line = lines[0].strip() if lines else ""
    
    # Try simple comma-separated format in first line
    if ',' in first_line and first_line.count(',') >= 2:
        parts = first_line.split(',')
        if len(parts) >= 3:
            # Take the first three items, ignore everything after
            ans1 = parts[0].strip()
            ans2 = parts[1].strip()
            # For the third answer, stop at the first whitespace followed by a non-alphanumeric character
            ans3_match = re.match(r'([^,]+?)(?:\s+[^a-zA-Z0-9].*)?$', parts[2].strip())
            ans3 = ans3_match.group(1) if ans3_match else parts[2].strip()
            
            # Check if these look like valid answers (not explanations)
            if len(ans1) < 30 and len(ans2) < 30 and len(ans3) < 30:
                return [normalize_answer(ans1), normalize_answer(ans2), normalize_answer(ans3)]
    
    # Look for the three blank pattern at the beginning of the response
    blank_pattern = r'blank\s*\(?i\)?\s*[:：]?\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?blank\s*\(?ii\)?\s*[:：]?\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?blank\s*\(?iii\)?\s*[:：]?\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(blank_pattern, response, re.DOTALL | re.IGNORECASE)
    if match:
        return [normalize_answer(match.group(1)), normalize_answer(match.group(2)), normalize_answer(match.group(3))]
    
    # Pattern 1: Look for three words separated by commas anywhere in the response
    pattern1 = r'([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)\s*,\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)\s*,\s*([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(pattern1, response)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        ans3 = match.group(3).strip()
        
        # Clean up the third answer by removing any non-word characters following it
        ans3_clean = re.match(r'([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)', ans3)
        if ans3_clean:
            ans3 = ans3_clean.group(1)
            
        return [normalize_answer(ans1), normalize_answer(ans2), normalize_answer(ans3)]
    
    # Pattern 2: Look for numbered answers
    pattern2 = r'(?:1\.?\s*|\(i\)\s*|\(1\)\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:2\.?\s*|\(ii\)\s*|\(2\)\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:3\.?\s*|\(iii\)\s*|\(3\)\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(pattern2, response, re.DOTALL)
    if match:
        return [normalize_answer(match.group(1)), normalize_answer(match.group(2)), normalize_answer(match.group(3))]
    
    # Pattern 3: Look for blank-specific answers
    pattern3 = r'(?:blank\s*\(?i\)?\s*|\(i\)\s*|first\s+blank\s*[:：]?\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:blank\s*\(?ii\)?\s*|\(ii\)\s*|second\s+blank\s*[:：]?\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?).+?(?:blank\s*\(?iii\)?\s*|\(iii\)\s*|third\s+blank\s*[:：]?\s*)([a-zA-Z\-]+(?:\s+[a-zA-Z\-]+)?)'
    match = re.search(pattern3, response, re.DOTALL | re.IGNORECASE)
    if match:
        return [normalize_answer(match.group(1)), normalize_answer(match.group(2)), normalize_answer(match.group(3))]
    
    # If none of these patterns work, look for frequent words
    # Filter out common words that are likely to be parts of explanations
    stopwords = ['the', 'and', 'for', 'blank', 'answer', 'first', 'second', 'third', 'explanation', 
                 'that', 'with', 'this', 'from', 'not', 'are', 'has', 'have', 'been', 'word', 'context']
    
    words = [word for word in re.findall(r'\b([a-zA-Z\-]+)\b', response) 
             if word.lower() not in stopwords and len(word) > 2]
    
    # Filter to words that appear in response
    if words:
        # Count occurrences
        word_counts = {}
        for word in words:
            if word.lower() not in word_counts:
                word_counts[word.lower()] = 1
            else:
                word_counts[word.lower()] += 1
        
        # Get top 3 most frequent words
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_words) >= 3:
            return [sorted_words[0][0], sorted_words[1][0], sorted_words[2][0]]
    
    return ["", "", ""]

# 1. Load JSON file
json_file = "/home/ltang24/Education/GRE verbal three answers/GRE_Verbal_array_of_3_answers.json"
with open(json_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Limit to first 50 questions
questions = questions[:50]

# 2. Define main model and backup models (only GPT models)
main_model = "gpt-4o"
backup_models = ["gpt-4", "gpt-4o-mini"]

# 3. Initialize client
client = Client()

print(f"Testing with main model: {main_model}")
print(f"Prompting Strategy: Optimized Chain of Thought for Text Completion")
print("-" * 100)

total = len(questions)
correct_count = 0
details = []

for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer")
    
    print(f"Processing question {i+1}/{total} (Q{question_number})...")
    
    # Construct optimized Chain of Thought prompt for Text Completion
    prompt = (
        "Please solve this GRE Text Completion question:\n\n"
        f"Passage: {content}\n"
        "Options:\n"
    )
    
    # Add options in a clear format
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
    
    messages = [{"role": "user", "content": prompt}]
    
    # Try with main model first
    current_model = main_model
    response = ""
    is_correct = False
    models_tried = []
    best_answers = ["", "", ""]
    best_response = ""
    best_model = ""
    runtime = 0
    
    # Try each model
    available_models = [main_model] + backup_models.copy()  # Make a copy to avoid modifying original
    for model in available_models:
        models_tried.append(model)
        
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=60,
                temperature=0.1  # Lower temperature for more consistent formatting
            ).choices[0].message.content.strip()
            
            # Extract answers
            answers = extract_answers(response)
            
            # Normalize expected answers
            expected_normalized = [normalize_answer(e) for e in expected]
            
            # Check if answers match
            if len(answers) == 3 and all(a for a in answers):
                current_is_correct = (
                    answers[0] == expected_normalized[0] and
                    answers[1] == expected_normalized[1] and
                    answers[2] == expected_normalized[2]
                )
                
                if current_is_correct:
                    is_correct = True
                    best_answers = answers
                    best_response = response
                    best_model = model
                    runtime = time.perf_counter() - start_time
                    break
                elif not best_answers[0] and not best_answers[1] and not best_answers[2]:
                    # If we haven't found any answers yet, store these as the best so far
                    best_answers = answers
                    best_response = response
                    best_model = model
            
        except Exception as e:
            print(f"Error with {model} on Q{question_number}: {e}")
        
        runtime = time.perf_counter() - start_time
    
    if is_correct:
        correct_count += 1
        print(f"  ✓ Correct: {best_answers}")
    else:
        print(f"  ✗ Incorrect: Model: {best_answers}, Expected: {expected}")
    
    # Record details
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

accuracy = correct_count / total if total > 0 else 0
print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct answers: {correct_count}/{total}")
print("-" * 100)

results = {
    "strategy": "Optimized Chain of Thought for Text Completion",
    "accuracy": accuracy,
    "total_questions": total,
    "correct_count": correct_count,
    "details": details
}

# Save results
output_file = "GRE_Verbal_array_of_3_answers_OptimizedCoT_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")