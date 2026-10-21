import uuid 
from sqlalchemy import BigInteger, Column, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exit.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy import TIMESTAMP 
from pydantic_settings import BaseSettings

Base = declarative_base()

class PullRequest(Base):
    __tablename__ = "pull_requests"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_full_name = Column(Text, nullable=False)
    pr_number = Column(Integer, nullable=False)
    head_sha = Column(Text, nullable=False)
    installation_id = Column(BigInteger, nullable=False)
    status = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())

class Settings(BaseSettings):
    database_url: str = ""
    redis_url: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
