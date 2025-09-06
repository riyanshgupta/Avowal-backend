import os
from dotenv import load_dotenv
load_dotenv()
# SECRETS that has not to be shared on the github and has to be stored in .env file only
DATABASE_URL = os.getenv(key="DATABASE_URI")
SECRET_KEY = os.getenv(key="SECRET_KEY")
ALGORITHM = os.getenv(key="ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTE = int(os.getenv(key="ACCESS_TOKEN_EXPIRE_MINUTE"))
MAIL = os.getenv(key="MAIL")
MAIL_PASSWORD = os.getenv(key="MAIL_PASSWORD")
SALT = os.getenv(key="PASSWORD_RESET_SALT")
CLOUD_NAME = os.getenv(key="CLOUD_NAME")
API_KEY_CLOUD = os.getenv(key="API_KEY_CLOUD")
API_SECRET = os.getenv(key="API_SECRET")
PASSWORD = os.getenv(key="PASSWORD")
API_KEY_GEMINI=os.getenv(key="API_KEY_GEMINI")
API_KEY_OPEN_ROUTER=os.getenv(key="API_KEY_OPEN_ROUTER")
SYSTEM_PROMPT_FOR_APPROVAL = os.getenv(key="SYSTEM_PROMPT_FOR_APPROVAL")
GOOGLE_CLIENT_ID=os.getenv(key="GOOGLE_CLIENT_ID")

iiitbh_email_domain = "iiitbh.ac.in"