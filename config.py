import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///site.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Ansible paths
    ANSIBLE_INVENTORY_PATH = 'ansible/inventories'
    ANSIBLE_PLAYBOOK_PATH = 'ansible/playbooks'
    
    # Monitoring settings
    HOST_CHECK_INTERVAL = 60  # seconds
    SSH_TIMEOUT = 5  # seconds