import os
import json
from flask import Blueprint, jsonify
from app.routes.utils_route import get_oci_client
health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

@health_bp.route('/health/oci', methods=['GET'])
def check_oci_connection():
    """
    Tests the connection to Oracle Cloud by fetching the Object Storage Namespace.
    """
    try:
        # 1. Initialize Client
        object_storage = get_oci_client('object_storage')
        
        # 2. Perform a lightweight API call
        namespace = object_storage.get_namespace().data
        
        # 3. Success Response
        return jsonify({
            "status": "connected",
            "provider": "Oracle Cloud Infrastructure",
            "namespace": namespace,
            "message": "OCI API credentials are valid."
        }), 200

    except Exception as e:
        # 4. Failure Response
        return jsonify({
            "status": "failed",
            "error": str(e),
            "tip": "Check your .env file, API Key path, or IAM Policies."
        }), 500
# @health_bp.route('/health/metadata-debug', methods=['GET'])
# def debug_metadata():
#     """
#     DEBUG ONLY: Checks if Metadata Bucket exists and reads its JSON content.
#     [cite_start][cite: 93, 95] - Inspects the private metadata storage.
#     """
#     bucket_name = os.getenv('METADATA_BUCKET_NAME', 'host-service-metadata')
    
#     try:
#         # 1. Init Client
#         object_storage = get_oci_client('object_storage')
#         namespace = object_storage.get_namespace().data
        
#         # 2. Check Bucket Existence (List Objects)
#         # This confirms the bucket exists and we can access it
#         list_response = object_storage.list_objects(namespace, bucket_name)
#         objects = list_response.data.objects
        
#         files_found = [obj.name for obj in objects]
        
#         debug_data = {
#             "status": "Bucket Found",
#             "bucket_name": bucket_name,
#             "files_in_bucket": files_found,
#             "contents": {}
#         }

#         # 3. Read critical files if they exist
#         for filename in ['users.json', 'buckets.json']:
#             if filename in files_found:
#                 try:
#                     obj = object_storage.get_object(namespace, bucket_name, filename)
#                     content = obj.data.content.decode('utf-8')
#                     debug_data["contents"][filename] = json.loads(content)
#                 except Exception as e:
#                     debug_data["contents"][filename] = f"Error reading file: {str(e)}"
#             else:
#                 debug_data["contents"][filename] = "File not found (Not created yet)"

#         return jsonify(debug_data), 200

#     except Exception as e:
#         # If the bucket itself is missing or we have no permission
#         return jsonify({
#             "status": "Error",
#             "message": f"Could not access Metadata Bucket '{bucket_name}'",
#             "error_details": str(e)
#         }), 500