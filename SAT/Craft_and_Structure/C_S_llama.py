import json
import re
import time
import os
from datetime import datetime
import sys
import argparse
from g4f.client import Client
import random

# Add this dictionary with correct answers for Words in Context questions
words_in_context_answers = {
    122: "B",
    123: "D",
    124: "B",
    125: "A",
    126: "B",
    127: "C",
    128: "B", 
    129: "D",
    130: "A",
    131: "B",
    132: "B",
    133: "A",
    134: "C",
    135: "D",
    136: "A",
    137: "C",
    138: "C",
    139: "B", 
    140: "A",
    141: "C",
    142: "C",
    143: "C",
    144: "A",
    145: "A",
    146: "D",
    147: "B",
    148: "C",
    149: "D",
    150: "A",
    151: "D",
    152: "A",
    153: "B",
    154: "C",
    155: "B",
    156: "B",
    157: "B",
    158: "C",
    159: "C",
    160: "C",
    161: "C",
    162: "A",
    163: "D",
    164: "B",
    165: "C",
    166: "A",
    167: "D",
    168: "D",
    169: "D",
    170: "C",
    171: "B",
    172: "A",
    173: "A",
    174: "B",
    175: "D",
    176: "D",
    177: "B",
    178: "D",
    179: "B",
    180: "C",
    181: "B",
    182: "B",
    183: "B",
    184: "D",
    185: "D",
    186: "C",
    187: "A",
    188: "D",
    189: "B",
    190: "B",
    191: "C",
    192: "B",
    193: "A",
    200: "B",
    201: "A",
    202: "C",
    203: "C",
    204: "D",
    205: "B",
    206: "A",
    207: "B",
    208: "B",
    209: "B",
    210: "C",
    211: "D",
    212: "B"
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
    text1 = question_data.get("text1", "")
    text2 = question_data.get("text2", "")
    question = question_data.get("question", "")
    options = question_data.get("options", {})
    
    prompt = (
        "Please solve the following reading comprehension question and select the single best answer (A/B/C/D).\n\n"
    )
    
    # Check if it's a Cross-Text Connections question (has both text1 and text2)
    if text1 and text2:
        prompt += f"Text 1:\n{text1}\n\n"
        prompt += f"Text 2:\n{text2}\n\n"
    # Check if it's a single text question
    elif text1 or text2:
        prompt += f"Text:\n{text1 or text2}\n\n"
    
    # Add the passage if it exists (for Text Structure and Purpose or Words in Context questions)
    if "passage" in question_data and question_data["passage"]:
        prompt += f"Text:\n{question_data['passage']}\n\n"
    elif "text" in question_data and question_data["text"]:
        prompt += f"Text:\n{question_data['text']}\n\n"
    
    prompt += f"Question: {question}\n\n"
    prompt += "Options:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nImportant: Provide ONLY the letter of your answer (A, B, C, or D)."
    return prompt

# Generate five-shot prompt with examples - other functions omitted for brevity
# Generate five-shot prompt with examples
def generate_five_shot_prompt(question_data, question_type):
    """Generate a prompt with five examples of the same type followed by the question"""
    # Define examples based on the question type
    examples = []
    
    if question_type == "Cross-Text Connections":
        examples = [
            {
                "text1": "In 1916, H. Dugdale Sykes disputed claims that The Two Noble Kinsmen was coauthored by William Shakespeare and John Fletcher. Sykes felt Fletcher's contributions to the play were obvious—Fletcher had a distinct style in his other plays, so much so that lines with that style were considered sufficient evidence of Fletcher's authorship. But for the lines not deemed to be by Fletcher, Sykes felt that their depiction of women indicated that their author was not Shakespeare but Philip Massinger.",
                "text2": "Scholars have accepted The Two Noble Kinsmen as coauthored by Shakespeare since the 1970s: it appears in all major one-volume editions of Shakespeare's complete works. Though scholars disagree about who wrote what exactly, it is generally held that on the basis of style, Shakespeare wrote all of the first act and most of the last, while John Fletcher authored most of the three middle acts.",
                "question": "Based on the texts, both Sykes in Text 1 and the scholars in Text 2 would most likely agree with which statement?",
                "options": {
                    "A": "John Fletcher's writing has a unique, readily identifiable style.",
                    "B": "The women characters in John Fletcher's plays are similar to the women characters in Philip Massinger's plays.",
                    "C": "The Two Noble Kinsmen belongs in one-volume compilations of Shakespeare's complete plays.",
                    "D": "Philip Massinger's style in the first and last acts of The Two Noble Kinsmen is an homage to Shakespeare's style."
                },
                "answer": "A"
            },
            {
                "text1": "Public policy researcher Anthony Fowler studied the history of elections in Australia, a country that requires citizens to vote. Fowler argues that requiring citizens to vote leads to a significant increase in voters who would otherwise not have the time or motivation to vote. Thus, election results in countries that require citizens to vote better reflect the preferences of the country as a whole.",
                "text2": "Governments in democratic countries function better when more people vote. However, forcing people to vote may have negative consequences. Shane P. Singh and Jason Roy studied what happens when a country requires its citizens to vote. They found that when people feel forced to vote, they tend to spend less time looking for information about their choices when voting. As a result, votes from these voters may not reflect their actual preferences.",
                "question": "Based on the texts, how would Singh and Roy (Text 2) most likely respond to the research discussed in Text 1?",
                "options": {
                    "A": "Only countries of a certain population size should implement mandatory voting.",
                    "B": "People who are forced to vote are likely to become politically engaged in other ways, such as volunteering or running for office.",
                    "C": "Requiring people to vote does not necessarily lead to election outcomes that better represent the preferences of the country as a whole.",
                    "D": "Countries that require voting must also make the process of voting easier for their citizens."
                },
                "answer": "C"
            },
            {
                "text1": "Africa's Sahara region—once a lush ecosystem—began to dry out about 8,000 years ago. A change in Earth's orbit that affected climate has been posited as a cause of desertification, but archaeologist David Wright also attributes the shift to Neolithic peoples. He cites their adoption of pastoralism as a factor in the region drying out: the pastoralists' livestock depleted vegetation, prompting the events that created the Sahara Desert.",
                "text2": "Research by Chris Brierley et al. challenges the idea that Neolithic peoples contributed to the Sahara's desertification. Using a climate-vegetation model, the team concluded that the end of the region's humid period occurred 500 years earlier than previously assumed. The timing suggests that Neolithic peoples didn't exacerbate aridity in the region but, in fact, may have helped delay environmental changes with practices (e.g., selective grazing) that preserved vegetation.",
                "question": "Based on the texts, how would Chris Brierley (Text 2) most likely respond to the discussion in Text 1?",
                "options": {
                    "A": "By pointing out that given the revised timeline for the end of the Sahara's humid period, the Neolithic peoples' mode of subsistence likely didn't cause the region's desertification",
                    "B": "By claiming that pastoralism was only one of many behaviors the Neolithic peoples took part in that may have contributed to the Sahara's changing climate",
                    "C": "By insisting that pastoralism can have both beneficial and deleterious effects on a region's vegetation and climate",
                    "D": "By asserting that more research needs to be conducted into factors that likely contributed to the desertification of the Sahara region"
                },
                "answer": "A"
            },
            {
                "text1": "Dance choreographer Alvin Ailey's deep admiration for jazz music can most clearly be felt in the rhythms and beats his works were set to. Ailey collaborated with some of the greatest jazz legends, like Charles Mingus, Charlie Parker, and perhaps his favorite, Duke Ellington. With his choice of music, Ailey helped bring jazz to life for his audiences.",
                "text2": "Jazz is present throughout Ailey's work, but it's most visible in Ailey's approach to choreography. Ailey often incorporated improvisation, a signature characteristic of jazz music, in his work. When managing his dance company, Ailey rarely forced his dancers to an exact set of specific moves. Instead, he encouraged his dancers to let their own skills and experiences shape their performances, as jazz musicians do.",
                "question": "Based on the texts, both authors would most likely agree with which statement?",
                "options": {
                    "A": "Dancers who worked with Ailey greatly appreciated his supportive approach as a choreographer.",
                    "B": "Ailey's work was strongly influenced by jazz.",
                    "C": "Audiences were mostly unfamiliar with the jazz music in Ailey's works.",
                    "D": "Ailey blended multiple genres of music together when choreographing dance pieces."
                },
                "answer": "B"
            },
            {
                "text1": "Microbes are tiny organisms in the soil, water, and air all around us. They thrive even in very harsh conditions. That's why Noah Fierer and colleagues were surprised when soil samples they collected from an extremely cold, dry area in Antarctica didn't seem to contain any life. The finding doesn't prove that there are no microbes in that area, but the team says it does suggest that the environment severely restricts microbes' survival.",
                "text2": "Microbes are found in virtually every environment on Earth. So it's unlikely they would be completely absent from Fierer's team's study site, no matter how extreme the environment is. There were probably so few organisms in the samples that current technology couldn't detect them. But since a spoonful of typical soil elsewhere might contain billions of microbes, the presence of so few in the Antarctic soil samples would show how challenging the conditions are.",
                "question": "Based on the texts, Fierer's team and the author of Text 2 would most likely agree with which statement about microbes?",
                "options": {
                    "A": "Most microbes are better able to survive in environments with extremely dry conditions than in environments with harsh temperatures.",
                    "B": "A much higher number of microbes would probably be found if another sample of soil were taken from the Antarctic study site.",
                    "C": "Microbes are likely difficult to detect in the soil at the Antarctic study site because they tend to be smaller than microbes found in typical soil elsewhere.",
                    "D": "Most microbes are probably unable to withstand the soil conditions at the Antarctic study site."
                },
                "answer": "D"
            }
        ]
    elif question_type == "Text Structure and Purpose":
        examples = [
            {
                "text": "\"How lifelike are they?\" Many computer animators prioritize this question as they strive to create ever more realistic environments and lighting. Generally, while characters in computer-animated films appear highly exaggerated, environments and lighting are carefully engineered to mimic reality. But some animators, such as Pixar's Sanjay Patel, are focused on a different question. Rather than asking first whether the environments and lighting they're creating are convincingly lifelike, Patel and others are asking whether these elements reflect their films' unique stories.",
                "question": "Which choice best describes the function of the underlined question in the text as a whole?",
                "options": {
                    "A": "It reflects a primary goal that many computer animators have for certain components of the animations they produce.",
                    "B": "It represents a concern of computer animators who are more interested in creating unique backgrounds and lighting effects than realistic ones.",
                    "C": "It conveys the uncertainty among many computer animators about how to create realistic animations using current technology.",
                    "D": "It illustrates a reaction that audiences typically have to the appearance of characters created by computer animators."
                },
                "answer": "A"
            },
            {
                "text": "The field of study called affective neuroscience seeks instinctive, physiological causes for feelings such as pleasure or displeasure. Because these sensations are linked to a chemical component (for example, the release of the neurotransmitter dopamine in the brain when one receives or expects a reward), they can be said to have a partly physiological basis. These processes have been described in mammals, but Jingnan Huang and his colleagues have recently observed that some behaviors of honeybees (such as foraging) are also motivated by a dopamine-based signaling process.",
                "question": "What choice best describes the main purpose of the text?",
                "options": {
                    "A": "It describes an experimental method of measuring the strength of physiological responses in humans.",
                    "B": "It illustrates processes by which certain insects can express how they are feeling.",
                    "C": "It summarizes a finding suggesting that some mechanisms in the brains of certain insects resemble mechanisms in mammalian brains.",
                    "D": "It presents research showing that certain insects and mammals behave similarly when there is a possibility of a reward for their actions."
                },
                "answer": "C"
            },
            {
                "text": "The following text is from Srimati Svarna Kumari Devi's 1894 novel The Fatal Garland (translated by A. Christina Albers in 1910). Shakti is walking near a riverbank that she visited frequently during her childhood. \n\n\"She crossed the woods she knew so well. The trees seemed to extend their branches like welcoming arms. They greeted her as an old friend. Soon she reached the river-side.\"",
                "question": "Which choice best describes the function of the underlined portion in the text as a whole?",
                "options": {
                    "A": "It suggests that Shakti feels uncomfortable near the river.",
                    "B": "It indicates that Shakti has lost her sense of direction in the woods.",
                    "C": "It emphasizes Shakti's sense of belonging in the landscape.",
                    "D": "It conveys Shakti's appreciation for her long-term friendships."
                },
                "answer": "C"
            },
            {
                "text": "Early in the Great Migration of 1910–1970, which involved the mass migration of Black people from the southern to the northern United States, political activist and Chicago Defender writer Fannie Barrier Williams was instrumental in helping other Black women establish themselves in the North. Many women hoped for better employment opportunities in the North because, in the South, they faced much competition for domestic employment and men tended to get agricultural work. To aid with this transition, Barrier Williams helped secure job placement in the North for many women before they even began their journey.",
                "question": "Which choice best states the main purpose of the text?",
                "options": {
                    "A": "To introduce and illustrate Barrier Williams's integral role in supporting other Black women as their circumstances changed during part of the Great Migration",
                    "B": "To establish that Barrier Williams used her professional connections to arrange employment for other Black women, including jobs with the Chicago Defender",
                    "C": "To demonstrate that the factors that motivated the start of the Great Migration were different for Black women than they were for Black men",
                    "D": "To provide an overview of the employment challenges faced by Black women in the agricultural and domestic spheres in the southern United States"
                },
                "answer": "A"
            },
            {
                "text": "Studying late nineteenth- and early twentieth-century artifacts from an agricultural and domestic site in Texas, archaeologist Ayana O. Flewellen found that Black women employed as farm workers utilized hook-and-eye closures to fasten their clothes at the waist, giving themselves a silhouette similar to the one that was popular in contemporary fashion and typically achieved through more restrictive garments such as corsets. Flewellen argues that this sartorial practice shows that these women balanced hegemonic ideals of femininity with the requirements of their physically demanding occupation.",
                "question": "Which choice best states the main purpose of the text?",
                "options": {
                    "A": "To describe an unexpected discovery that altered a researcher's view of how rapidly fashions among Black female farmworkers in late nineteenth- and early twentieth-century Texas changed during the period",
                    "B": "To discuss research that investigated the ways in which Black female farmworkers in late nineteenth- and early twentieth-century Texas used fashion practices to resist traditional gender ideals",
                    "C": "To evaluate a scholarly work that offers explanations for the impact of urban fashion ideals on Black female farmworkers in late nineteenth- and early twentieth-century Texas",
                    "D": "To summarize the findings of a study that explored factors influencing a fashion practice among Black female farmworkers in late nineteenth- and early twentieth-century Texas"
                },
                "answer": "D"
            }
        ]
    elif question_type == "Words in Context":
        examples = [
            {
                "passage": "Artist Marilyn Dingle's intricate, coiled baskets are ______blank sweetgrass and palmetto palm. Following a Gullah technique that originated in West Africa, Dingle skillfully winds a thin palm frond around a bunch of sweetgrass with the help of a 'sewing bone' to create the basket's signature look that no factory can reproduce.",
                "question": "Which choice completes the text with the most logical and precise word or phrase?",
                "options": {
                    "A": "indicated by",
                    "B": "handmade from",
                    "C": "represented by",
                    "D": "collected with"
                },
                "answer": "B"
            },
            {
                "passage": "The following text is adapted from Nathaniel Hawthorne's 1837 story 'Dr. Heidegger's Experiment.' The main character, a physician, is experimenting with rehydrating a dried flower.\nAt first [the rose] lay lightly on the surface of the fluid, appearing to imbibe none of its moisture. Soon, however, a singular change began to be visible. The crushed and dried petals stirred and assumed a deepening tinge of crimson, as if the flower were reviving from a deathlike slumber.",
                "question": "As used in the text, what does the phrase \"a singular\" most nearly mean?",
                "options": {
                    "A": "a lonely",
                    "B": "a disagreeable",
                    "C": "an acceptable",
                    "D": "an extraordinary"
                },
                "answer": "D"
            },
            {
                "passage": "Rejecting the premise that the literary magazine Ebony and Topaz (1927) should present a unified vision of Black American identity, editor Charles S. Johnson fostered his contributors' diverse perspectives by promoting their authorial autonomy. Johnson's self-effacement diverged from the editorial stances of W.E.B. Du Bois and Alain Locke, whose decisions for their publications were more ______blank.",
                "question": "Which choice completes the text with the most logical and precise word or phrase?",
                "options": {
                    "A": "proficient",
                    "B": "dogmatic",
                    "C": "ambiguous",
                    "D": "unpretentious"
                },
                "answer": "B"
            },
            {
                "passage": "Some economic historians ______blank that late nineteenth- and early twentieth-century households in the United States experienced an economy of scale when it came to food purchases—they assumed that large households spent less on food per person than did small households. Economist Trevon Logan showed, however, that a close look at the available data disproves this supposition.",
                "question": "Which choice completes the text with the most logical and precise word or phrase?",
                "options": {
                    "A": "surmised",
                    "B": "contrived",
                    "C": "questioned",
                    "D": "regretted"
                },
                "answer": "A"
            },
            {
                "passage": "The following text is from Bram Stoker's 1897 novel Dracula. The narrator is being driven in a carriage through a remote region at night.\n\nThe baying of the wolves sounded nearer and nearer, as though they were closing round on us from every side. I grew dreadfully afraid, and the horses shared my fear. The driver, however, was not in the least disturbed; he kept turning his head to left and right, but I could not see anything through the darkness.",
                "question": "As used in the text, what does the word \"disturbed\" most nearly mean?",
                "options": {
                    "A": "Disorganized",
                    "B": "Alarmed",
                    "C": "Offended",
                    "D": "Interrupted"
                },
                "answer": "B"
            }
        ]
    
    prompt = f"I'll show you five examples of {question_type} questions and their answers, then ask you a new question.\n\n"
    
    for i, ex in enumerate(examples):
        prompt += f"Example {i+1}:\n"
        
        # Format based on question type
        if question_type == "Cross-Text Connections":
            prompt += f"Text 1: {ex['text1']}\n\n"
            prompt += f"Text 2: {ex['text2']}\n\n"
        elif question_type == "Text Structure and Purpose" or question_type == "Words in Context":
            if "text" in ex:
                prompt += f"Text: {ex['text']}\n\n"
            elif "passage" in ex:
                prompt += f"Text: {ex['passage']}\n\n"
        
        prompt += f"Question: {ex['question']}\n"
        prompt += "Options:\n"
        for letter in sorted(ex['options'].keys()):
            prompt += f"{letter}: {ex['options'][letter]}\n"
        prompt += f"Answer: {ex['answer']}\n\n"
    
    # Add the actual question
    prompt += "Now, please answer this new question:\n\n"
    
    # Format based on question type
    if question_type == "Cross-Text Connections":
        text1 = question_data.get("text1", "")
        text2 = question_data.get("text2", "")
        prompt += f"Text 1: {text1}\n\n"
        prompt += f"Text 2: {text2}\n\n"
    elif question_type == "Text Structure and Purpose" or question_type == "Words in Context":
        if "text" in question_data:
            prompt += f"Text: {question_data['text']}\n\n"
        elif "passage" in question_data:
            prompt += f"Text: {question_data['passage']}\n\n"
    
    question = question_data.get("question", "")
    options = question_data.get("options", {})
    
    prompt += f"Question: {question}\n"
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
    if question_type == "Cross-Text Connections":
        text1 = question_data.get("text1", "")
        text2 = question_data.get("text2", "")
        prompt += f"Text 1: {text1}\n\n"
        prompt += f"Text 2: {text2}\n\n"
    elif question_type == "Text Structure and Purpose" or question_type == "Words in Context":
        if "text" in question_data:
            prompt += f"Text: {question_data['text']}\n\n"
        elif "passage" in question_data:
            prompt += f"Text: {question_data['passage']}\n\n"
    
    question = question_data.get("question", "")
    options = question_data.get("options", {})
    
    prompt += f"Question: {question}\n\n"
    prompt += "Options:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nPlease think through this problem carefully using the following steps:\n"
    
    if question_type == "Cross-Text Connections":
        prompt += "1. Understand what the question is asking\n"
        prompt += "2. Analyze key information from Text 1\n"
        prompt += "3. Analyze key information from Text 2\n"
        prompt += "4. Identify connections or contrasts between the two texts\n"
    elif question_type == "Text Structure and Purpose":
        prompt += "1. Understand what the question is asking\n"
        prompt += "2. Examine the structure and purpose of the text\n"
        prompt += "3. Identify how different parts of the text function\n"
    elif question_type == "Words in Context":
        prompt += "1. Understand what the question is asking\n"
        prompt += "2. Analyze the context in which the word or phrase is used\n"
        prompt += "3. Consider the meaning and nuance of each option\n"
    
    prompt += "4. Evaluate each option carefully\n"
    prompt += "5. Explain your reasoning for selecting or rejecting each option\n"
    prompt += "6. Conclude with your final answer\n\n"
    prompt += "After your analysis, clearly indicate your final answer with 'Final Answer: [letter]'"
    
    return prompt
def main():
    parser = argparse.ArgumentParser(description="Evaluate LLM performance on reading comprehension questions by skill type")
    parser.add_argument("--input", default="/home/ltang24/Education/SAT/Craft_and_Structure.json", 
                        help="Path to input JSON file with questions")
    parser.add_argument("--output", default="results", help="Output directory for results")
    parser.add_argument("--models", nargs="+", default=[ "llama-3.1-8b", "llama-3.1-70b", 
                                                         "llama-3.1-405b"],
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
    
    skill_types = ["Cross-Text Connections", "Text Structure and Purpose", "Words in Context"]
    
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
                    difficulty = question.get("questionDifficulty", "Medium")
                    
                    # Get correct answer - use our hardcoded answers dictionary for Words in Context
                    if skill_type == "Words in Context" and question_num in words_in_context_answers:
                        correct_answer = words_in_context_answers[question_num]
                    else:
                        correct_answer = question.get("correctAnswer", "").strip().upper()
                    
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
                            "question_text": question.get("question", ""),
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
                            "question_text": question.get("question", ""),
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
    result_file = os.path.join(args.output, f"reading_comp_results_{timestamp}.json")
    
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
    
    summary_file = os.path.join(args.output, f"summary_{timestamp}.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    
    print(f"Summary report saved to {summary_file}")
    
    # Generate a simplified CSV report for easy viewing
    csv_file = os.path.join(args.output, f"summary_{timestamp}.csv")
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