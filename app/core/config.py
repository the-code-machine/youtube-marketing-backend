import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    # Add inside Settings class
    # EMAIL SETTINGS
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") # App Password, NOT login password
    
    
    # ZEPTO MAIL SETTINGS
    ZEPTO_API_URL = os.getenv("ZEPTO_API_URL", "https://api.zeptomail.in/v1.1/email")
    ZEPTO_API_KEY = os.getenv("ZEPTO_API_KEY")
    ZEPTO_FROM_ADDRESS = os.getenv("ZEPTO_FROM_ADDRESS")
    ZEPTO_TO_ADDRESS = os.getenv("ZEPTO_TO_ADDRESS")        
    
    # LIMITS
    DAILY_EMAIL_LIMIT = 100
    DAILY_IG_LIMIT = 200

settings = Settings()
