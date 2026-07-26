from utils.database import get_db
from models.user import User
from utils.password import verify_password
from sqlalchemy.exc import SQLAlchemyError
from exceptions.auth import AuthError
from fastapi_jwt import JwtAccessBearerCookie
import secrets
from datetime import timedelta
import os
import logging

logger = logging.getLogger("supportops.auth")

# JWT配置
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'default_secret_key') + 'happy'

# 从请求头或cookie中读取访问令牌（优先从请求头读取）
access_security = JwtAccessBearerCookie(
    secret_key=JWT_SECRET_KEY,
    auto_error=True,
    access_expires_delta=timedelta(days=2)  # 访问令牌有效期为2天
)

def create_token(user_id: int, user_name: str, salting: str = ""):
    # 生成token的主体部分，包含用户名和随机盐值
    subject = {
        "user_id": user_id,
        "user_name": user_name,
        "salting": secrets.token_hex(16)
    }
    
    # 创建新的访问令牌
    access_token = access_security.create_access_token(subject=subject)
    
    return access_token


def authenticate(username: str, password: str) -> str:
    """
    认证用户
    
    Args:
        username (str): 用户名
        password (str): 明文密码
    
    Returns:
        str: 认证成功返回token，失败返回None
    
    Raises:
        AuthError: 认证失败时抛出
    """
    db = next(get_db())
    try:
        # 查询用户
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            raise AuthError("认证失败")
        
        # 验证密码
        if not verify_password(password, user.password_hash):
            raise AuthError("认证失败")
        
        # 如果需要生成token，可以在这里实现
        # return create_token(user.id)
        return create_token(user.id, user.username)
    
    except SQLAlchemyError as e:
        raise AuthError("认证失败") from e
    finally:
        db.close()

def register_user(username: str, password: str):
    """
    注册新用户
    
    Args:
        username (str): 用户名
        password (str): 明文密码
    
    Raises:
        AuthError: 如果用户名已存在或注册失败
    """
    from utils.password import hash_password

    db = next(get_db())
    try:
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            raise AuthError("用户名已存在")

        new_user = User(username=username, password_hash=hash_password(password))
        db.add(new_user)
        db.commit()
        logger.info("用户 %s 注册成功", username)
    except AuthError:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        logger.error("注册数据库操作失败: %s", e)
        db.rollback()
        raise AuthError("注册失败，请稍后重试")
    except Exception as e:
        logger.error("注册过程中发生未知错误: %s", e)
        db.rollback()
        raise AuthError("注册失败，请稍后重试")
    finally:
        db.close()