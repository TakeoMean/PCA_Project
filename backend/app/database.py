import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

database_url = os.getenv('DATABASE_URL')
if database_url:
    engine_url = database_url
else:
    engine_url = URL.create(
        'postgresql+psycopg',
        username=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
        host=os.getenv('DATABASE_HOST', 'localhost'),
        port=int(os.getenv('DATABASE_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'smca'),
    )

connect_args = {}
if isinstance(engine_url, str) and engine_url.startswith('sqlite'):
    connect_args = {'check_same_thread': False}

engine = create_engine(engine_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
