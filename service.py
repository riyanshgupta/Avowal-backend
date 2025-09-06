import json
from fastapi import HTTPException
from fastapi.responses import JSONResponse
import jwt
from datetime import datetime, timedelta, timezone
import logging
import traceback

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy.ext.asyncio import AsyncSession

from config import GOOGLE_CLIENT_ID, ACCESS_TOKEN_EXPIRE_MINUTE, iiitbh_email_domain
from helpers import create_access_token, create_user, get_user_by_email, pwd_context
from schema import UserCreate
import secrets
from datetime import timedelta

def verify_google_token(token: str) -> dict:
    try:
        payload = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        return payload
    except ValueError as e:
        logging.error(f"Error verifying Google token: {e}")
        return None

async def create_jwt_for_google_user(google_payload: dict, session: AsyncSession) -> str:
    try:
        user_data = {
            "email": google_payload.get("email"),
        }
    
        user = await get_user_by_email(user_data["email"], session=session)
        
        if not user:
            # Create user in DB
            if not str(user_data["email"]).endswith(iiitbh_email_domain):
                raise HTTPException(status_code=403, detail=f"Email domain must be {iiitbh_email_domain}")

            hashed_password = pwd_context.hash(secrets.token_urlsafe(16))  # Generate a secure random password
            json_response: JSONResponse = await create_user(
                user=UserCreate(
                    email = user_data["email"],
                    password = hashed_password,
                    username = user_data["email"].split("@")[0]
            ), session=session, name=google_payload.get("name"), profile_pic=google_payload.get("picture"), from_google=True)

            user_id = json.loads(json_response.body.decode('utf-8')).get('user_id')
            user_data["id"] = user_id
        else:
            user_data["id"] = user.id

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTE)
        access_token = create_access_token(data=user_data, expire_delta=access_token_expires)
        return {"access_token": access_token, "token_type": "bearer"}
    
    # This should not catch HTTPException, but any other exception
    except Exception as e:
        logging.error(f"Error creating JWT for Google user: {traceback.format_exc()}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail="Internal Server Error")