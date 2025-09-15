import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import numpy as np
import pickle
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Generate or get secret key
def get_secret_key():
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        secret_key = secrets.token_hex(24)
        print("Warning: Using auto-generated secret key. For production, set SECRET_KEY environment variable.")
    return secret_key

app.secret_key = get_secret_key()

# Load your ML model
try:
    with open("model.pkl", "rb") as f:
        model = pickle.load(f)
except FileNotFoundError:
    model = None
    print("Warning: model.pkl not found. Prediction functionality will be disabled.")

# Initialize OpenAI client - FIXED: Get API key from environment variable
api_key = os.environ.get("OPENAI_API_KEY")
if api_key:
    client = OpenAI(api_key=api_key)
    print("OpenAI client initialized successfully")
else:
    client = None
    print("Warning: OPENAI_API_KEY not found. Chatbot functionality will be disabled.")

# ================== DB HELPERS ==================
def get_db():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

# ================== DATABASE SETUP ==================
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

def create_admin():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE username = ? OR email = ?", ('admin', 'admin@example.com'))
    if not cur.fetchone():
        password = generate_password_hash("admin123")
        cur.execute(
            "INSERT INTO users (email, username, password, is_admin) VALUES (?, ?, ?, 1)",
            ("admin@example.com", "admin", password)
        )
        conn.commit()
    conn.close()

# ================== CHATBOT HELPER ==================
def ask_gpt(message):
    try:
        # Check if API key and client are available
        if not client:
            return "Chatbot service is currently unavailable. Please try again later."
            
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful and knowledgeable sleep expert. Provide detailed, practical advice about sleep health, sleep disorders, and sleep improvement techniques. Be empathetic and professional."},
                {"role": "user", "content": message}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        # Return more specific error messages
        error_msg = str(e).lower()
        if "authentication" in error_msg or "api key" in error_msg or "invalid" in error_msg:
            return "Authentication error with AI service. Please contact administrator."
        elif "quota" in error_msg or "limit" in error_msg:
            return "AI service quota exceeded. Please try again later."
        elif "network" in error_msg or "connection" in error_msg:
            return "Network connection issue. Please check your internet connection and try again."
        else:
            return "I'm having trouble connecting to the AI service right now. Please try again later."

def save_chat_history(user_id, message, response):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_history (user_id, message, response) VALUES (?, ?, ?)",
        (user_id, message, response)
    )
    conn.commit()
    conn.close()

def get_chat_history(user_id, limit=10):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT message, response, timestamp FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit)
    )
    history = cur.fetchall()
    conn.close()
    return history

# ================== ROUTES ==================
@app.route('/predict')
def predict():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('predict.html')

@app.route('/result', methods=['POST'])
def result():
    if 'username' not in session:
        return redirect(url_for('login'))

    age = int(request.form['age'])
    sleep_duration = float(request.form['sleep_duration'])
    stress_level = int(request.form['stress_level'])
    physical_activity = float(request.form['physical_activity'])

    if model:
        features = np.array([[age, sleep_duration, stress_level, physical_activity]])
        prediction = model.predict(features)[0]
    else:
        prediction = "Model not available"
        
    return render_template('result.html', prediction=prediction)

# ================== LOGIN ROUTE (ROOT) ==================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['is_admin'] = user['is_admin']
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')

@app.route('/home')
def home():
    if 'username' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    return render_template('home.html', username=session['username'])

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        username = request.form['username'].strip()
        password_hash = generate_password_hash(request.form['password'])

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, username, password) VALUES (?, ?, ?)",
                        (email, username, password_hash))
            conn.commit()
            conn.close()
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email or Username already exists", "danger")
    return render_template('signup.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template('forgot_password.html')

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cur.fetchone()

        if user:
            hashed_password = generate_password_hash(new_password)
            cur.execute("UPDATE users SET password = ? WHERE email = ?", (hashed_password, email))
            conn.commit()
            conn.close()
            flash("Password updated successfully. Please log in.", "success")
            return redirect(url_for('login'))
        else:
            conn.close()
            flash("Email not found", "danger")

    return render_template('forgot_password.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'], is_admin=session.get('is_admin', 0))

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", 'success')
    return redirect(url_for('login'))

# ================== GPT CHATBOT ==================
@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    chat_history = get_chat_history(user_id)
    
    if request.method == 'POST':
        user_message = request.form.get('message', '')
        
        if user_message:
            try:
                bot_response = ask_gpt(user_message)
                save_chat_history(user_id, user_message, bot_response)
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'user_message': user_message,
                        'bot_response': bot_response
                    })
                
                # For non-AJAX requests
                chat_history = get_chat_history(user_id)
                return render_template('chatbot.html', 
                                    user_message=user_message, 
                                    bot_response=bot_response,
                                    chat_history=chat_history)
            except Exception as e:
                error_msg = f"Error processing your request: {str(e)}"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'user_message': user_message,
                        'bot_response': error_msg
                    })
                return render_template('chatbot.html', 
                                    user_message=user_message, 
                                    bot_response=error_msg,
                                    chat_history=chat_history)
    
    return render_template('chatbot.html', chat_history=chat_history)

# ================== INIT & RUN ==================
def show_all_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, is_admin FROM users")
    rows = cur.fetchall()
    print("\n=== Registered Users ===")
    for row in rows:
        print(f"ID: {row['id']}, Username: {row['username']}, Admin: {bool(row['is_admin'])}")
    conn.close()

init_db()
create_admin()
show_all_users()

if __name__ == '__main__':
    app.run(debug=True)