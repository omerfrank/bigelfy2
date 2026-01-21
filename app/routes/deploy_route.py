import os
import io
import zipfile
import uuid
import datetime
import mimetypes
import json
from flask import Blueprint, request, jsonify, session
from werkzeug.utils import secure_filename
from app.routes.auth_route import get_oci_client
from app.decorators.login_req import login_required
import oci
import traceback

deploy_bp = Blueprint('deploy', __name__)

# --- Configuration ---
METADATA_BUCKET = os.getenv('METADATA_BUCKET_NAME', 'host-service-metadata')
DEPLOYMENTS_FILE = 'buckets.json'
MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024  # 100MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_FILES_IN_ZIP = 1000
MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50MB for in-memory processing
MAX_SITES_PER_USER = int(os.getenv('MAX_SITES_PER_USER', '5'))

# --- Helpers ---

def get_metadata_namespace():
    client = get_oci_client('object_storage')
    return client.get_namespace().data

def load_deployments_db():
    """Fetches buckets.json from OCI. Creates it if it doesn't exist."""
    client = get_oci_client('object_storage')
    namespace = get_metadata_namespace()
    try:
        response = client.get_object(namespace, METADATA_BUCKET, DEPLOYMENTS_FILE)
        return json.loads(response.data.content.decode('utf-8'))
    except oci.exceptions.ServiceError as e:
        # If file doesn't exist (404), create it with empty list
        if e.status == 404:
            print(f"DEBUG: {DEPLOYMENTS_FILE} not found, creating it")
            empty_list = []
            save_deployments_db(empty_list)
            return empty_list
        # Re-raise other service errors
        raise
    except Exception as e:
        print(f"ERROR loading deployments DB: {e}")
        # Try to create the file if it doesn't exist
        try:
            empty_list = []
            save_deployments_db(empty_list)
            return empty_list
        except:
            return []  # Last resort fallback

def save_deployments_db(deployments_data):
    """Saves updated list to buckets.json."""
    client = get_oci_client('object_storage')
    namespace = get_metadata_namespace()
    json_bytes = json.dumps(deployments_data, indent=2).encode('utf-8')
    
    client.put_object(
        namespace, METADATA_BUCKET, DEPLOYMENTS_FILE, json_bytes,
        content_type='application/json'
    )

def validate_zip_safety(zip_file):
    """
    Prevents Zip Bombs and validates file counts/sizes.
    """
    total_size = 0
    file_count = 0
    
    for zinfo in zip_file.infolist():
        if zinfo.is_dir():
            continue
        
        file_count += 1
        total_size += zinfo.file_size
        
        # Individual file size limit
        if zinfo.file_size > MAX_FILE_SIZE:
            raise ValueError(f"File {zinfo.filename} exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit")
    
    if file_count > MAX_FILES_IN_ZIP:
        raise ValueError(f"ZIP contains {file_count} files (max {MAX_FILES_IN_ZIP})")
    
    if total_size > MAX_UNCOMPRESSED_SIZE:
        raise ValueError(f"Uncompressed size exceeds {MAX_UNCOMPRESSED_SIZE // (1024*1024)}MB limit")

def validate_filename(filename):
    """
    Prevents path traversal attacks and validates filenames.
    """
    # Check for path traversal
    if filename.startswith('/') or '..' in filename or '\\' in filename:
        raise ValueError(f"Invalid file path in ZIP: {filename}")
    
    # Additional security checks
    if filename.startswith('~') or filename.startswith('.'):
        raise ValueError(f"Hidden or system files not allowed: {filename}")
    
    return True

def sanitize_bucket_name(base_name):
    """
    Ensures bucket name meets OCI requirements:
    - 1-256 characters
    - Lowercase alphanumeric and hyphens only
    - Cannot start/end with hyphen
    """
    # Convert to lowercase and keep only alphanumeric and hyphens
    sanitized = ''.join(c if c.isalnum() or c == '-' else '-' for c in base_name.lower())
    
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    
    # Ensure it's not empty and within length limits
    if not sanitized or len(sanitized) > 256:
        raise ValueError("Invalid bucket name after sanitization")
    
    return sanitized

def empty_bucket(client, namespace, bucket_name):
    """
    Recursively delete all objects in bucket with pagination.
    """
    while True:
        try:
            response = client.list_objects(
                namespace, 
                bucket_name,
                limit=1000
            )
            objects = response.data.objects
            
            if not objects:
                break
            
            for obj in objects:
                try:
                    client.delete_object(namespace, bucket_name, obj.name)
                except Exception as e:
                    print(f"Warning: Failed to delete object {obj.name}: {e}")
                    
        except Exception as e:
            print(f"Error listing objects in bucket {bucket_name}: {e}")
            break

def cleanup_bucket(namespace, bucket_name):
    """
    Cleanup helper to delete bucket and all its contents.
    Used for rollback on deployment failure.
    """
    try:
        client = get_oci_client('object_storage')
        empty_bucket(client, namespace, bucket_name)
        client.delete_bucket(namespace, bucket_name)
    except Exception as e:
        print(f"Cleanup error for bucket {bucket_name}: {e}")



@deploy_bp.route('', methods=['POST'])
@login_required
def deploy_site():
    print("--- [DEBUG] Starting Deployment Process ---")
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        # 1. Load User's Deployment History
        print("[DEBUG] Loading deployment DB...")
        all_deployments = load_deployments_db()
        user_sites = [d for d in all_deployments if d.get('owner_id') == session['user_id']]
        
        if len(user_sites) >= MAX_SITES_PER_USER:
            return jsonify({"error": f"Maximum of {MAX_SITES_PER_USER} sites allowed per user"}), 403

        # 2. Check File Size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        print(f"[DEBUG] File Size: {file_size} bytes")
        
        if file_size > MAX_ZIP_SIZE:
            return jsonify({"error": f"ZIP file too large (max {MAX_ZIP_SIZE // (1024*1024)}MB)"}), 400

        # 3. Read & Validate ZIP
        print("[DEBUG] Reading ZIP file...")
        file_stream = io.BytesIO(file.read())
        
        if not zipfile.is_zipfile(file_stream):
            return jsonify({"error": "File is not a valid ZIP"}), 400

        # 4. Prepare OCI Clients
        print("[DEBUG] Initializing OCI Clients...")
        object_storage = get_oci_client('object_storage')
        if not object_storage:
             raise ValueError("Failed to initialize OCI Object Storage Client")

        namespace = get_metadata_namespace()
        compartment_id = os.getenv('OCI_COMPARTMENT_ID')
        
        if not compartment_id:
            return jsonify({"error": "Server configuration error: OCI_COMPARTMENT_ID not set"}), 500

        # 5. Generate Bucket Name
        site_uid = str(uuid.uuid4())[:8]
        base_bucket_name = f"site-{session['user_id']}-{site_uid}"
        new_bucket_name = sanitize_bucket_name(base_bucket_name)
        print(f"[DEBUG] Target Bucket Name: {new_bucket_name}")

        bucket_created = False
        
        # 6. Process ZIP & Upload
        with zipfile.ZipFile(file_stream) as zf:
            print("[DEBUG] Validating ZIP safety...")
            validate_zip_safety(zf)

            # Create Bucket
            create_details = oci.object_storage.models.CreateBucketDetails(
                name=new_bucket_name,
                compartment_id=compartment_id,
                public_access_type='ObjectRead'
            )
            
            object_storage.create_bucket(namespace, create_details)
            bucket_created = True
            print("[DEBUG] Bucket created successfully.")
            has_index = False

            # Upload Files
            print("[DEBUG] Starting file upload...")
            for file_info in zf.infolist():
                if file_info.is_dir():
                    continue
                
                filename = file_info.filename
                validate_filename(filename) # Security check
                
                if filename.lower() == 'index.html':
                    has_index = True
                
                content = zf.read(filename)
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = 'application/octet-stream'

                print(f"   -> Uploading: {filename} ({content_type})")
                object_storage.put_object(
                    namespace,
                    new_bucket_name,
                    filename,
                    content,
                    content_type=content_type
                )

            # 7. Update Metadata
            print("[DEBUG] Upload complete. Updating metadata...")
            if has_index:
                site_url = f"https://objectstorage.{os.getenv('OCI_REGION')}.oraclecloud.com/n/{namespace}/b/{new_bucket_name}/o/index.html"
            else:
                site_url = f"https://objectstorage.{os.getenv('OCI_REGION')}.oraclecloud.com/n/{namespace}/b/{new_bucket_name}/o/"

            new_record = {
                "bucket_key": new_bucket_name,
                "owner_id": session['user_id'],
                "launch_time": datetime.datetime.utcnow().isoformat(),
                "status": "Active",
                "url": site_url,
                "has_index": has_index
            }
            all_deployments.append(new_record)
            save_deployments_db(all_deployments)
            
            print("[DEBUG] Metadata updated. Deployment Success!")
            return jsonify({
                "message": "Deployment successful",
                "site_url": site_url,
                "bucket_name": new_bucket_name,
                "has_index": has_index
            }), 201

    except ValueError as e:
        print(f"❌ VALIDATION ERROR: {e}")
        if bucket_created: cleanup_bucket(namespace, new_bucket_name)
        return jsonify({"error": str(e)}), 400
    
    except oci.exceptions.ServiceError as e:
        print(f"❌ OCI SERVICE ERROR: {e}")
        if bucket_created: cleanup_bucket(namespace, new_bucket_name)
        if e.status == 403:
            return jsonify({"error": "Permission denied (Check OCI Policies)"}), 403
        return jsonify({"error": f"OCI Error: {e.message}"}), 500
    
    except Exception as e:
        print("❌ CRITICAL UNEXPECTED ERROR:")
        traceback.print_exc()  # This prints the full error stack to your terminal
        
        if 'bucket_created' in locals() and bucket_created:
            print("[DEBUG] Cleaning up bucket due to failure...")
            cleanup_bucket(namespace, new_bucket_name)
            
        return jsonify({"error": "Deployment failed due to internal server error"}), 500

@deploy_bp.route('', methods=['GET'])
@login_required
def list_deployments():
    """Returns list of sites owned by the current user."""
    all_deployments = load_deployments_db()
    # Filter by logged-in user
    user_sites = [d for d in all_deployments if d.get('owner_id') == session['user_id']]
    return jsonify({"sites": user_sites}), 200

@deploy_bp.route('/<bucket_name>', methods=['DELETE'])
@login_required
def delete_site(bucket_name):
    """
    Deletes the site bucket and removes from metadata.
    """
    object_storage = get_oci_client('object_storage')
    namespace = get_metadata_namespace()
    
    # Verify Ownership
    all_deployments = load_deployments_db()
    site_record = next((d for d in all_deployments if d['bucket_key'] == bucket_name), None)
    
    if not site_record or site_record['owner_id'] != session['user_id']:
        return jsonify({"error": "Site not found or unauthorized"}), 404

    try:
        # Empty the bucket first (with pagination)
        empty_bucket(object_storage, namespace, bucket_name)
        
        # Delete the bucket
        object_storage.delete_bucket(namespace, bucket_name)

        # Update Metadata
        all_deployments = [d for d in all_deployments if d['bucket_key'] != bucket_name]
        save_deployments_db(all_deployments)

        return jsonify({"message": "Site deleted successfully"}), 200

    except Exception as e:
        print(f"Delete error: {e}")
        return jsonify({"error": "Failed to delete site. Please try again."}), 500