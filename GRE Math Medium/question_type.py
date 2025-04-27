import os
import json
import easyocr
import re

# Define directories
source_dir = "/home/ltang24/Education/GRE Math Medium/"

# Initialize the OCR reader
reader = easyocr.Reader(['en'])

def determine_question_type(text):
    # Join all text pieces into a single string for easier analysis
    full_text = " ".join(text).lower()
    
    # Debug print to see what text is being extracted
    print(f"Extracted text: {full_text[:200]}...")  # Print first 200 chars
    
    # Check for quantitative comparison questions
    if "quantity a" in full_text and "quantity b" in full_text:
        print("Found quantitative comparison patterns")
        return "quantitative_comparison"
    
    # Check for multiple-choice multiple answer questions
    if any(phrase in full_text for phrase in ["indicate all", "select all", "one or more", "could be"]):
        print("Found multiple-choice multiple patterns")
        return "multiple_choice_multiple"
    
    # More flexible check for multiple-choice single answer questions
    option_patterns = [
        r'\ba\s*[\.:\)_]', r'\bb\s*[\.:\)_]', r'\bc\s*[\.:\)_]', r'\bd\s*[\.:\)_]', r'\be\s*[\.:\)_]',  # a. b. c. etc.
        r'\(a\)', r'\(b\)', r'\(c\)', r'\(d\)', r'\(e\)',  # (a) (b) etc.
        r'\ba\b.*\bb\b.*\bc\b',  # Just a, b, c in sequence
    ]
    
    # Also check for options with numbers following (a then number, b then number, etc.)
    has_numbered_options = bool(re.search(r'\ba\s*[-:\._ )]*\s*\d+.*\bb\s*[-:\._ )]*\s*\d+', full_text))
    
    option_matches = [bool(re.search(pattern, full_text)) for pattern in option_patterns]
    
    if any(option_matches) or has_numbered_options:
        print("Found multiple-choice single patterns with regular expressions")
        return "multiple_choice_single"
    
    # If we see strings like "a 12 b 18 c 36" - these are likely answer choices
    if re.search(r'\b[a-e]\b\s*\d+.*\b[a-e]\b\s*\d+', full_text):
        print("Found multiple-choice pattern with letters and numbers")
        return "multiple_choice_single"
    
    # If no answer choices are found, it's likely a numeric entry question
    print("No answer choices found, classifying as numeric entry")
    return "numeric_entry"

# Load existing JSON data
json_data = None
with open(os.path.join(source_dir, '/home/ltang24/Education/GRE Math Medium/GRE Math Medium.json'), 'r') as f:
    json_data = json.loads(f.read())

# Create a list of PNG files to process
png_files = [f for f in os.listdir(source_dir) if f.endswith(".png")]
total_files = len(png_files)

# Dictionary to store categorizations
categorizations = {}

# Process each image file
for i, filename in enumerate(png_files):
    file_path = os.path.join(source_dir, filename)
    
    print(f"\nProcessing {filename} ({i+1}/{total_files})")
    
    question_number = filename.split('.')[0]  # Extract number from filename
    
    # Extract text from image
    try:
        result = reader.readtext(file_path, detail=0)
        
        # Determine question type
        question_type = determine_question_type(result)
        
        # Store the categorization
        categorizations[question_number] = question_type
        print(f"Classified {filename} as {question_type}")
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        categorizations[question_number] = "error"

# Add categorization to the JSON data
for item in json_data["GRE Math Medium.json"]:
    question_number = item["question_number"]
    if question_number in categorizations:
        item["question_type"] = categorizations[question_number]

# Save the updated JSON data
output_json_path = os.path.join(source_dir, "gre_math_categorized.json")
with open(output_json_path, 'w') as f:
    json.dump(json_data, f, indent=4)

print(f"\nClassification complete! Results saved to {output_json_path}")