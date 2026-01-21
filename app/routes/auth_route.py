import json
import os
import io
import datetime
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.routes.utils_route import get_oci_client

auth_bp = Blueprint('auth', __name__)

# Constants
METADATA_BUCKET = os.getenv('METADATA_BUCKET_NAME', 'host-service-metadata')
USERS_FILE = 'users.json'

def get_metadata_bucket_namespace():
    """Helper to get the namespace (required for Object Storage calls)."""
    client = get_oci_client('object_storage')
    return client.get_namespace().data

def load_users_db():
    """
    Fetches and parses users.json from OCI Object Storage.
    Returns an empty dict if the file doesn't exist yet.
    """
    client = get_oci_client('object_storage')
    namespace = get_metadata_bucket_namespace()
    
    try:
        # Attempt to get the object
        response = client.get_object(namespace, METADATA_BUCKET, USERS_FILE)
        file_content = response.data.content.decode('utf-8')
        return json.loads(file_content)
    except Exception as e:
        # If file not found (404), return empty DB. Real production code should check status code.
        print(f"DEBUG: users.json not found or error: {e}")
        return {}

def save_users_db(users_data):
    """
    Uploads the updated users dictionary back to OCI as users.json.
    """
    client = get_oci_client('object_storage')
    namespace = get_metadata_bucket_namespace()
    
    json_bytes = json.dumps(users_data, indent=2).encode('utf-8')
    
    client.put_object(
        namespace,
        METADATA_BUCKET,
        USERS_FILE,
        json_bytes,
        content_type='application/json'
    )

# --- Routes ---

@auth_bp.route('/check', methods=['GET'])
def check_auth():
    """Checks if a valid session cookie exists[cite: 43]."""
    if 'user_id' in session:
        return jsonify({"authenticated": True, "user": session.get('user_id')}), 200
    return jsonify({"authenticated": False}), 401

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Handle user registration.
    Hashes password and saves to Metadata Bucket[cite: 35, 47].
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    #Load existing users
    users_db = load_users_db()

    #Check if user exists
    if username in users_db:
        return jsonify({"error": "User already exists"}), 409

    #Hash password 
    hashed_pw = generate_password_hash(password)

    #Create user record [cite: 35]
    users_db[username] = {
        "email": email,
        "password_hash": hashed_pw,
        "created_at": datetime.datetime.utcnow().isoformat()
    }

    #Save back to OCI
    try:
        save_users_db(users_db)
        return jsonify({"message": "User created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Handle user login.
    Verifies hash and sets session[cite: 56, 57].
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')

    #Load users
    users_db = load_users_db()

    #Validate User
    user_record = users_db.get(username)
    
    if not user_record:
        return jsonify({"error": "Invalid credentials"}), 401

    #Verify Hash [cite: 56]
    if check_password_hash(user_record['password_hash'], password):
        session['user_id'] = username
        return jsonify({"message": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({"message": "Logged out"}), 200