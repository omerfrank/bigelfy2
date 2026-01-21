from functools import wraps
from flask import session, jsonify

def login_required(f):
    """
    Decorator to ensure that a user is logged in before accessing a route.
    Checks if 'user_id' exists in the Flask session.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # User is not logged in, return 401 Unauthorized
            return jsonify({"error": "Unauthorized. Please login first."}), 401
        
        # User is logged in, proceed to the actual route function
        return f(*args, **kwargs)
    
    return decorated_function