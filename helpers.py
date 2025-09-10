import asyncio
from bisect import bisect_left
import logging
import traceback
from fastapi.security import OAuth2PasswordBearer
from pydantic import EmailStr
from database import get_db_session, get_session
from models import Comment, Confession, ConfessionMentionLink, User
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Union
from fastapi import HTTPException, status, Depends
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTE, PASSWORD
from schema import UserCreate
from data import emails_list, name_list

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# -------------Functions for authentication---------------------------------------------------------------------------------------------------
async def get_user_by_username(username: str, session: AsyncSession):
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(email: str, session: AsyncSession) -> Union[User, None]:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(user: UserCreate, session: AsyncSession, name: str = "", profile_pic: str="", from_google: bool = False) -> JSONResponse:
    hashedpassword = pwd_context.hash(user.password)
    try:
        global emails_list, name_list
        if not from_google:
            user_model = await get_user_by_username(user.username, session)
            if user_model is not None:
                return JSONResponse(
                    status_code=400, content={"message": f"Username already exists"}
                )

            user_model = await get_user_by_email(user.email, session)
            if user_model is not None:
                return JSONResponse(
                    status_code=400, content={"message": f"Email already exists"}
                )
            index = bisect_left(list(emails_list), user.email)

        user_model = User(
            username=user.username,
            email=user.email,
            hashedpassword=hashedpassword,
            name=name_list[index] if not from_google else name,
            profile_pic=profile_pic if from_google else "images/profile/def.jpg", # the default profile pic
        )
        session.add(user_model)
        await session.commit()
        return JSONResponse(
            status_code=200,
            content={
                "message": f"User created successfully with username: {user.username}",
                "user_id": user_model.id,
            },
        )
    except Exception as e:
        await session.rollback()

        logging.error(f"Error occurred in create_user: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Something went wrong")


async def authenticate_user(email: EmailStr, password: str, session: AsyncSession) -> Union[User, None]:
    user: User | None = await get_user_by_email(str(email), session)
    if not user:
        logging.warning(f"Authentication failed for email: {email}")
        return None
    verified_user = pwd_context.verify(password, str(user.hashedpassword))
    if verified_user:
        return user
    return None


def create_access_token(data: dict, expire_delta: timedelta | None = None):
    to_encode = data.copy()
    if expire_delta:
        expire = datetime.now(timezone.utc) + expire_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=24 * 30
        )  # default 30 days
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(payload=to_encode, key=SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def verify_token(token: str, session: AsyncSession):
    try:
        payload = jwt.decode(jwt=token, key=SECRET_KEY, algorithms=["HS256"])
        id: int = payload.get("id")
        result = await session.execute(select(User).where(User.id == id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=403, detail=f"User not found")
        return payload
    except Exception as e:
        logging.error(f"Exception occurred in verify_token: {traceback.format_exc()}")
        raise HTTPException(status_code=401, detail=f"Token is invalid or expired")


async def get_current_user(
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(jwt=token, key=SECRET_KEY, algorithms=["HS256"])
        id: int = payload.get("id")
        user = {
            "id": id,
            "email": payload.get("email"),
        }  # user_id only
        return user
    except (jwt.PyJWTError, ValueError) as e:
        if e == ValueError:
            logging.error(f"ValueError occurred in get_current_user: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def change_username_in_confessions(old_username: str, user: User, session: AsyncSession):
    try:
        stmt = (
            select(Confession)
            .join(ConfessionMentionLink, ConfessionMentionLink.confession_id == Confession.id)
            .where(ConfessionMentionLink.user_id == user.id)
            .order_by(Confession.created_at.desc())
        )
        result = await session.execute(stmt)
        confessions: list[Confession] = result.scalars().all()
        update_required = False
        for confession in confessions:
            if '@'+old_username in confession.content:
                confession.content = confession.content.replace('@' + old_username, '@' + user.username)
                update_required = True
        # # Lets do the bulk update now
        if update_required:
            await session.commit()
        
    except Exception as e:
        await session.rollback()
        logging.error(f"Error occurred while changing username in confessions: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to update username in confessions")

async def delete_confession_and_related(
    confession_id: int,
    session: AsyncSession,
) -> bool:
    """
    Deletes a confession and all related data:
    - All comments associated with the confession.
    - All mention links (ConfessionMentionLink) for the confession.
    - The confession itself.
    
    Returns True if successful, False otherwise.
    """
    try:
        # Step 1: Fetch the confession to ensure it exists
        stmt = select(Confession).where(Confession.id == confession_id)
        result = await session.execute(stmt)
        confession = result.scalar_one_or_none()
        
        if not confession:
            return False  # Confession not found
        
        
        # Step 2: Delete all comments related to the confession
        async def delete_comments():
            async with get_db_session() as session2:
                delete_comments_stmt = delete(Comment).where(Comment.confession_id == confession_id)
                await session2.execute(delete_comments_stmt)
                await session2.commit()

        # Step 3: Delete all mention links for the confession
        async def delete_links():
            async with get_db_session() as session1:
                delete_links_stmt = delete(ConfessionMentionLink).where(ConfessionMentionLink.confession_id == confession_id)
                await session1.execute(delete_links_stmt)
                await session1.commit()

        # Concurrent deletions       
        tasks = [
            asyncio.create_task(delete_comments()),
            asyncio.create_task(delete_links())
        ]
        await asyncio.gather(*tasks)

        # Step 4: Delete the confession itself
        await session.delete(confession)
        
        # Commit all changes
        await session.commit()
        
        return True
    
    except Exception as e:
        await session.rollback()
        logging.error(f"Error deleting confession {confession_id}: {e} {traceback.format_exc()}")
        return False
