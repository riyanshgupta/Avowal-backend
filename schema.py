from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime
from models import User
class UserCreate(BaseModel):
    username : str = Field(min_length=3, max_length=50)  
    email : EmailStr
    password: str = Field(min_length=6, max_length=255)

class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    profile_pic: str
    relationship_status: str

    class Config:
        from_attributes = True
        
class ConfessionCreate(BaseModel):
    content: str

class mentionedUser(BaseModel):
    id: int
    username: str
    profile_pic: str

    class Config:
        from_attributes = True
class ConfessionResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    mentions: List[mentionedUser]

    class Config:
        from_attributes = True
        from_attributes = True

class CommentResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    user: UserResponse

    class Config:
        from_attributes = True

class CommentCreate(BaseModel):
    content: str
    
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    
    
class MarkAsReadRequest(BaseModel):
    confession_ids: List[int]

class GoogleIDToken(BaseModel):
    id_token: str