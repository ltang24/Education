import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    # Remove dots and spaces
    answer = re.sub(r'[.\s]', '', answer, flags=re.IGNORECASE)
    return answer.strip().upper()

def extract_mc_answer(response):
    """Extract single letter options (A-E) from the model's response for multiple-choice questions"""
    # Look for explicit answer pattern like "Answer: X" or "Option: X"
    explicit_pattern = r'(?:answer|option|choice)(?:is|:|\s)\s*([A-E])\.?'
    explicit_match = re.search(explicit_pattern, response, re.IGNORECASE)
    if explicit_match:
        return normalize_answer(explicit_match.group(1))
    
    # Look for standalone letter with period
    standalone_pattern = r'\b([A-E])\.(?!\w)'
    standalone_match = re.search(standalone_pattern, response, re.IGNORECASE)
    if standalone_match:
        return normalize_answer(standalone_match.group(1))
    
    # Look for letter at the beginning of lines
    line_pattern = r'(?:^|\n)\s*([A-E])\.?'
    line_match = re.search(line_pattern, response, re.IGNORECASE)
    if line_match:
        return normalize_answer(line_match.group(1))
    
    # Last resort: just extract all letters A-E and take the first one
    all_options = re.findall(r'\b([A-E])\b', response, re.IGNORECASE)
    if all_options:
        return normalize_answer(all_options[0])
    
    return ""

def extract_select_in_passage_answer(response, valid_sentences):
    """Extract a selected sentence from the passage for select-in-passage questions"""
    # First, look for text in quotation marks
    quote_pattern = r'"([^"]+)"'
    quote_matches = re.findall(quote_pattern, response)
    
    for quote in quote_matches:
        clean_quote = re.sub(r'\s+', ' ', quote).strip()
        # Look for the most similar sentence in valid_sentences
        for sentence in valid_sentences:
            clean_sentence = re.sub(r'\s+', ' ', sentence).strip()
            if clean_sentence == clean_quote or (
                len(clean_quote) > 10 and  # Only consider substantial quotes
                (clean_quote in clean_sentence or clean_sentence in clean_quote)
            ):
                return sentence
    
    # If no matching quotes found, try to find an exact match for a valid sentence in the response
    for sentence in valid_sentences:
        # Create a clean version of the sentence for matching
        clean_sentence = re.sub(r'\s+', ' ', sentence).strip()
        if clean_sentence in re.sub(r'\s+', ' ', response):
            return sentence
    
    # If no exact match, try to find the most similar sentence
    max_overlap = 0
    best_match = ""
    
    for sentence in valid_sentences:
        # Break the sentence into words for partial matching
        sentence_words = set(re.findall(r'\b\w+\b', sentence.lower()))
        response_words = set(re.findall(r'\b\w+\b', response.lower()))
        
        # Calculate overlap
        overlap = len(sentence_words.intersection(response_words))
        
        # If this sentence has better overlap than previous best, update
        if overlap > max_overlap and overlap > 5:  # Require minimum overlap
            max_overlap = overlap
            best_match = sentence
    
    # Return the best match only if it's reasonably similar
    if max_overlap > len(sentence_words) * 0.5:  # At least 50% overlap
        return best_match
    
    return ""

# 1. Load JSON file
json_file = "/home/ltang24/Education/GRE_RC_questions.json"
with open(json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# 2. Define main model and backup models
main_model = "gpt-4o"
backup_models = ["gpt-4", "gpt-4o-mini"]

# 3. Initialize client
client = Client()

# 4. Limit to first 50 passages
passage_limit = 50
passages = data["passages"][:passage_limit]

print(f"Main model: {main_model}")
print(f"Backup models: {', '.join(backup_models)}")
print(f"Processing the first {len(passages)} passages...")
print("-" * 100)

total_questions = 0
correct_count = 0
results = {
    "passages": []
}

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
    
    for question in questions:
        question_number = question.get("question", "Unknown")
        question_type = question.get("question_type", "")
        options = question.get("options", [])
        correct_answer = question.get("correct_answer", "")
        
        print(f"  Processing question {question_number} ({question_type})...")
        total_questions += 1
        
        # Construct prompt based on question type
        if "Multiple-choice" in question_type:
            prompt = (
                f"Please carefully analyze the following reading passage and answer the question. Choose one correct option from the provided choices.\n\n"
                f"Reading Passage:\n{passage_content}\n\n"
                f"Question: {question_number}\n"
            )
            
            # Add options
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
                f"Question: {question_number}\n\n"
                f"IMPORTANT: For this question, you need to select the exact sentence from the passage that best answers the question. "
                f"In your response, please include the following:\n\n"
                f"Selected Sentence: \"Copy and paste the EXACT sentence from the passage that answers the question.\"\n"
                f"Explanation: Explain why this sentence answers the question.\n\n"
                f"Make sure to use quotation marks around the selected sentence and copy it exactly as it appears in the passage."
            )
        else:
            # Skip unknown question types
            print(f"  Skipping unknown question type: {question_type}")
            continue
        
        messages = [{"role": "user", "content": prompt}]
        
        # Try with models
        response = ""
        is_correct = False
        models_tried = []
        best_answer = ""
        best_response = ""
        best_model = ""
        runtime = 0
        
        # Prepare valid sentences for select-in-passage questions
        valid_sentences = []
        if "Select-in-Passage" in question_type:
            # Simple sentence splitting - may need refinement for complex texts
            valid_sentences = re.split(r'(?<=[.!?])\s+', passage_content)
            valid_sentences = [s.strip() for s in valid_sentences if s.strip()]
        
        # Try each model
        available_models = [main_model] + backup_models
        for model in available_models:
            models_tried.append(model)
            
            start_time = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=120  # Longer timeout for reading comprehension
                ).choices[0].message.content.strip()
                
                # Extract answer based on question type
                if "Multiple-choice" in question_type:
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
                            # If we haven't found any answers yet, store this as the best so far
                            best_answer = answer
                            best_response = response
                            best_model = model
                
                elif "Select-in-Passage" in question_type:
                    answer = extract_select_in_passage_answer(response, valid_sentences)
                    
                    if answer:
                        # For select-in-passage, we need to check if the selected sentence matches the correct answer
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
                            # If we haven't found any answers yet, store this as the best so far
                            best_answer = answer
                            best_response = response
                            best_model = model
                
            except Exception as e:
                print(f"  Error with {model} on question {question_number}: {e}")
            
            runtime = time.perf_counter() - start_time
        
        if is_correct:
            correct_count += 1
            passage_results["correct_count"] += 1
        
        # Record question details
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

# Calculate overall accuracy
accuracy = correct_count / total_questions if total_questions > 0 else 0
results["total_questions"] = total_questions
results["correct_count"] = correct_count
results["accuracy"] = accuracy

print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct answers: {correct_count}/{total_questions}")
print("-" * 100)

# Save results
output_file = "GRE_RC_questions_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")