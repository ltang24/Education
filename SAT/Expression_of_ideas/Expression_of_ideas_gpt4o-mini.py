import json
import re
import time
import os
from datetime import datetime
import sys
import argparse
from g4f.client import Client
import random

# Hardcoded correct answers for any questions missing them
expression_skill_answers = {
    # Add any missing answers here if needed
}

# Function to normalize answer for comparison
def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    if not answer:
        return ""
    answer = re.sub(r'^(answer\s*[12]?\s*[:：\-]?\s*)|["\'""]', '', answer, flags=re.IGNORECASE)
    return answer.strip().upper()

# Function to extract the letter answer from model response
def extract_answer(response):
    """Extract the answer letter (A-D) from the model's response"""
    if not response:
        return ""
        
    response_upper = response.upper()
    
    # Try to find explicit final answer markers
    final_answer_patterns = [
        r'FINAL ANSWER[:：\s]*([A-D])',
        r'ANSWER[:：\s]*([A-D])',
        r'THE ANSWER IS[:：\s]*([A-D])',
        r'SELECTED ANSWER[:：\s]*([A-D])',
        r'BEST OPTION[:：\s]*([A-D])',
        r'OPTION\s*([A-D])'
    ]
    
    for pattern in final_answer_patterns:
        match = re.search(pattern, response_upper)
        if match:
            return match.group(1)
    
    # Try to find a standalone letter at the end of the response
    lines = response_upper.strip().split('\n')
    last_line = lines[-1].strip()
    match = re.match(r'^([A-D])[.:]?$', last_line)
    if match:
        return match.group(1)
    
    # Look for standalone letter in the first or last line
    for line in [lines[0], lines[-1]]:
        match = re.search(r'\b([A-D])\b', line)
        if match:
            return match.group(1)
    
    # Look for any standalone letter in the entire response
    match = re.search(r'\b([A-D])\b', response_upper)
    if match:
        return match.group(1)
    
    # Last resort: find any letter (even if not standalone)
    match = re.search(r'([A-D])', response_upper)
    if match:
        return match.group(1)
    
    return ""

# Generate zero-shot prompt
def generate_zero_shot_prompt(question_data):
    """Generate a simple direct prompt asking for the answer"""
    skill_type = question_data.get("skill", "")
    
    if skill_type == "Rhetorical Synthesis":
        notes = question_data.get("notes", "")
        student_goal = question_data.get("student_goal", "")
        answer_choices = question_data.get("answer_choices", {})
        
        prompt = (
            f"Please solve the following Rhetorical Synthesis question and select the single best answer (A/B/C/D).\n\n"
            f"Notes: {notes}\n\n"
            f"Student's Goal: {student_goal}\n\n"
            f"Answer Choices:\n"
        )
        for letter in sorted(answer_choices.keys()):
            prompt += f"{letter}: {answer_choices[letter]}\n"
    
    elif skill_type == "Transitions":
        passage = question_data.get("passage", "")
        options = question_data.get("options", {})
        
        prompt = (
            f"Please solve the following Transitions question and select the single best answer (A/B/C/D).\n\n"
            f"Passage: {passage}\n\n"
            f"Which choice completes the text with the most logical transition?\n\n"
            f"Options:\n"
        )
        for letter in sorted(options.keys()):
            prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nImportant: Provide ONLY the letter of your answer (A, B, C, or D)."
    return prompt

# Generate five-shot prompt with examples
def generate_five_shot_prompt(question_data, question_type):
    """Generate a prompt with five examples of the same type followed by the question"""
    # Define examples based on the question type
    examples = []
    
    if question_type == "Rhetorical Synthesis":
        examples = [
            {
                "notes": "As engineered structures, many bird nests are uniquely flexible yet cohesive. A research team led by Yashraj Bhosale wanted to better understand the mechanics behind these structural properties. Bhosale's team used laboratory models that simulated the arrangement of flexible sticks into nest-like structures. The researchers analyzed the points where sticks touched one another. When pressure was applied to the model nests, the number of contact points between the sticks increased, making the structures stiffer.",
                "student_goal": "Present the primary aim of the research study.",
                "answer_choices": {
                    "A": "Bhosale's team wanted to better understand the mechanics behind bird nests' uniquely flexible yet cohesive structural properties.",
                    "B": "The researchers used laboratory models that simulated the arrangement of flexible sticks and analyzed the points where sticks touched one another.",
                    "C": "After analyzing the points where sticks touched, the researchers found that the structures became stiffer when pressure was applied.",
                    "D": "As analyzed by Bhosale's team, bird nests are uniquely flexible yet cohesive engineered structures."
                },
                "answer": "A"
            },
            {
                "notes": "The Atlantic Monthly magazine was first published in 1857 and focused on politics, art, and literature. In 2019, historian Cathryn Halverson published the book Faraway Women and the 'Atlantic Monthly.' The book's subject is female authors whose autobiographies appeared in the magazine in the early 1900s. One of the authors discussed is Juanita Harrison.",
                "student_goal": "Introduce Cathryn Halverson's book to an audience already familiar with the Atlantic Monthly.",
                "answer_choices": {
                    "A": "Cathryn Halverson's Faraway Women and the 'Atlantic Monthly' discusses female authors whose autobiographies appeared in the magazine in the early 1900s.",
                    "B": "A magazine called the Atlantic Monthly, referred to in Cathryn Halverson's book title, was first published in 1857.",
                    "C": "Faraway Women and the 'Atlantic Monthly' features contributors to the Atlantic Monthly, first published in 1857 as a magazine focusing on politics, art, and literature.",
                    "D": "An author discussed by Cathryn Halverson is Juanita Harrison, whose autobiography appeared in the Atlantic Monthly in the early 1900s."
                },
                "answer": "A"
            },
            {
                "notes": "Organisms release cellular material (such as hair or skin) into their environment, and the DNA from these substances is known as environmental DNA (eDNA). Researchers collect and analyze eDNA to detect the presence of species that are difficult to observe. Geneticist Sara Oyler-McCance's research team analyzed eDNA in water samples from the Florida Everglades to detect invasive constrictor snake species. The study determined a 91% probability of detecting Burmese python eDNA in a given location.",
                "student_goal": "Present the study to an audience already familiar with environmental DNA.",
                "answer_choices": {
                    "A": "Sara Oyler-McCance's researchers analyzed eDNA in water samples from the Florida Everglades for evidence of invasive constrictor snakes, which are difficult to observe.",
                    "B": "An analysis of eDNA can detect the presence of invasive species that are difficult to observe, such as constrictor snakes.",
                    "C": "Researchers found Burmese python eDNA, or environmental DNA, in water samples; eDNA is the DNA in released cellular materials, such as shed skin cells.",
                    "D": "Sara Oyler-McCance's researchers analyzed environmental DNA (eDNA)—that is, DNA from cellular materials released by organisms—in water samples from the Florida Everglades."
                },
                "answer": "A"
            },
            {
                "notes": "Sam Maloof (1916–2009) was an American woodworker and furniture designer, and the son of Lebanese immigrants. He received a 'genius grant' from the MacArthur Foundation in 1985. The Museum of Fine Arts in Boston owns a rocking chair made by Maloof from walnut wood. The chair features sleek, contoured armrests and seat, and a back consisting of seven spindle-like slats.",
                "student_goal": "Describe the rocking chair to an audience unfamiliar with Sam Maloof.",
                "answer_choices": {
                    "A": "With its sleek, contoured armrests and seat, the walnut rocking chair in Boston's Museum of Fine Arts is just one piece of furniture created by American woodworker Sam Maloof.",
                    "B": "Sam Maloof was born in 1916 and died in 2009, and during his life, he made a chair that you can see if you visit the Museum of Fine Arts in Boston.",
                    "C": "Furniture designer Sam Maloof was a recipient of one of the John D. and Catherine T. MacArthur Foundation's 'genius grants.'",
                    "D": "The rocking chair is made from walnut, and it has been shaped such that its armrests and seat are sleek and contoured."
                },
                "answer": "A"
            },
            {
                "notes": "Species belonging to the Orchidaceae family are found in both tropical and temperate environments. However, the diversity of Orchidaceae species in temperate forests, such as those in Oaxaca, Mexico, has not been well studied. Arelee Estefanía Muñoz-Hernández led a study to determine how many different Orchidaceae species are present in these forests. Her team collected orchids each month for a year at a site in Oaxaca and found that 74 species were present.",
                "student_goal": "Present the study and its findings.",
                "answer_choices": {
                    "A": "A study led by Arelee Estefanía Muñoz-Hernández identified a total of 74 Orchidaceae species in the temperate forests of Oaxaca, Mexico.",
                    "B": "There are orchids in many environments, but there are 74 Orchidaceae species in Oaxaca, Mexico.",
                    "C": "Oaxaca, Mexico, is home to temperate forests containing 74 Orchidaceae species.",
                    "D": "Arelee Estefanía Muñoz-Hernández and her team wanted to know how many different Orchidaceae species are present in the forests of Oaxaca, Mexico, so they conducted a study to collect orchids."
                },
                "answer": "A"
            }
        ]
    elif question_type == "Transitions":
        examples = [
            {
                "passage": "Samuel Coleridge-Taylor was a prominent classical music composer from England who toured the US three times in the early 1900s. The child of a West African father and an English mother, Coleridge-Taylor emphasized his mixed‐race ancestry. For example, he referred to himself as Anglo-African. ______blank he incorporated the sounds of traditional African music into his classical music compositions.",
                "question": "Which choice completes the text with the most logical transition?",
                "options": {
                    "A": "In addition,",
                    "B": "Actually,",
                    "C": "However,",
                    "D": "Regardless,"
                },
                "answer": "A"
            },
            {
                "passage": "In her poetry collection Thomas and Beulah, Rita Dove interweaves the titular characters' personal stories with broader historical narratives. She places Thomas's journey from the American South to the Midwest in the early 1900s within the larger context of the Great Migration. ______blank Dove sets events from Beulah's personal life against the backdrop of the US Civil Rights Movement.",
                "question": "Which choice completes the text with the most logical transition?",
                "options": {
                    "A": "Specifically,",
                    "B": "Thus,",
                    "C": "Regardless,",
                    "D": "Similarly,"
                },
                "answer": "D"
            },
            {
                "passage": "In a heated debate in biogeography, the field is divided between dispersalists and vicariancists. ______blank there are those who argue that dispersal is the most crucial determining factor in a species' distribution, and those who insist that vicariance (separation due to geographic barriers) is. Biogeographer Isabel Sanmartín counts herself among neither.",
                "question": "Which choice completes the text with the most logical transition?",
                "options": {
                    "A": "Furthermore,",
                    "B": "By contrast,",
                    "C": "Similarly,",
                    "D": "That is,"
                },
                "answer": "D"
            },
            {
                "passage": "Most of the planets that have been discovered outside our solar system orbit G-type stars, like our Sun. In 2014, ______blank researchers identified a planet orbiting KELT-9, a B-type star more than twice as massive and nearly twice as hot as the Sun. Called KELT-9b, it is one of the hottest planets ever discovered.",
                "question": "Which choice completes the text with the most logical transition?",
                "options": {
                    "A": "likewise,",
                    "B": "however,",
                    "C": "therefore,",
                    "D": "for example,"
                },
                "answer": "B"
            },
            {
                "passage": "In 1815, while in exile in Jamaica, Venezuelan revolutionary Simón Bolívar penned a letter praising England's republican government and expressing hope that Latin American nations seeking independence from Spain might achieve something similar. The letter was addressed to a local merchant, Henry Cullen; ______blank though, Bolívar's goal was to persuade political leaders from England and Europe to support his cause.",
                "question": "Which choice completes the text with the most logical transition?",
                "options": {
                    "A": "additionally,",
                    "B": "ultimately,",
                    "C": "accordingly,",
                    "D": "consequently,"
                },
                "answer": "B"
            }
        ]
    
    prompt = f"I'll show you five examples of {question_type} questions and their answers, then ask you a new question.\n\n"
    
    for i, ex in enumerate(examples):
        prompt += f"Example {i+1}:\n"
        
        # Format based on question type
        if question_type == "Rhetorical Synthesis":
            prompt += f"Notes: {ex['notes']}\n\n"
            prompt += f"Student's Goal: {ex['student_goal']}\n\n"
            prompt += "Answer Choices:\n"
            for letter in sorted(ex['answer_choices'].keys()):
                prompt += f"{letter}: {ex['answer_choices'][letter]}\n"
        elif question_type == "Transitions":
            prompt += f"Passage: {ex['passage']}\n\n"
            prompt += "Which choice completes the text with the most logical transition?\n\n"
            prompt += "Options:\n"
            for letter in sorted(ex['options'].keys()):
                prompt += f"{letter}: {ex['options'][letter]}\n"
        
        prompt += f"Answer: {ex['answer']}\n\n"
    
    # Add the actual question
    prompt += "Now, please answer this new question:\n\n"
    
    # Format based on question type
    if question_type == "Rhetorical Synthesis":
        notes = question_data.get("notes", "")
        student_goal = question_data.get("student_goal", "")
        answer_choices = question_data.get("answer_choices", {})
        
        prompt += f"Notes: {notes}\n\n"
        prompt += f"Student's Goal: {student_goal}\n\n"
        prompt += "Answer Choices:\n"
        for letter in sorted(answer_choices.keys()):
            prompt += f"{letter}: {answer_choices[letter]}\n"
    elif question_type == "Transitions":
        passage = question_data.get("passage", "")
        options = question_data.get("options", {})
        
        prompt += f"Passage: {passage}\n\n"
        prompt += "Which choice completes the text with the most logical transition?\n\n"
        prompt += "Options:\n"
        for letter in sorted(options.keys()):
            prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nProvide ONLY the letter of your answer (A, B, C, or D)."
    
    return prompt

# Generate chain-of-thought prompt
def generate_cot_prompt(question_data, question_type):
    """Generate a prompt that encourages step-by-step reasoning"""
    prompt = (
        f"Please solve the following {question_type} question using step-by-step reasoning.\n\n"
    )
    
    # Format based on question type
    if question_type == "Rhetorical Synthesis":
        notes = question_data.get("notes", "")
        student_goal = question_data.get("student_goal", "")
        answer_choices = question_data.get("answer_choices", {})
        
        prompt += f"Notes: {notes}\n\n"
        prompt += f"Student's Goal: {student_goal}\n\n"
        prompt += "Answer Choices:\n"
        for letter in sorted(answer_choices.keys()):
            prompt += f"{letter}: {answer_choices[letter]}\n"
    
    elif question_type == "Transitions":
        passage = question_data.get("passage", "")
        options = question_data.get("options", {})
        
        prompt += f"Passage: {passage}\n\n"
        prompt += "Which choice completes the text with the most logical transition?\n\n"
        prompt += "Options:\n"
        for letter in sorted(options.keys()):
            prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nPlease think through this problem carefully using the following steps:\n"
    
    if question_type == "Rhetorical Synthesis":
        prompt += "1. Understand the given notes and the student's goal\n"
        prompt += "2. Analyze each answer choice in relation to the notes and goal\n"
        prompt += "3. Determine which answer choice best fulfills the student's goal given the information in the notes\n"
    elif question_type == "Transitions":
        prompt += "1. Understand the context and meaning of the passage\n"
        prompt += "2. Identify the relationship between the sentences before and after the blank\n"
        prompt += "3. Consider each transition option and how it affects the flow and logic of the passage\n"
    
    prompt += "4. Evaluate each option carefully\n"
    prompt += "5. Explain your reasoning for selecting or rejecting each option\n"
    prompt += "6. Conclude with your final answer\n\n"
    prompt += "After your analysis, clearly indicate your final answer with 'Final Answer: [letter]'"
    
    return prompt

def main():
    parser = argparse.ArgumentParser(description="Evaluate LLM performance on SAT Expression of Ideas questions")
    parser.add_argument("--input", default="/home/ltang24/Education/SAT/Expression_of_ideas.json", 
                        help="Path to input JSON file with questions")
    parser.add_argument("--output", default="results", help="Output directory for results")
    parser.add_argument("--models", nargs="+", default=["gpt-4o-mini"],
                        help="List of models to evaluate")
    parser.add_argument("--strategies", nargs="+", default=["zero-shot", "five-shot", "chain-of-thought"],
                        help="List of prompting strategies to use")
    parser.add_argument("--questions_per_type", type=int, default=20, 
                        help="Number of questions to test per skill type")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds for model responses")
    parser.add_argument("--temp", type=float, default=0.3, help="Temperature setting for model calls")
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output, exist_ok=True)
    
    # Initialize G4F client
    client = Client()
    
    # Load questions
    print(f"Loading questions from {args.input}")
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Extract questions depending on JSON structure
        if isinstance(data, dict) and "questions" in data:
            questions = data["questions"]
        else:
            questions = data
            
        print(f"Loaded {len(questions)} total questions")
    except Exception as e:
        print(f"Error loading questions: {e}")
        return
    
    # Group questions by skill type
    questions_by_skill = {}
    for question in questions:
        skill = question.get("skill", "Unknown")
        if skill not in questions_by_skill:
            questions_by_skill[skill] = []
        questions_by_skill[skill].append(question)
    
    skill_types = ["Rhetorical Synthesis", "Transitions"]
    
    # Verify that each skill type has enough questions
    for skill in skill_types:
        if skill not in questions_by_skill:
            print(f"Warning: No questions found for skill type: {skill}")
            questions_by_skill[skill] = []
        else:
            print(f"Found {len(questions_by_skill[skill])} questions for skill type: {skill}")
            # Randomly select questions_per_type questions if there are more
            if len(questions_by_skill[skill]) > args.questions_per_type:
                questions_by_skill[skill] = random.sample(questions_by_skill[skill], args.questions_per_type)
    
    # Store all results
    all_results = {}
    
    # Test each model and strategy
    for model_name in args.models:
        all_results[model_name] = {}
        
        for strategy in args.strategies:
            print(f"\n{'-'*80}")
            print(f"Testing model: {model_name} with strategy: {strategy}")
            print(f"{'-'*80}")
            
            strategy_results = {
                "total": 0,
                "correct": 0,
                "accuracy": 0,
                "by_skill": {},
                "by_difficulty": {},
                "details": []
            }
            
            # Process each skill type
            for skill_type in skill_types:
                print(f"\nTesting skill type: {skill_type}")
                
                # Initialize skill results
                if skill_type not in strategy_results["by_skill"]:
                    strategy_results["by_skill"][skill_type] = {
                        "total": 0,
                        "correct": 0,
                        "accuracy": 0,
                        "by_difficulty": {}
                    }
                
                # Process questions for this skill type
                for question in questions_by_skill[skill_type]:
                    question_num = question.get("number", 0)
                    difficulty = question.get("difficulty", "Medium")
                    
                    # Get correct answer - use hardcoded answers dictionary if needed
                    if question_num in expression_skill_answers:
                        correct_answer = expression_skill_answers[question_num]
                    else:
                        correct_answer = question.get("correct_answer", "").strip().upper()
                    
                    # Debug info
                    if not correct_answer:
                        print(f"  WARNING: Missing correct answer for question {question_num}")
                        continue  # Skip questions with missing answers
                    
                    # Initialize difficulty counts for this skill type if not seen before
                    if difficulty not in strategy_results["by_skill"][skill_type]["by_difficulty"]:
                        strategy_results["by_skill"][skill_type]["by_difficulty"][difficulty] = {"total": 0, "correct": 0}
                    
                    # Initialize overall difficulty counts if not seen before
                    if difficulty not in strategy_results["by_difficulty"]:
                        strategy_results["by_difficulty"][difficulty] = {"total": 0, "correct": 0}
                    
                    print(f"\nQuestion {question_num} (Skill: {skill_type}, Difficulty: {difficulty}):")
                    
                    # Generate the appropriate prompt
                    if strategy == "zero-shot":
                        prompt = generate_zero_shot_prompt(question)
                    elif strategy == "five-shot":
                        prompt = generate_five_shot_prompt(question, skill_type)
                    else:  # chain-of-thought
                        prompt = generate_cot_prompt(question, skill_type)
                    
                    # Call the model
                    try:
                        start_time = time.time()
                        response = client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                            timeout=args.timeout,
                            temperature=args.temp
                        ).choices[0].message.content.strip()
                        runtime = round(time.time() - start_time, 2)
                        
                        # Extract the answer
                        model_answer = extract_answer(response)
                        is_correct = (model_answer == correct_answer)
                        
                        # Update statistics
                        strategy_results["total"] += 1
                        strategy_results["by_skill"][skill_type]["total"] += 1
                        strategy_results["by_skill"][skill_type]["by_difficulty"][difficulty]["total"] += 1
                        strategy_results["by_difficulty"][difficulty]["total"] += 1
                        
                        if is_correct:
                            strategy_results["correct"] += 1
                            strategy_results["by_skill"][skill_type]["correct"] += 1
                            strategy_results["by_skill"][skill_type]["by_difficulty"][difficulty]["correct"] += 1
                            strategy_results["by_difficulty"][difficulty]["correct"] += 1
                        
                        # Store result details
                        result_detail = {
                            "question_number": question_num,
                            "skill": skill_type,
                            "question_text": question.get("student_goal", "") if skill_type == "Rhetorical Synthesis" else "Transitions question",
                            "difficulty": difficulty,
                            "correct_answer": correct_answer,
                            "model_answer": model_answer,
                            "is_correct": is_correct,
                            "runtime": runtime,
                            "full_response": response[:1000] + "..." if len(response) > 1000 else response
                        }
                        strategy_results["details"].append(result_detail)
                        
                        print(f"  Model answer: {model_answer}, Correct answer: {correct_answer}")
                        print(f"  {'✓ Correct' if is_correct else '✗ Incorrect'} (Runtime: {runtime}s)")
                        
                    except Exception as e:
                        print(f"  Error getting model response: {e}")
                        
                        # Store error in details
                        result_detail = {
                            "question_number": question_num,
                            "skill": skill_type,
                            "question_text": question.get("student_goal", "") if skill_type == "Rhetorical Synthesis" else "Transitions question",
                            "difficulty": difficulty,
                            "correct_answer": correct_answer,
                            "model_answer": None,
                            "is_correct": False,
                            "error": str(e)
                        }
                        strategy_results["details"].append(result_detail)
                
                # Calculate accuracy for this skill type
                if strategy_results["by_skill"][skill_type]["total"] > 0:
                    strategy_results["by_skill"][skill_type]["accuracy"] = (
                        strategy_results["by_skill"][skill_type]["correct"] / 
                        strategy_results["by_skill"][skill_type]["total"]
                    )
                
                # Calculate accuracy by difficulty for this skill type
                for difficulty, counts in strategy_results["by_skill"][skill_type]["by_difficulty"].items():
                    if counts["total"] > 0:
                        counts["accuracy"] = counts["correct"] / counts["total"]
            
            # Calculate overall accuracy
            if strategy_results["total"] > 0:
                strategy_results["accuracy"] = strategy_results["correct"] / strategy_results["total"]
            
            # Calculate overall accuracy by difficulty
            for difficulty, counts in strategy_results["by_difficulty"].items():
                if counts["total"] > 0:
                    counts["accuracy"] = counts["correct"] / counts["total"]
            
            # Print summary
            print(f"\nSummary for {model_name} with {strategy}:")
            print(f"Overall Accuracy: {strategy_results['accuracy']:.2%} ({strategy_results['correct']}/{strategy_results['total']})")
            
            for skill_type in skill_types:
                skill_stats = strategy_results["by_skill"].get(skill_type, {})
                if skill_stats.get("total", 0) > 0:
                    print(f"\n  {skill_type} Accuracy: {skill_stats['accuracy']:.2%} ({skill_stats['correct']}/{skill_stats['total']})")
                    
                    for difficulty, stats in skill_stats.get("by_difficulty", {}).items():
                        if stats.get("total", 0) > 0:
                            print(f"    {difficulty} Difficulty: {stats['accuracy']:.2%} ({stats['correct']}/{stats['total']})")
            
            # Store results for this strategy
            all_results[model_name][strategy] = strategy_results
    
    # Save all results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = os.path.join(args.output, f"expression_of_ideas_results_{timestamp}.json")
    
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nAll results saved to {result_file}")
    
    # Generate summary report
    summary = {
        "timestamp": timestamp,
        "models_tested": args.models,
        "strategies_tested": args.strategies,
        "skill_types": skill_types,
        "questions_per_type": args.questions_per_type,
        "model_summaries": {}
    }
    
    for model_name in args.models:
        model_summary = {}
        for strategy in args.strategies:
            if model_name in all_results and strategy in all_results[model_name]:
                results = all_results[model_name][strategy]
                strategy_summary = {
                    "overall": {
                        "accuracy": results["accuracy"],
                        "correct": results["correct"],
                        "total": results["total"]
                    },
                    "by_skill": {},
                    "by_difficulty": {}
                }
                
                # Add skill type summaries
                for skill_type in skill_types:
                    if skill_type in results["by_skill"]:
                        skill_data = results["by_skill"][skill_type]
                        strategy_summary["by_skill"][skill_type] = {
                            "accuracy": skill_data.get("accuracy", 0),
                            "correct": skill_data.get("correct", 0),
                            "total": skill_data.get("total", 0),
                            "by_difficulty": skill_data.get("by_difficulty", {})
                        }
                
                # Add difficulty summaries
                for difficulty, data in results["by_difficulty"].items():
                    strategy_summary["by_difficulty"][difficulty] = {
                        "accuracy": data.get("accuracy", 0),
                        "correct": data.get("correct", 0),
                        "total": data.get("total", 0)
                    }
                
                model_summary[strategy] = strategy_summary
        
        summary["model_summaries"][model_name] = model_summary

    summary_file = os.path.join(args.output, f"summary_expression_{timestamp}.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Summary report saved to {summary_file}")

    # Generate a simplified CSV report for easy viewing
    csv_file = os.path.join(args.output, f"summary_expression_{timestamp}.csv")
    with open(csv_file, "w", encoding="utf-8") as f:
        # Write CSV header
        f.write("Model,Strategy,Overall Accuracy")
        for skill_type in skill_types:
            f.write(f",{skill_type} Accuracy")
        f.write("\n")
        
        # Write data rows
        for model_name in args.models:
            for strategy in args.strategies:
                if (model_name in summary["model_summaries"] and 
                    strategy in summary["model_summaries"][model_name]):
                    
                    model_strategy = summary["model_summaries"][model_name][strategy]
                    overall_acc = model_strategy["overall"]["accuracy"]
                    
                    f.write(f"{model_name},{strategy},{overall_acc:.2%}")
                    
                    for skill_type in skill_types:
                        if (skill_type in model_strategy["by_skill"] and
                            "accuracy" in model_strategy["by_skill"][skill_type]):
                            skill_acc = model_strategy["by_skill"][skill_type]["accuracy"]
                            f.write(f",{skill_acc:.2%}")
                        else:
                            f.write(",N/A")
                    
                    f.write("\n")

    print(f"CSV summary saved to {csv_file}")   

if __name__ == "__main__":
    main()