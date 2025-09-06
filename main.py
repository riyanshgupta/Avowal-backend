

from collections import defaultdict
import logging, asyncio, traceback

from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Set, Union
from os import getenv, path
from re import findall, fullmatch

from fastapi import FastAPI, Depends, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi_mail import ConnectionConfig
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from sqlmodel import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import cloudinary.uploader
import cloudinary

from database import get_session, init_db
from models import Confession, User, Comment
from schema import (
    ConfessionCreate,
    ConfessionResponse,
    GoogleIDToken,
    UserCreate,
    CommentCreate,
    CommentResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MarkAsReadRequest,
)
from data import emails_list
from service import create_jwt_for_google_user, verify_google_token
from utils import LLM_analyzer
from config import (
    MAIL,
    API_KEY_OPEN_ROUTER,
    MAIL_PASSWORD,
    API_KEY_CLOUD,
    API_SECRET,
    CLOUD_NAME,
    SECRET_KEY,
    SYSTEM_PROMPT_FOR_APPROVAL,
    API_KEY_GEMINI,
    SALT,
    ACCESS_TOKEN_EXPIRE_MINUTE,
)
from helpers import (
    authenticate_user,
    create_access_token,
    delete_confession_and_related,
    get_user_by_username,
    get_user_by_email,
    verify_token,
    get_current_user,
)
# -----------------------------------------Do Not Change here----------------------------------------------------------------------

app = FastAPI()

# @app.on_event("startup")
async def on_startup():
    await asyncio.gather(init_db())


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conf = ConnectionConfig(
    MAIL_USERNAME=MAIL,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL,
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,  # Use either MAIL_SSL_TLS or MAIL_STARTTLS, not both
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)
cloudinary.config(
    cloud_name=CLOUD_NAME, api_key=API_KEY_CLOUD, api_secret=API_SECRET, secure=True
)

# Serializer for token generation
serializer = URLSafeTimedSerializer(SECRET_KEY)

images_path = Path("images")
app.mount("/images", StaticFiles(directory=images_path), name="images")

analyzer = LLM_analyzer(SYSTEM_PROMPT_FOR_APPROVAL, API_KEY_GEMINI, API_KEY_OPEN_ROUTER)
comment_event_queue = asyncio.Queue()



# ------------------------------------------------------------------------------------------------------------------------
@app.get("/")
async def root():
    return JSONResponse(
        status_code=200,
        content={
            "message": "API is live",
            "documentation": "https://avowal-backend.vercel.app/docs",
        })

# ----------------------------------------------Oauth2.0 and JWT based authentication system---------------------------------
@app.post("/auth/google")
async def auth_google(google_id_token: GoogleIDToken, session: AsyncSession = Depends(get_session)):
    google_payload = verify_google_token(google_id_token.id_token)
    if not google_payload:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    
    response = await create_jwt_for_google_user(google_payload, session)

    return response

# ----------------------------------------------Auth Routes---------------------------------
# @app.post("/signup")
# async def register_user(
#     user: UserCreate, session: AsyncSession = Depends(get_session)
# ):

#     user_model = await get_user_by_username(user.username, session)
#     if user_model is not None:
#         return JSONResponse(
#             status_code=400, content={"message": "Username already taken"}
#         )
#     user_model = await get_user_by_email(user.email, session)
#     if user_model:
#         return JSONResponse(status_code=400, content={"message": f"Email already exists"})
#     if user.email not in emails_list:
#         return JSONResponse(
#             status_code=400,
#             content={
#                 "message": f"This email doesn't exists in our database please enter your college mail"
#             },
#         )
#     return await create_user(user, session)
    
# ------------------Login Route-----------------------

@app.post("/login")
async def login_for_accesstoken(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate_user(
        email=form_data.username, password=form_data.password, session=session  # email is considered username here
    )
    if user is None:
        raise HTTPException(status_code=401, detail=f"Incorrect password or email")
    access_token_expire = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTE)
    access_token = create_access_token(
        data={
            "id": user.id,
            "email": user.email
        }, 
        expire_delta=access_token_expire
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/verifytoken")
async def verify_user_token(
    token: str, session: AsyncSession = Depends(get_session)
):
    await verify_token(token, session)
    return {"message": "Token is Valid"}


# ------------------------Forgot Password Routes-------------------------


# @app.post("/forgot-password")
# async def forgot_password(
#     request: ForgotPasswordRequest,
#     background_tasks: BackgroundTasks,
#     session: AsyncSession = Depends(get_session),
# ):
#     user = await get_user_by_email(request.email, session)

#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="User with this email does not exist.",
#         )

#     # Generate a token that expires in 10 minutes
#     token = serializer.dumps(user.email, salt=SALT)
#     reset_link = f"https://avowal-backend.vercel.app/reset-password?token={token}"

#     # Prepare the email
#     message = MessageSchema(
#         subject="Password Reset Request",
#         recipients=[request.email],
#         body=f"Click on the link to reset your password: {reset_link}",
#         subtype="html",
#     )

#     # Send email
#     fm = FastMail(conf)
#     background_tasks.add_task(fm.send_message, message)

#     return {"message": "Password reset email has been sent."}


# @app.post("/reset-password")
# async def reset_password(
#     request: ResetPasswordRequest, session: AsyncSession = Depends(get_session)
# ):
#     try:
#         # Decode the token (expires in 10 minutes)
#         email = serializer.loads(request.token, salt=SALT, max_age=600)
#     except SignatureExpired:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST, detail="The token has expired."
#         )
#     except BadTimeSignature:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token."
#         )

#     # Fetch user and update the password
#     user = await get_user_by_email(email, session)

#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
#         )

#     # Update the password (hash the password as per your application logic)
#     user.hashedpassword = pwd_context.hash(
#         request.new_password
#     )  # Make sure to hash this password before storing
#     session.add(user)
#     await session.commit()
#     return {"message": "Password has been reset successfully."}


# -------------------------Routes for user profile--------------------------------------


# User can only update username and relationship_status
@app.put("/update")
async def update_user(
    username: Optional[str] = None,
    relationship_status: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    current_user = await get_user_by_email(current_user.get("email"), session)

    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    if relationship_status:
        if relationship_status not in ["Single", "Committed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Relationship status can be either Single or Committed",
            )
        current_user.relationship_status = relationship_status
    if username:
        validate = lambda s: bool(fullmatch(r"[A-Za-z_.]+", s))
        if not validate(username):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid username. Only alphanumerics, _s and .s are allowed.",
            )
        
        # Check if username is already taken (heavy db call, use redis)
        user = await get_user_by_username(username, session)
        if user and user.id != current_user.id:
            raise HTTPException(status_code=403, detail=f"Username already taken")
        
        current_user.username = username

    if username or relationship_status:
        session.add(current_user)
        await session.commit()
        await session.refresh(current_user)

    data = jsonable_encoder(
        current_user, include=["id", "username", "relationship_status", "name"]
    )
    return {"message": "User updated successfully", "data": data}


# User can only update profile pic
@app.post("/update_profile_pic")
async def upload_profile_pic(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_user),
):

    current_user = await get_user_by_email(current_user.get("email"), session)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")

    if "image" not in file.content_type:
        return JSONResponse(
            status_code=404, content={"message": "File provided is not an image"}
        )

    # delete previous file from cloud
    if current_user.profile_pic != "images/profile/def.jpg":
        cloudinary.uploader.destroy(current_user.username)

    filecontent = await file.read()

    ext = file.filename.split(".")[-1]
    if ext not in ["jpg", "jpeg", "png"]:
        return JSONResponse(
            status_code=404, content={"message": "File provided is not an image"}
        )

    upload_result = cloudinary.uploader.upload(
        filecontent,
        public_id=current_user.username,
        eager=[
            {
                "width": 500,
                "height": 500,
                "crop": "thumb",
                "gravity": "auto",
                "aspect_ratio": "1.0",
                "radius": 10,
            }
        ],
    )
    current_user.profile_pic = upload_result["eager"][0]["secure_url"]
    session.add(current_user)
    await session.commit()
    return JSONResponse(
        status_code=200,
        content={
            "message": "Profile pic updated",
            "data": {"url": upload_result["eager"][0]["secure_url"]},
        },
    )


@app.get("/profile_data")
async def get_profile(current_user: Dict[str, Any] = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    current_user = await get_user_by_email(current_user.get("email"), session)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    data = jsonable_encoder(
        current_user, exclude=["hashedpassword", "id", "unread_confessions"]
    )
    return {"message": "Profile fetched successfully", "data": data}


@app.get("/search_users")
async def search_users(
    q: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):

    stmt = select(User).where(
        (User.username.ilike(f"{q}%")) | (User.email.ilike(f"{q}%"))
    )
    
    results = await session.execute(stmt)
    users = results.scalars().all()

    data = [
        jsonable_encoder(user, exclude=["hashedpassword", "id", "unread_confessions"])
        for user in users
    ]
    return {"message": "Users found", "data": data}


@app.get("/user")  # viewed profile function yet to be implemented
async def get_user(
    username: str,
    searched: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    
    if searched and username!=current_user.get("username"):
        user = await get_user_by_username(username, session)
        if user:
            user.searched_counts += 1
            session.add(user)
            await session.commit()

    else:
        user = await get_user_by_username(username, session)

    if not user:
        raise HTTPException(status_code=403, detail=f"Username not found")
    data = jsonable_encoder(user, exclude=["hashedpassword", "id", "unread_confessions"])

    return {"message": "User found", "data": data}


@app.delete("/delete_user")
async def delete_user(
    session: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    current_user: User = await get_user_by_email(current_user.get("email"), session)
    if current_user.profile_pic != "images/profile/def.jpg":
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, lambda: cloudinary.uploader.destroy(current_user.username)
        )
        if response.get("result") != "ok":
            logging.warning("*******ALERT*********:", response)

    await session.delete(current_user)
    await session.commit()
    return {"message": "User deleted successfully"}


# ----------------- Routes for confessions--------------------


async def extract_mentions(
    content: str, 
    session: AsyncSession
) -> Dict[str, Union[int, None]]:
    """
    Extract mentions from the content and map them to user IDs.
    Returns: A dictionary mapping usernames to their user IDs (or None if not found).
    """
    # Extract mentions using regex
    pattern = r"@([A-Za-z0-9_.]+)"  # Matches @username
    mentions = set(findall(pattern, content))

    res = {}
    if not mentions:
        return res

    stmt = select(User.username, User.id).where(User.username.in_(list(mentions)))
    result = await session.execute(stmt)
    existing_users = result.all()

    existing_usernames = {user.username: user.id for user in existing_users}

    for username in mentions:
        res[username] = existing_usernames.get(username)
    return res


@app.post("/confessions", response_model=ConfessionResponse)
async def add_confession(
    confession: ConfessionCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    
    mentioned_usernames = await extract_mentions(confession.content, session)
    # return JSONResponse(mentioned_usernames, status_code=200)
    
    valid_user_ids = []
    for username, user_id in mentioned_usernames.items():
        if user_id is None:
            # Not to raise exception here, store the mentions as a plain text then
            # Edge case : In future with same username a user got registered in that case no linking would happen for this confession
            continue

        valid_user_ids.append(user_id)
    
    # Backward compatibility
    valid_users = await session.execute(select(User).where(User.id.in_(valid_user_ids)))
    valid_users = valid_users.scalars().all()
    
    try:
        # Check with LLM analyzer

        llm_decision = await analyzer.analyze_confession(confession.content)
    except Exception as e:
        logging.error(f"Error occurred in add_confession: {traceback.format_exc()}")
        # Fallback: Allow confession if LLM analysis fails
        logging.warning(f"LLM analysis failed, allowing confession: {str(e)}")
        llm_decision = "APPROVE"  # Fallback to approve
    
    if llm_decision and llm_decision.lower().startswith("reject"):
        raise HTTPException(status_code=403, detail="Confession rejected by content analyzer")
    

    db_confession = Confession(content=confession.content, mentions=valid_users)
    session.add(db_confession)
    await session.commit()
    await session.refresh(db_confession)

    # Load mentions to avoid serialization issues and limit fields
    stmt = (
        select(Confession)
        .where(Confession.id == db_confession.id)
        .options(
            selectinload(Confession.mentions).load_only(User.id, User.username, User.profile_pic)
        )
    )
    result = await session.execute(stmt)
    db_confession: Confession = result.scalar_one()

    # This part is inefficient and should be done in a background task for production
    # For now, keeping it simple
    update_stmt = update(User).values(
        unread_confessions=func.array_prepend(
            db_confession.id, 
            User.unread_confessions
        )
    )
    await session.execute(update_stmt)
    await session.commit()

    return ConfessionResponse.from_orm(db_confession)


@app.get("/confessions")
async def get_confessions(
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    current_user:User = await get_user_by_email(current_user.get("email"), session)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    # Optimized query - select only needed columns
    if q:
        stmt = select(Confession.id, Confession.content, Confession.created_at, func.count(Comment.id)).outerjoin(Comment).group_by(Confession.id).where(
            Confession.content.ilike(f"%{q}%")
        ).order_by(Confession.created_at.desc()).offset(skip).limit(limit)
    else:
        stmt = select(Confession.id, Confession.content, Confession.created_at, func.count(Comment.id)).outerjoin(Comment).group_by(Confession.id).order_by(
            Confession.created_at.desc()
        ).offset(skip).limit(limit)
    
    result = await session.execute(stmt)
    confessions = result.mappings().all()

    unread_confessions_set = set(current_user.unread_confessions)
    mp: Dict[int, Set[str]] = defaultdict(set)
    data = []
    mentions_str, pattern = "", r"@([A-Za-z0-9_.]+)"
    for confession in confessions:
        data.append({
            "id": confession.id,
            "content": confession.content,
            "created_at": confession.created_at.isoformat(),
            "read": confession.id not in unread_confessions_set,
            "comments_count": confession.count,
            "mentions": []
        })
        
        temp_mentions = findall(pattern, confession.content)
        if temp_mentions:
            mp[confession.id].update(temp_mentions)
            mentions_str += '@' + ' @'.join(username for username in temp_mentions) + ' '

    map_username_to_user_id = await extract_mentions(mentions_str, session)

    for confession in data:
        if confession["id"] in mp:
            confession["mentions"] = [username for username in mp[confession["id"]] if username in map_username_to_user_id]

    return {
        "message": "Confessions fetched successfully", 
        "data": data
    }


@app.delete("/delete/confession")
async def delete_confession(
    confession_id: int,
    password: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Only for admin to delete any confession
    """
    if password == getenv("PASSWORD"):
        result = await delete_confession_and_related(
            confession_id=confession_id,session=session) # Error handeling is not proper
        if result:
            return {"message": "Confession deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Confession not found")
    raise HTTPException(status_code=401, detail="You are not allowed here")


@app.post("/confessions/mark_as_read")
async def mark_confessions_as_read(
    request: MarkAsReadRequest,
    session: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user = await session.get(User, current_user.get("id"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    unread_confessions_set = set(user.unread_confessions)
    unread_confessions_set -= set(request.confession_ids)
    user.unread_confessions = list(unread_confessions_set)

    session.add(user)
    await session.commit()
    return {"message": "Selected confessions marked as read successfully"}


# --------------------- Routes for comments-------------------------


# Function to publish comment events
# async def publish_comment_event(comment_data: dict):
#     await comment_event_queue.put(comment_data)

# Changed
@app.post("/confessions/{confession_id}/comments", response_model=CommentResponse)
async def add_comment(
    confession_id: int,
    comment: CommentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Dict = Depends(get_current_user),
):
    result = await session.execute(
        select(Confession.id).where(Confession.id == confession_id)
    )
    db_confession = result.scalar_one_or_none()
    if not db_confession:
        raise HTTPException(status_code=404, detail="Confession not found.")

    db_comment = Comment(
        content=comment.content,
        user_id=current_user.get("id"),
        confession_id=confession_id
    )
        
    session.add(db_comment)
    await session.commit()

    stmt = select(Comment).where(Comment.id == db_comment.id).options(selectinload(Comment.user))
    result = await session.execute(stmt)
    db_comment = result.scalar_one()

    return CommentResponse.from_orm(db_comment)


# Can be optimized with pagination if needed
# Changed
@app.get("/comment/{confession_id}")
async def get_comments(
    confession_id: int, session: AsyncSession = Depends(get_session)
):
    # Optimized query using composite index
    stmt = select(
        Comment.content, 
        Comment.user_id, 
        Comment.id, 
        Comment.created_at
    ).where(
        Comment.confession_id == confession_id
    ).order_by(Comment.created_at.desc())  # Use index for ordering
    
    result = await session.execute(stmt)
    comments = result.mappings().all()
    comments = jsonable_encoder(comments)
   
    # Batch user lookup for better performance
    if comments:
        user_ids = [comment["user_id"] for comment in comments]
        stmt = select(User.id, User.username, User.profile_pic).where(User.id.in_(user_ids))
        result = await session.execute(stmt)
        users = result.mappings().all()
        user_map = {user.id: user for user in users}

        for comment in comments:
            if comment.get("user_id") in user_map:
                comment["user"] = user_map[comment.get("user_id")]
    
    return JSONResponse(status_code=200, content={"message": jsonable_encoder(comments)})


@app.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    result = await session.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if current_user.get("id") != comment.user_id:
        return JSONResponse(
            status_code=400, content={"message": f"You are not allowed here"}
        )
    
    await session.delete(comment)
    await session.commit()
    
    return JSONResponse(
        status_code=200, content={"message": "Comment deleted successfully"}
    )


@app.post("set/email/")
async def set_email(password: str):
    if password != getenv("PASSWORD"):
        return JSONResponse(
            status_code=400,
            content={
                "message": f"Invalid Password, 2 more attempts and your ip is blocked"
            },
        )
        # IP blocking mechanism yet to be implement
    import json

    emails, names = [], []
    if not path.exists("data.json"):
        raise HTTPException(status_code=500, detail="data.json doesn't exists")
    with open(file="data.json", encoding="utf-8", mode="r") as f:
        data = json.loads(f.read())
    mp = {}
    for student in data:
        mp[student["email"]] = student["name"]
    myKeys = list(mp.keys())
    myKeys.sort()
    mp = {i: mp[i] for i in myKeys}
    for key in mp:
        emails.append(key)
        names.append(mp[key])
    with open(file="emails.json", encoding="utf-8", mode="w") as f:
        f.write(json.dumps({"emails": emails, "names": names}))
    return JSONResponse(status_code=200, content={"message": "Success"})

@app.get("/topsearched_usernames")
async def get_top_usernames(
    session: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    # Fetch top 10 usernames based on searched_counts
    stmt = select(User.username, User.searched_counts, User.profile_pic).order_by(User.searched_counts.desc()).limit(10)
    result = await session.execute(stmt)
    result = result.mappings().all()
    data = [{
        "username": row["username"],
        "profile_pic": row["profile_pic"],
        "searched_counts": row["searched_counts"],
    } for row in result]
    
    return JSONResponse(status_code=200, content={"message": "Success", "data": data})


if __name__ == "__main__":
    import uvicorn
    asyncio.run(on_startup())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, workers=1)