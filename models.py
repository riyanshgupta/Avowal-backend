from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel, ARRAY, Column, Integer, String, Text
from datetime import datetime
from sqlalchemy import Index

class ConfessionMentionLink(SQLModel, table=True):
    __table_args__ = (
        Index('idx_confession_mention_link', 'confession_id', 'user_id'),
    )
    
    confession_id: Optional[int] = Field(
        default=None, foreign_key="confession.id", primary_key=True
    )
    user_id: Optional[int] = Field(
        default=None, foreign_key="user.id", primary_key=True
    )


class Comment(SQLModel, table=True):
    __table_args__ = (
        Index('idx_comment_confession_created', 'confession_id', 'created_at'),
        Index('idx_comment_user_created', 'user_id', 'created_at'),
    )
    
    id: Optional[int] = Field(primary_key=True)
    content: str = Field(sa_column=Column(Text, nullable=False))  # Fixed: moved nullable to Column
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)

    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    confession_id: Optional[int] = Field(default=None, foreign_key="confession.id", index=True)

    user: Optional["User"] = Relationship(back_populates="comments")
    confession: Optional["Confession"] = Relationship(back_populates="comments")


class Confession(SQLModel, table=True):
    __table_args__ = (
        Index('idx_confession_created_at', 'created_at'),
        Index('idx_confession_content_gin', 'content', postgresql_using='gin', postgresql_ops={'content': 'gin_trgm_ops'}),
    )
    
    id: Optional[int] = Field(primary_key=True)
    content: str = Field(sa_column=Column(Text, nullable=False))  # Fixed: moved nullable to Column
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)

    mentions: List["User"] = Relationship(
        back_populates="mentioned_in", link_model=ConfessionMentionLink
    )
    comments: List[Comment] = Relationship(back_populates="confession")


class User(SQLModel, table=True):
    __table_args__ = (
        Index('idx_user_email', 'email'),
        Index('idx_user_username', 'username'),
        Index('idx_user_relationship_status', 'relationship_status'),
    )
    
    id: Optional[int] = Field(primary_key=True)
    username: str = Field(max_length=50, unique=True, nullable=False, index=True)
    email: str = Field(max_length=255, unique=True, nullable=False, index=True)
    name: str = Field(max_length=255, nullable=False)
    hashedpassword: str = Field(max_length=255, nullable=False)
    profile_pic: str = Field(
        max_length=500, nullable=False, default="images/profile/def.jpg"
    )
    unread_confessions: List[int] = Field(
        default=[], sa_column=Column(ARRAY(Integer))
    )
    relationship_status: str = Field(max_length=10, default="Single", nullable=False)

    mentioned_in: List[Confession] = Relationship(
        back_populates="mentions", link_model=ConfessionMentionLink
    )
    comments: List[Comment] = Relationship(back_populates="user")