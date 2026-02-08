"""
BitPro 配置管理
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
import json


class Settings(BaseSettings):
    """应用配置"""
    
    # API 配置
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "BitPro"
    
    # CORS 配置
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:8888", "http://127.0.0.1:8888"]
    
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            if v.startswith("["):
                return json.loads(v)
            return [i.strip() for i in v.split(",")]
        return v
    
    # 数据库配置
    DB_PATH: Optional[str] = None
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    
    # 交易所配置 - OKX
    OKX_API_KEY: Optional[str] = None
    OKX_API_SECRET: Optional[str] = None
    OKX_PASSPHRASE: Optional[str] = None
    OKX_TESTNET: bool = True
    
    # AI 配置
    QWEN_API_KEY: Optional[str] = None
    
    # Redis 配置 (可选)
    REDIS_URL: Optional[str] = None
    
    # 数据同步间隔 (秒)
    SYNC_INTERVAL_TICKER: int = 10
    SYNC_INTERVAL_FUNDING: int = 60
    SYNC_INTERVAL_KLINE: int = 300
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# 全局配置实例
settings = Settings()
