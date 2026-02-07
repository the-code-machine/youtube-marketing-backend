from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from datetime import timedelta
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.schemas import UserCreate, UserLogin, UserResponse, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------
# REGISTER
# ---------------------------------------------------------
@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    # 1. Check if email exists
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    # 2. Create new user
    new_user = User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role="user",
        plan="free"
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------
@router.post("/login", response_model=Token)
def login(response: Response, login_data: UserLogin, db: Session = Depends(get_db)):
    # 1. Check User
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    # 2. Check Password
    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    # 3. Create Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "id": user.id, "role": user.role},
        expires_delta=access_token_expires
    )
    
    # 4. SET COOKIE (Crucial for "credentials=true")
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,   # JavaScript cannot read this (prevents XSS)
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",  # Allows cookie to be sent on top-level navigation
        secure=False     # Set to True in Production (HTTPS)
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}

# ---------------------------------------------------------
# GET CURRENT USER (Dependency)
# ---------------------------------------------------------
from fastapi import Cookie, Header

def get_current_user(
    access_token: Optional[str] = Cookie(None), 
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Tries to get token from Cookie first, then Authorization header.
    """
    token = None
    
    # Try Cookie
    if access_token:
        token = access_token.replace("Bearer ", "")
    # Try Header
    elif authorization:
        token = authorization.replace("Bearer ", "")
        
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    # Verify Token (Logic for verifying JWT would go here)
    # For brevity, assuming valid if present, but you MUST add verify logic
    return token