import os
import oci

def get_oci_client(service_type):
    """
    Factory function to create OCI clients (Identity, ObjectStorage, etc.).
    """
    auth_method = os.getenv('OCI_AUTH_METHOD', 'instance_principal')

    if auth_method == 'config_file':
        # Local Development: Use keys defined in .env
        config_path = os.getenv('OCI_CONFIG_PATH', oci.config.DEFAULT_LOCATION)
        config_profile = os.getenv('OCI_CONFIG_PROFILE', 'DEFAULT')
        
        try:
            config = oci.config.from_file(file_location=config_path, profile_name=config_profile)
            if service_type == 'identity':
                return oci.identity.IdentityClient(config)
            elif service_type == 'object_storage':
                return oci.object_storage.ObjectStorageClient(config)
        except Exception as e:
            print(f"Error loading OCI config: {e}")
            return None

    else:
        # [cite_start]Production: Use Instance Principals (Dynamic Groups) [cite: 83, 87]
        try:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            if service_type == 'identity':
                return oci.identity.IdentityClient(config={}, signer=signer)
            elif service_type == 'object_storage':
                return oci.object_storage.ObjectStorageClient(config={}, signer=signer)
        except Exception as e:
            print(f"Error initializing Instance Principals: {e}")
            return None
            
    return None