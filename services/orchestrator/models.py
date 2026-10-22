import uuid
from sqlalchemy import BigInteger, Column, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy import TIMESTAMP
from pydantic import BaseModel
from pydantic_settings import BaseSettings

Base = declarative_base()

class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_full_name = Column(Text, nullable=False)
    pr_number = Column(Integer, nullable=False)
    head_sha = Column(Text, nullable=False)
    installation_id = Column(BigInteger, nullable=False)
    status = Column(Text, default="pending")
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())

class Findings(Base):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pr_id = Column(UUID(as_uuid=True), ForeignKey("pull_requests.id"), nullable=False)
    file = Column(Text, nullable=False)
    line= Column(Integer, nullable=False)
    severity = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    agent = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())

class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_full_name = Column(Text, nullable=False)
    pattern_text = Column(Text, nullable=False)
    frequency = Column(Integer, default=1)
    updated_at = Column(TIMESTAMP, nullable=False, default=func.now())

class AnalyzeResult(BaseModel):
    pr_id: uuid.UUID
    pr_number: int
    repo_full_name: str
    head_sha: str
    installation_id: int

class Settings(BaseSettings):
    database_url: str = ""
    redis_url: str = ""
    github_app_id: str = ""
    github_app_private_key: str = ""
    openai_api_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://langfuse:3000"

    class Config:
        env_file = ".env"