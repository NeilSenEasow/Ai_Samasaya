import google.generativeai as genai
from flask import Flask, request, render_template, jsonify, Response, redirect, url_for, send_from_directory, send_file, make_response, abort
import os
import pdfplumber
from google.cloud import aiplatform
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables
load_dotenv()

genai.configure(api_key=os.getenv("GOGGLE_API_KEY"))

# Directory for uploads
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Function to extract text from PDF using pdfplumber
def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

# Function to divide text into chapters based on headings
def divide_into_chapters(text):
    chapters = {}
    current_chapter = "Introduction"
    for line in text.splitlines():
        # Detect "Chapter" heading
        if line.strip().lower().startswith("chapter"):
            current_chapter = line.strip()
            chapters[current_chapter] = ""
        else:
            chapters[current_chapter] = chapters.get(current_chapter, "") + line + "\n"
    return chapters

# Function to summarize a chapter
def summarize_text(text):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
        Act like a professional teacher and summarize the following text in a way that is:
        1.divided into chapters with clear headings for each chapter. 
        2.  Short and simple, covering all the important points.
        3. Easy to understand for students, using clear and concise language.
        4. Breaking down the text into chapters with clear headings for each chapter.
        5. each chapter should show in different paragraph. and start from new line.
        if there is a topic then give atleast 2-3 lines about it.
        5. Including all the important keywords and concepts, explained in an easy-to-digest manner.
        6. Including examples and illustrations to help students understand the concepts better. but not too many. and not too complex. and keep sort summary.
        7. Including summaries, bullet points, or key takeaways at the end of each chapter. 
        8. all the important keywords and concepts, explained in an easy-to-digest manner.
        9. if there a topic then give atleast 2-3 lines about it.
        10. if there is a list of items then give atleast 2-3 lines about it.
        11. if there is a definition then give atleast 2-3 lines about it.
        12. if there is a example then give atleast 2-3 lines about it.
        13. if there is a concept then give atleast 2-3 lines about it.
        14. if there is a theory then give atleast 2-3 lines about it.
        15. if there is a formula then give atleast 2-3 lines about it.
        16. if there is a law then give atleast 2-3 lines about it.
        17. if there is a rule then give atleast 2-3 lines about it.
        18. if there is a principle then give atleast 2-3 lines about it.
        19. if there is a theorem then give atleast 2-3 lines about it.
        20. after each chapter give  space and start from new line. 
        21. divide the text into chapters with clear headings for each chapter.
        
        Here is the text to summarize:

    {text}
    """

    response = model.generate_content(prompt)
    return response.text

# Function to generate questions based on chapter content
def generate_questions(text):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
    Act like a professional teacher and summarize the following text in a way that is:
    your teaching a class and you want to ask questions from the following text.
    Generate  5 random quiz questions based on the following text:
    each question should be unique and should test the students' understanding of the concepts discussed in the text.
    Each question should be clear, concise, and easy to understand, with a single correct answer.
    each question should be mcq type and should have 4 options. 
    Each question should cover a different aspect of the text, testing the students' knowledge of different concepts.
    Each question should be relevant and important, focusing on key points discussed in the text.
    Each question should be well-structured, with proper grammar, punctuation, and spelling.
    Each question should be challenging and engaging, encouraging students to think critically and apply their knowledge.
    each question should be ask for answer when answer is entered it should show if it is correct or not.
    Here is the text to generate questions from:
    
    Provide 'Correct' if the answer is correct, or 'Incorrect' if the answer is wrong.
    
     \n\n{text}
    """
    
   
    response = model.generate_content(prompt)
    return response.text
    
# Function to parse questions generated by Gemini AI
def parse_gemini_questions(response_text):
    questions = []
    lines = response_text.split("\n")
    for line in lines:
        if line.startswith("Q:"):
            question = {"question": line[3:], "options": []}
            questions.append(question)
        elif line.startswith("-"):
            questions[-1]["options"].append(line[2:])
    return questions

# Home route
@app.route("/")
def index():
    global chapters_data  # Ensure chapters_data is accessible
    for chapter, data in chapters_data.items():
        if "questions" not in data or not data["questions"]:
            # Generate questions using Gemini AI
            prompt = f"""
            Generate 5 multiple-choice questions based on the following summary:
            {data['summary']}
            Each question should have 4 options, with one correct answer.
            """
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            
            # Parse and store questions (adjust parsing as per Gemini output format)
            questions = parse_gemini_questions(response.text)
            data["questions"] = questions

    return render_template("index.html", chapters=chapters_data, enumerate=enumerate)


# Route to handle the uploaded PDF
@app.route('/pdf', methods=['POST'])
def handle_pdf():
    if 'pdf' not in request.files:
        return render_template("error.html", message="No PDF uploaded.")
    
    pdf_file = request.files['pdf']
    if pdf_file.filename == '':
        return render_template("error.html", message="No file selected.")

    # Save the uploaded file
    pdf_path = os.path.join(UPLOAD_FOLDER, pdf_file.filename)
    pdf_file.save(pdf_path)

    # Extract text from the uploaded PDF
    text = extract_text_from_pdf(pdf_path)

    # Divide the text into chapters
    chapters = divide_into_chapters(text)

    results = {}
    for chapter, content in chapters.items():
        summary = summarize_text(content)
        questions = generate_questions(content)  # Only pass content, no need for question or user_answer
        results[chapter] = {"summary": summary, "questions": questions}

    # Render results in pdf.html
    return render_template("pdf.html", results=results)


@app.route("/check_answers", methods=["POST"])
def check_answers():
    user_answers = request.form.to_dict()  # Get user answers
    feedback = {}
    
    for chapter, data in chapters_data.items():
        chapter_feedback = []
        for idx, question in enumerate(data["questions"]):
            user_answer = user_answers.get(f"{chapter}_q{idx}", "")
            # Validate answer using Gemini AI
            prompt = f"""
            Question: {question['question']}
            Options: {', '.join(question['options'])}
            User's Answer: {user_answer}
            Is the user's answer correct? Provide feedback.
            """
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            chapter_feedback.append(response.text)  # Store feedback

        feedback[chapter] = chapter_feedback

    return render_template("result.html", feedback=feedback)




if __name__ == '__main__':
    app.run(debug=True)