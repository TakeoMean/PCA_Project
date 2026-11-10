from datetime import datetime, timedelta, timezone
import os

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

SECRET_KEY = os.getenv('SECRET_KEY', 'local-development-secret-change-before-deployment')
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 120

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login')
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except ValueError:
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {'sub': subject, 'exp': datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get('sub')
        if username is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


ROLE_PERMISSIONS = {
    'Administrator': frozenset({
        'audit:read',
        'departments:write',
        'reports:read',
        'risks:assess',
        'risks:create',
        'risks:read',
        'treatments:approve',
        'treatments:manage',
        'users:manage',
    }),
    'SMCA Manager': frozenset({
        'audit:read',
        'departments:write',
        'reports:read',
        'risks:assess',
        'risks:create',
        'risks:read',
        'treatments:approve',
        'treatments:manage',
    }),
    'Risk Manager': frozenset({
        'audit:read',
        'reports:read',
        'risks:assess',
        'risks:create',
        'risks:read',
        'treatments:manage',
    }),
    'Department Manager': frozenset({
        'risks:assess',
        'risks:create',
        'risks:read',
        'treatments:manage',
    }),
    'Auditor': frozenset({
        'audit:read',
        'reports:read',
        'risks:read',
    }),
}


def has_permission(user: User, permission: str) -> bool:
    role_name = user.role.name if user.role else ''
    return permission in ROLE_PERMISSIONS.get(role_name, frozenset())


def require_permission(permission: str):
    def permission_dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Your role does not allow {permission.replace(":", " ")}',
            )
        return user

    return permission_dependency


def can_access_department(user: User, department_id: int) -> bool:
    role_name = user.role.name if user.role else ''
    if role_name in {'Administrator', 'SMCA Manager', 'Risk Manager', 'Auditor'}:
        return True
    return user.department_id == department_id
