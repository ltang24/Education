import json
import re
import time
import os
import random
import argparse
from datetime import datetime
from g4f.client import Client

# Constants
MAX_RETRIES = 3
RATE_LIMIT_KEYWORD = "限流"  # Rate limit keyword in Chinese

def extract_answer(response: str) -> str:
    """Extract the answer letter (A-D) from the model's response for TOEFL listening questions."""
    if not response:
        return ""
    
    response_upper = response.upper()
    
    # Look for explicit answer patterns
    if any(kw in response_upper for kw in ["ANSWER: A", "ANSWER:A", "ANSWER IS A", "FINAL ANSWER: A"]):
        return "A"
    if any(kw in response_upper for kw in ["ANSWER: B", "ANSWER:B", "ANSWER IS B", "FINAL ANSWER: B"]):
        return "B"
    if any(kw in response_upper for kw in ["ANSWER: C", "ANSWER:C", "ANSWER IS C", "FINAL ANSWER: C"]):
        return "C"
    if any(kw in response_upper for kw in ["ANSWER: D", "ANSWER:D", "ANSWER IS D", "FINAL ANSWER: D"]):
        return "D"
    
    # Handle multiple answer questions (like "B, C" or "B D")
    multi_answer_match = re.search(r'([A-D])[,\s]+([A-D])', response_upper)
    if multi_answer_match:
        return f"{multi_answer_match.group(1)}, {multi_answer_match.group(2)}"
    
    # Look for last line or standalone letter
    lines = response_upper.strip().split('\n')
    if lines:
        last_line = lines[-1].strip()
        if last_line in ["A", "A.", "A:"]:
            return "A"
        if last_line in ["B", "B.", "B:"]:
            return "B"
        if last_line in ["C", "C.", "C:"]:
            return "C"
        if last_line in ["D", "D.", "D:"]:
            return "D"
    
    # Last resort: any standalone A/B/C/D
    standalone_match = re.search(r'\b([A-D])\b', response_upper)
    if standalone_match:
        return standalone_match.group(1)
    
    # Ultimate fallback: any A/B/C/D character
    any_letter_match = re.search(r'[A-D]', response_upper)
    if any_letter_match:
        return any_letter_match.group(0)
    
    return ""

def is_correct_answer(model_answer: str, correct_answer: str) -> bool:
    """Check if the model's answer is correct, handling both single and multiple-choice answers."""
    if not model_answer or not correct_answer:
        return False
    
    # Handle multiple answer questions
    if "," in correct_answer or " " in correct_answer:
        correct_parts = re.findall(r'[A-D]', correct_answer.upper())
        model_parts = re.findall(r'[A-D]', model_answer.upper())
        return sorted(correct_parts) == sorted(model_parts)
    
    # Handle single answer questions
    return model_answer.upper() == correct_answer.upper()

def generate_zero_shot_prompt(question_data: dict) -> str:
    """Generate a simple direct prompt for the TOEFL listening question."""
    prompt = "Please answer the following TOEFL listening question based on the provided conversation transcript.\n\n"
    
    # Add conversation transcript
    prompt += f"Conversation Transcript:\n{question_data.get('CONVERSATION', '')}\n\n"
    
    # Add question
    q = question_data['questions'][0]  # Get the first question for this example
    prompt += f"Question: {q['Question']}\n\n"
    
    # Add options
    prompt += "Options:\n"
    for letter, text in q['Options'].items():
        prompt += f"{letter}: {text}\n"
    
    # Add instruction
    prompt += "\nProvide ONLY the letter of your answer (e.g., A, B, C, or D)."
    
    return prompt

def generate_five_shot_prompt(question_data: dict, examples: list) -> str:
    """Generate a prompt with five examples followed by the actual question."""
    prompt = "I'll show you five examples of TOEFL listening questions and their answers, then ask you a new question.\n\n"
    
    # Add examples
    for i, example in enumerate(examples, 1):
        prompt += f"Example {i}:\n"
        prompt += f"Conversation (excerpt):\n{example['CONVERSATION'][:200]}...\n\n"
        q = example['questions'][0]  # Get the first question for this example
        prompt += f"Question: {q['Question']}\n"
        prompt += "Options:\n"
        for letter, text in q['Options'].items():
            prompt += f"{letter}: {text}\n"
        prompt += f"Answer: {q['Answer']}\n\n"
    
    # Add the actual question
    prompt += "Now, please answer this new question:\n\n"
    prompt += f"Conversation Transcript:\n{question_data.get('CONVERSATION', '')}\n\n"
    
    q = question_data['questions'][0]  # Get the first question for this example
    prompt += f"Question: {q['Question']}\n\n"
    
    # Add options
    prompt += "Options:\n"
    for letter, text in q['Options'].items():
        prompt += f"{letter}: {text}\n"
    
    # Add instruction
    prompt += "\nProvide ONLY the letter of your answer (e.g., A, B, C, or D)."
    
    return prompt

def generate_cot_prompt(question_data: dict) -> str:
    """Generate a prompt that encourages step-by-step reasoning."""
    prompt = "Please solve the following TOEFL listening question using step-by-step reasoning.\n\n"
    
    # Add conversation transcript
    prompt += f"Conversation Transcript:\n{question_data.get('CONVERSATION', '')}\n\n"
    
    # Add question
    q = question_data['questions'][0]  # Get the first question for this example
    prompt += f"Question: {q['Question']}\n\n"
    
    # Add options
    prompt += "Options:\n"
    for letter, text in q['Options'].items():
        prompt += f"{letter}: {text}\n"
    
    # Add reasoning instructions
    prompt += "\nPlease think through your reasoning carefully using these steps:\n"
    prompt += "1. Understand what the question is asking\n"
    prompt += "2. Identify relevant parts of the conversation\n"
    prompt += "3. Evaluate each option based on the conversation\n"
    prompt += "4. Explain why the correct answer is right and others are wrong\n\n"
    prompt += "After your analysis, clearly state your final answer as: Final Answer: [letter]"
    
    return prompt

def process_question(question_data, index, question_index, model_name, strategy, args, client, pool=None):
    """Process a single question and return the result."""
    q = question_data['questions'][question_index]
    question_id = f"{question_data['NO']}-{question_index+1}"
    correct_answer = q['Answer'].strip()
    
    # Generate appropriate prompt based on strategy
    if strategy == "zero-shot":
        prompt = generate_zero_shot_prompt(question_data)
    elif strategy == "five-shot":
        examples = random.sample(pool, min(5, len(pool))) if pool else []
        prompt = generate_five_shot_prompt(question_data, examples)
    else:  # chain-of-thought
        prompt = generate_cot_prompt(question_data)
    
    # Call model with retries
    resp = None
    for attempt in range(1, MAX_RETRIES+1):
        try:
            t0 = time.time()
            content = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                timeout=args.timeout,
                temperature=args.temp
            ).choices[0].message.content.strip()
            rt = round(time.time() - t0, 2)
            
            # Check for rate limiting
            if RATE_LIMIT_KEYWORD in content:
                print(f"  [Attempt {attempt}/{MAX_RETRIES}] Rate limit detected, waiting 120s...")
                time.sleep(120)
                continue
                
            # Print full response in verbose mode
            if args.verbose:
                print(f"Full response:\n{content}\n")
                
            resp = content
            break
        except Exception as e:
            print(f"  [Attempt {attempt}/{MAX_RETRIES}] Error: {e}")
            time.sleep(5)
    else:
        # All retries failed
        print(f"  Question {question_id} failed after multiple retries, skipping\n")
        return {
            "index": index,
            "question_id": question_id,
            "question_text": q['Question'],
            "correct_answer": correct_answer,
            "model_answer": None,
            "is_correct": False,
            "error": "rate_limited"
        }
    
    # Extract and evaluate answer
    model_answer = extract_answer(resp)
    is_correct = is_correct_answer(model_answer, correct_answer)
    
    print(f"Q{question_id}: {q['Question'][:50]}...")
    print(f"  Model answer: {model_answer}, Correct answer: {correct_answer}")
    print(f"  {'✓ Correct' if is_correct else '✗ Incorrect'} (Runtime: {rt}s)\n")
    
    return {
        "index": index,
        "question_id": question_id,
        "question_text": q['Question'],
        "correct_answer": correct_answer,
        "model_answer": model_answer,
        "model_full_response": resp[:500] if args.verbose else "",
        "is_correct": is_correct,
        "runtime": rt
    }

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate LLM on TOEFL listening comprehension questions"
    )
    parser.add_argument(
        "--input",
        default="/home/ltang24/Education/TOFEL/listening /TOFELFILELIESTINGWITHOUTMP3.json",
        help="Path to input JSON file with questions"
    )
    parser.add_argument(
        "--output", default="results_toefl_listening",
        help="Output directory for results"
    )
    parser.add_argument(
        "--models", nargs="+", default=["gpt-4o-mini"],
        help="List of models to evaluate"
    )
    parser.add_argument(
        "--strategies", nargs="+",
        default=["zero-shot", "five-shot", "chain-of-thought"],
        help="List of prompting strategies to use"
    )
    parser.add_argument(
        "--questions_per_test", type=int, default=5,
        help="Number of questions to test per conversation"
    )
    parser.add_argument(
        "--timeout", type=int, default=120,
        help="Timeout in seconds for model responses"
    )
    parser.add_argument(
        "--temp", type=float, default=0.3,
        help="Temperature setting for model calls"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable verbose output with full model responses"
    )
    args = parser.parse_args()

    # Create output directory if it doesn't exist
    os.makedirs(args.output, exist_ok=True)
    
    # Initialize client
    client = Client()

    # Load questions
    print(f"Loading questions from {args.input}")
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            conversations = json.load(f)
            
        print(f"Loaded {len(conversations)} conversations")
    except Exception as e:
        print(f"Error loading questions: {e}")
        return

    # Sample conversations if needed
    if args.questions_per_test < len(conversations):
        conversations = random.sample(conversations, args.questions_per_test)
        print(f"Sampled {len(conversations)} conversations for testing")

    # Store all results
    all_results = {}

    # Test each model and strategy
    for model_name in args.models:
        all_results[model_name] = {}
        
        for strat in args.strategies:
            print("\n" + "-"*80)
            print(f"Testing model: {model_name} with strategy: {strat}")
            print("-"*80 + "\n")

            # Initialize statistics
            stats = {
                "total": 0,
                "correct": 0,
                "by_conversation": {},
                "details": []
            }

            # Process each conversation
            for i, conversation in enumerate(conversations):
                conv_id = conversation.get('NO', i+1)
                conv_title = conversation.get('TITLE', f"Conversation {conv_id}")
                
                print(f"Testing conversation {conv_id}: {conv_title}\n")
                
                # Initialize conversation stats
                stats["by_conversation"][conv_id] = {
                    "title": conv_title,
                    "total": 0,
                    "correct": 0,
                    "questions": []
                }
                
                # Process each question in this conversation
                questions_in_conv = min(len(conversation['questions']), args.questions_per_test)
                
                for q_idx in range(questions_in_conv):
                    result = process_question(
                        conversation, 
                        i, 
                        q_idx, 
                        model_name, 
                        strat, 
                        args, 
                        client,
                        pool=conversations if strat == "five-shot" else None
                    )
                    
                    # Update statistics
                    stats["total"] += 1
                    stats["by_conversation"][conv_id]["total"] += 1
                    
                    if result.get("is_correct", False):
                        stats["correct"] += 1
                        stats["by_conversation"][conv_id]["correct"] += 1
                    
                    # Store detailed results
                    stats["details"].append(result)
                    stats["by_conversation"][conv_id]["questions"].append(result)

            # Calculate accuracy metrics
            total = stats["total"]
            correct = stats["correct"]
            accuracy = correct/total if total else 0.0
            stats["accuracy"] = accuracy
            
            # Calculate accuracy by conversation
            for conv_id, conv_data in stats["by_conversation"].items():
                conv_total = conv_data["total"]
                conv_correct = conv_data["correct"]
                conv_data["accuracy"] = conv_correct/conv_total if conv_total else 0.0

            # Generate summary text
            lines = []
            lines.append(f"{model_name} with {strat} strategy summary:")
            lines.append(f"Overall accuracy: {accuracy:.2%} ({correct}/{total})\n")
            
            for conv_id, conv_data in sorted(stats["by_conversation"].items()):
                t = conv_data["total"]
                c = conv_data["correct"]
                a = conv_data["accuracy"]
                lines.append(f"  Conversation {conv_id} - {conv_data['title']}: {a:.2%} ({c}/{t})")
            
            stats["summary_text"] = "\n".join(lines)

            # Print summary
            print(stats["summary_text"])

            # Store results for this strategy
            all_results[model_name][strat] = stats

    # Save results to file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.output, f"toefl_listening_results_{ts}.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"All results saved to {out_path}")

    # Generate CSV summary for easy viewing
    csv_path = os.path.join(args.output, f"toefl_listening_summary_{ts}.csv")
    
    with open(csv_path, "w", encoding="utf-8") as f:
        # Write header
        f.write("Model,Strategy,Overall Accuracy")
        for conv in conversations:
            conv_id = conv.get('NO', 'Unknown')
            f.write(f",Conversation {conv_id} Accuracy")
        f.write("\n")
        
        # Write data
        for model_name in args.models:
            for strat in args.strategies:
                if model_name in all_results and strat in all_results[model_name]:
                    model_strat = all_results[model_name][strat]
                    f.write(f"{model_name},{strat},{model_strat['accuracy']:.2%}")
                    
                    for conv in conversations:
                        conv_id = conv.get('NO', 'Unknown')
                        if str(conv_id) in model_strat["by_conversation"]:
                            conv_acc = model_strat["by_conversation"][str(conv_id)]["accuracy"]
                            f.write(f",{conv_acc:.2%}")
                        else:
                            f.write(",N/A")
                    
                    f.write("\n")
    
    print(f"CSV summary saved to {csv_path}")

if __name__ == "__main__":
    main()