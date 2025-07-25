import streamlit as st
import requests
import json
import uuid # For generating anonymous user IDs if needed
import keys

# --- Configuration ---
# IMPORTANT: Replace with your actual Google Gemini API key.
# If running in a Canvas environment, __api_key__ might be provided automatically.
# Otherwise, you need to get one from Google AI Studio.
API_KEY = keys.API_Key # Leave empty if running in Canvas, otherwise paste your API key here.
GEMINI_MODEL = "gemini-2.0-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={API_KEY}"

# --- Firebase Configuration (Placeholder for future persistence) ---
# In a real Canvas environment, __app_id__, __firebase_config__, __initial_auth_token__
# would be globally available. For a standalone script, these are placeholders.
# If you were to integrate Firestore, you'd initialize Firebase here.
# For this example, we are not using Firestore for persistence, but the structure
# is shown for completeness if the user asks for it later.
app_id = "default-app-id" # Placeholder
firebase_config = {} # Placeholder
initial_auth_token = None # Placeholder
# --- Helper Function for Gemini API Calls ---
def call_gemini_api(prompt_parts, generation_config=None, system_instruction=None):
    """
    Makes a call to the Gemini API with the given prompt parts and configuration.
    """
    headers = {
        'Content-Type': 'application/json'
    }

    # Construct the base payload
    payload = {
        "contents": prompt_parts,
    }

    if generation_config:
        payload["generationConfig"] = generation_config
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        result = response.json()

        if result.get("candidates") and result["candidates"][0].get("content") and \
           result["candidates"][0]["content"].get("parts") and \
           result["candidates"][0]["content"]["parts"][0].get("text"):
            return result["candidates"][0]["content"]["parts"][0]["text"]
        else:
            st.error(f"Gemini API returned an unexpected response structure: {result}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error calling Gemini API: {e}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"Error decoding JSON response from Gemini API: {e}. Response text: {response.text}")
        return None

# --- Streamlit Session State Initialization ---
def initialize_session_state():
    """Initializes all necessary session state variables."""
    if "session_started" not in st.session_state:
        st.session_state.session_started = False
        st.session_state.concept = ""
        st.session_state.difficulty = "Beginner"
        st.session_state.role = ""
        st.session_state.chat_history = [] # Stores user/model interactions for display
        st.session_state.llm_chat_history = [] # Stores history for LLM context (buffer window)
        st.session_state.current_question = ""
        st.session_state.current_concept_chunk = ""
        st.session_state.concept_chunks = []
        st.session_state.chunk_index = 0
        st.session_state.learning_goal = ""
        st.session_state.org_benefit = ""
        st.session_state.feedback_message = ""
        st.session_state.user_answer = ""
        st.session_state.session_ended = False
        st.session_state.user_id = str(uuid.uuid4()) # Generate a unique ID for anonymous users

# --- LLM Prompt Definitions ---

# System instruction for breaking down the concept
BREAKDOWN_SYSTEM_PROMPT = """
You are an expert educator. Your task is to break down a given concept into 5-8 smaller, sequential learning chunks.
Each chunk should represent a foundational aspect or a logical progression in understanding the concept.
Provide only the list of chunks, one per line, without any introductory or concluding remarks.
Example:
Concept: Photosynthesis
Chunks:
1. What is Photosynthesis?
2. Key Components: Chlorophyll, Sunlight, Water, CO2
3. Light-Dependent Reactions
4. Light-Independent Reactions (Calvin Cycle)
5. Products and Importance
6. Factors Affecting Photosynthesis
"""

# System instructAPI_Key = 'AIzaSyC3mqFeZPHGkLhEFWlAs8CQkRjcx9X8MdQ'ion for generating questions
QUESTION_SYSTEM_PROMPT = """
You are an adaptive learning AI. Your goal is to generate a single, clear, and concise question based on the provided concept chunk, difficulty level, and user's role.
The question should assess the user's understanding of that specific chunk.
Consider the previous conversation history to avoid repetitive questions and to build upon prior knowledge.
If the user's role is provided, tailor the question slightly to be relevant to their professional context if applicable, but keep it focused on the core concept.
Do not provide answers or hints in the question.
"""

# System instruction for evaluating answers
EVALUATION_SYSTEM_PROMPT = """
You are an adaptive learning AI. Your task is to evaluate a user's answer to a given question based on the correct concept chunk information.
Provide concise feedback:
1. State clearly if the answer is "Correct", "Partially Correct", or "Incorrect".
2. If "Partially Correct" or "Incorrect", explain why and provide a hint or point them towards the correct understanding without giving the full answer.
3. Suggest if they should move to the next concept chunk ("Ready for next chunk") or need more questions on the current chunk ("Needs more practice on this chunk").
4. If they are ready for the next chunk, briefly summarize what they got right.
5. If they need more practice, briefly explain what they missed.

Format your response clearly.
"""

# System instruction for generating session goals and benefits
GOAL_BENEFIT_SYSTEM_PROMPT = """
You are an educational consultant. Based on the concept learned, the user's role, and the difficulty level, articulate:
1.  **Learning Goal:** What specific knowledge or skill should the candidate know/do at the end of this session? (Focus on actionable outcomes).
2.  **Organizational Benefit:** How will their organization benefit from the candidate acquiring this knowledge/skill? (Focus on tangible value).

Format your response clearly with "Learning Goal:" and "Organizational Benefit:" headings.
"""

# --- Core Logic Functions ---

def update_llm_chat_history(role, text):
    """Adds a new message to the LLM's chat history, maintaining a buffer window."""
    st.session_state.llm_chat_history.append({"role": role, "parts": [{"text": text}]})
    # Keep only the last 10 interactions (5 user, 5 model)
    if len(st.session_state.llm_chat_history) > 10:
        st.session_state.llm_chat_history = st.session_state.llm_chat_history[-10:]

def start_session_logic(concept, difficulty, role):
    """Handles the initial setup of the learning session."""
    st.session_state.session_started = True
    st.session_state.concept = concept
    st.session_state.difficulty = difficulty
    st.session_state.role = role
    st.session_state.chat_history.append({"role": "system", "content": f"Starting session on '{concept}' at '{difficulty}' difficulty for a '{role}'."})
    st.session_state.llm_chat_history.append({"role": "system", "parts": [{"text": f"User wants to learn '{concept}' at '{difficulty}' difficulty. User's role: '{role}'."}]})

    with st.spinner("Breaking down the concept and setting session goals..."):
        # 1. Break down the concept
        breakdown_prompt = [{"role": "user", "parts": [{"text": f"Concept: {concept}"}]}]
        chunks_response = call_gemini_api(breakdown_prompt, system_instruction=BREAKDOWN_SYSTEM_PROMPT)
        if chunks_response:
            st.session_state.concept_chunks = [c.strip() for c in chunks_response.split('\n') if c.strip()]
            st.session_state.chat_history.append({"role": "system", "content": "Concept broken down into chunks."})
        else:
            st.session_state.chat_history.append({"role": "error", "content": "Failed to break down concept. Please try again."})
            st.session_state.session_started = False
            return

        # 2. Define session goal and organizational benefit
        goal_benefit_prompt = [{"role": "user", "parts": [{"text": f"Concept: {concept}\nDifficulty: {difficulty}\nRole: {role}"}]}]
        goal_benefit_response = call_gemini_api(goal_benefit_prompt, system_instruction=GOAL_BENEFIT_SYSTEM_PROMPT)
        if goal_benefit_response:
            lines = goal_benefit_response.split('\n')
            goal_found = False
            benefit_found = False
            for line in lines:
                if line.startswith("**Learning Goal:**"):
                    st.session_state.learning_goal = line.replace("Learning Goal:", "").strip()
                    goal_found = True
                elif line.startswith("**Organizational Benefit:**"):
                    st.session_state.org_benefit = line.replace("Organizational Benefit:", "").strip()
                    benefit_found = True
            if not goal_found or not benefit_found:
                st.session_state.chat_history.append({"role": "error", "content": "Failed to extract full session goals/benefits."})
        else:
            st.session_state.chat_history.append({"role": "error", "content": "Failed to generate session goals/benefits."})

    # Generate the first question
    if st.session_state.concept_chunks:
        st.session_state.current_concept_chunk = st.session_state.concept_chunks[st.session_state.chunk_index]
        generate_next_question()
    else:
        st.session_state.chat_history.append({"role": "error", "content": "No concept chunks generated. Session cannot proceed."})
        st.session_state.session_started = False

def generate_next_question():
    """Generates a question based on the current concept chunk."""
    if st.session_state.chunk_index < len(st.session_state.concept_chunks):
        chunk = st.session_state.concept_chunks[st.session_state.chunk_index]
        st.session_state.current_concept_chunk = chunk
        prompt_text = f"Generate a question for the concept chunk: '{chunk}'. Difficulty: {st.session_state.difficulty}. User's role: {st.session_state.role}."
        
        # Prepare LLM chat history for context
        llm_context_history = st.session_state.llm_chat_history + [{"role": "user", "parts": [{"text": prompt_text}]}]

        with st.spinner(f"Generating question for '{chunk}'..."):
            question_response = call_gemini_api(llm_context_history, system_instruction=QUESTION_SYSTEM_PROMPT)
            print(question_response)
            exit()
            if question_response:
                st.session_state.current_question = question_response.strip()
                st.session_state.chat_history.append({"role": "model", "content": st.session_state.current_question})
                update_llm_chat_history("model", st.session_state.current_question)
                st.session_state.feedback_message = ""
            else:
                st.session_state.chat_history.append({"role": "error", "content": "Failed to generate question. Please refresh."})
                st.session_state.session_ended = True # End session if questions can't be generated
    else:
        st.session_state.session_ended = True
        st.session_state.chat_history.append({"role": "system", "content": "You have completed all concept chunks!"})

def handle_user_answer():
    """Processes the user's answer and evaluates it."""
    user_answer = st.session_state.user_answer_input
    if not user_answer.strip():
        st.session_state.feedback_message = "Please enter an answer."
        return

    st.session_state.chat_history.append({"role": "user", "content": user_answer})
    update_llm_chat_history("user", user_answer)

    evaluation_prompt_text = (
        f"Question: {st.session_state.current_question}\n"
        f"User Answer: {user_answer}\n"
        f"Concept Chunk (for context of correct answer): {st.session_state.current_concept_chunk}\n"
        f"Previous conversation context:\n"
        f"{json.dumps(st.session_state.llm_chat_history)}" # Pass history for context
    )
    
    # Prepare LLM chat history for context
    llm_context_history = st.session_state.llm_chat_history + [{"role": "user", "parts": [{"text": evaluation_prompt_text}]}]

    with st.spinner("Evaluating your answer..."):
        evaluation_response = call_gemini_api(llm_context_history, system_instruction=EVALUATION_SYSTEM_PROMPT)
        if evaluation_response:
            st.session_state.feedback_message = evaluation_response.strip()
            st.session_state.chat_history.append({"role": "model", "content": st.session_state.feedback_message})
            update_llm_chat_history("model", st.session_state.feedback_message)

            if "Ready for next chunk" in evaluation_response:
                st.session_state.chunk_index += 1
                if st.session_state.chunk_index < len(st.session_state.concept_chunks):
                    generate_next_question()
                else:
                    st.session_state.session_ended = True
                    st.session_state.chat_history.append({"role": "system", "content": "Congratulations! You've completed the learning session."})
            # If "Needs more practice" or "Partially Correct", stay on current chunk and re-prompt for answer
            st.session_state.user_answer_input = "" # Clear input after processing
        else:
            st.session_state.feedback_message = "Failed to evaluate answer. Please try again."
            st.session_state.chat_history.append({"role": "error", "content": st.session_state.feedback_message})


# --- Streamlit UI ---
def main():
    initialize_session_state()

    st.set_page_config(page_title="AI Learning Framework", layout="centered")

    st.markdown("""
    <style>
    .main {
        background-color: #000000;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 8px;
        padding: 10px 20px;
        font-size: 16px;
        border: none;
        cursor: pointer;
        transition: background-color 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .chat-container {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        max-height: 500px;
        overflow-y: auto;
        background-color: white;
        margin-bottom: 20px;
    }
    .user-message {
        background-color: #e6f7ff;
        padding: 10px;
        border-radius: 10px;
        margin-bottom: 8px;
        text-align: right;
        margin-left: 20%;
    }
    .model-message {
        background-color: #f0f0f0;
        padding: 10px;
        border-radius: 10px;
        margin-bottom: 8px;
        text-align: left;
        margin-right: 20%;
    }
    .system-message {
        background-color: #fffacd;
        padding: 8px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-style: italic;
        text-align: center;
        font-size: 0.9em;
    }
    .error-message {
        background-color: #ffe6e6;
        padding: 8px;
        border-radius: 8px;
        margin-bottom: 8px;
        color: #cc0000;
        font-weight: bold;
        text-align: center;
        font-size: 0.9em;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("🧠 AI Learning Framework")
    st.markdown("---")

    if not st.session_state.session_started:
        st.subheader("Start Your Learning Journey!")
        with st.form("initial_setup"):
            concept = st.text_input("What concept do you want to learn today?", key="concept_input", placeholder="e.g., Quantum Computing, Machine Learning, Supply Chain Optimization")
            difficulty = st.selectbox("Select Difficulty Level:", ["Beginner", "Intermediate", "Advanced"], key="difficulty_input")
            role = st.text_input("What is your current role?", key="role_input", placeholder="e.g., Software Engineer, Data Analyst, Project Manager")
            submit_button = st.form_submit_button("Start Learning Session")

            if submit_button:
                if concept and role:
                    start_session_logic(concept, difficulty, role)
                    st.rerun() # Rerun to switch to chat interface
                else:
                    st.error("Please fill in both the concept and your role to start.")
    else:
        st.subheader(f"Learning: {st.session_state.concept} ({st.session_state.difficulty})")
        st.markdown(f"**Your Role:** {st.session_state.role}")
        st.markdown("---")

        # Display Chat History
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="user-message">You: {msg["content"]}</div>', unsafe_allow_html=True)
            elif msg["role"] == "model":
                st.markdown(f'<div class="model-message">AI: {msg["content"]}</div>', unsafe_allow_html=True)
            elif msg["role"] == "system":
                st.markdown(f'<div class="system-message">System: {msg["content"]}</div>', unsafe_allow_html=True)
            elif msg["role"] == "error":
                st.markdown(f'<div class="error-message">Error: {msg["content"]}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        if not st.session_state.session_ended:
            if st.session_state.current_question:
                st.markdown(f"**Current Concept Chunk:** _{st.session_state.current_concept_chunk}_")
                st.markdown(f"**Question:** {st.session_state.current_question}")

                # User Answer Input
                st.text_area("Your Answer:", key="user_answer_input", on_change=handle_user_answer, height=100)

                # Display feedback (if any)
                if st.session_state.feedback_message:
                    st.info(st.session_state.feedback_message)
            else:
                st.info("Generating your next question...")
        else:
            st.success("Session Completed!")
            st.subheader("Session Summary:")
            if st.session_state.learning_goal:
                st.markdown(f"**Learning Goal:** {st.session_state.learning_goal}")
            if st.session_state.org_benefit:
                st.markdown(f"**Organizational Benefit:** {st.session_state.org_benefit}")

            if st.button("Start New Session"):
                st.session_state.clear() # Clear all session state
                st.rerun()

if __name__ == "__main__":
    main()
