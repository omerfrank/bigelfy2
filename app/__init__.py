import os
from flask import Flask, render_template
from flask_cors import CORS
from dotenv import load_dotenv

def create_app():
    # Load environment variables
    load_dotenv()

    app = Flask(__name__)

    # --- Configuration & Security ---
    app.secret_key = os.getenv('SECRET_KEY')  # Required for sessions

    
    # Enable CORS for cross-origin requests (Frontend Bucket <-> Backend VM)
    CORS(app, supports_credentials=True)

    # [cite_start]Limit max upload size (50MB) to prevent large ZIP attacks [cite: 102, 104]
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 

    # --- Register Blueprints ---
    from app.routes.auth_route import auth_bp
    from app.routes.deploy_route import deploy_bp
    from app.routes.health_route import health_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(deploy_bp, url_prefix='/api/deploy')
    app.register_blueprint(health_bp)
    @app.route('/')
    def index():
        """Serves the main frontend HTML page."""
        return render_template('index.html')
    return app
