import os
import json
import sys
from typing import List, Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import SQLModel, Field, create_engine, Session, select, Relationship
from jose import JWTError, jwt
from passlib.context import CryptContext
import redis

# --- 1. KONFIGURASI KEAMANAN & JWT ---
SECRET_KEY = "ALEXA_SUPER_SECRET_KEY_2026" 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 2. KONFIGURASI DATABASE & REDIS ---
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

engine = None
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def get_redis():
    if not REDIS_URL: return None
    try:
        r = redis.Redis.from_url(
            REDIS_URL, password=REDIS_PASSWORD,
            decode_responses=True, socket_connect_timeout=3
        )
        r.ping()
        return r
    except Exception: return None

redis_client = get_redis()

# --- 3. MODEL DATA (SQLMODEL) ---
class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    role: str
    link_id: Optional[int] = None

class Dosen(SQLModel, table=True):
    __tablename__ = "tb_dosen"
    id: Optional[int] = Field(default=None, primary_key=True)
    nip: str = Field(unique=True, index=True)
    nama: str
    no_hp: Optional[str] = None
    email: Optional[str] = None
    mahasiswa_bimbingan: List["Mahasiswa"] = Relationship(back_populates="dpa")

class Mahasiswa(SQLModel, table=True):
    __tablename__ = "tb_mahasiswa"
    id: Optional[int] = Field(default=None, primary_key=True)
    nim: str = Field(unique=True, index=True)
    nama: str
    no_hp: Optional[str] = None
    email: Optional[str] = None
    id_dpa: Optional[int] = Field(default=None, foreign_key="tb_dosen.id")
    dpa: Optional[Dosen] = Relationship(back_populates="mahasiswa_bimbingan")

# --- 4. INISIALISASI APP & DEPENDENCIES ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine:
        SQLModel.metadata.create_all(engine)
    yield

app = FastAPI(title="Sistem KRS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_session():
    if not engine:
        raise HTTPException(status_code=500, detail="Database belum terkonfigurasi")
    with Session(engine) as session:
        yield session

# --- 5. ENDPOINTS AUTHENTICATION ---
@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=401, 
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={
            "sub": user.username, 
            "id": user.id, 
            "role": user.role, 
            "link_id": user.link_id
        }
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role 
    }

# --- 6. ENDPOINTS DOSEN ---
@app.get("/dosen/")
def get_all_dosen(session: Session = Depends(get_session)):
    if redis_client:
        cached = redis_client.get("dosen:all")
        if cached: return json.loads(cached)
    
    results = session.exec(select(Dosen)).all()
    data = [{"id": d.id, "nip": d.nip, "nama": d.nama, "no_hp": d.no_hp, "email": d.email} for d in results]
    
    if redis_client:
        redis_client.setex("dosen:all", 300, json.dumps(data))
    return data

@app.get("/dosen/{dosen_id}")
def get_dosen(dosen_id: int, session: Session = Depends(get_session)):
    dosen = session.get(Dosen, dosen_id)
    if not dosen: raise HTTPException(status_code=404, detail="Dosen tidak ditemukan")
    return dosen

@app.post("/dosen/", status_code=201)
def create_dosen(dosen: Dosen, session: Session = Depends(get_session)):
    session.add(dosen)
    session.commit()
    session.refresh(dosen)
    if redis_client: redis_client.delete("dosen:all")
    return dosen

# --- 7. ENDPOINTS MAHASISWA ---
@app.get("/mahasiswa/")
def get_all_mahasiswa(session: Session = Depends(get_session)):
    results = session.exec(select(Mahasiswa)).all()
    return [{
        "id": m.id, "nim": m.nim, "nama": m.nama, "no_hp": m.no_hp, 
        "email": m.email, "id_dpa": m.id_dpa, 
        "nama_dpa": m.dpa.nama if m.dpa else "Belum Ada"
    } for m in results]

@app.post("/mahasiswa/", status_code=201)
def create_mahasiswa(mahasiswa: Mahasiswa, session: Session = Depends(get_session)):
    session.add(mahasiswa)
    session.commit()
    session.refresh(mahasiswa)
    return mahasiswa

# --- 8. ROOT & RUNNER ---
@app.get("/")
def root():
    return {
        "message": "Backend Sistem KRS Berjalan",
        "database_connected": engine is not None,
        "redis_connected": redis_client is not None,
    }

if __name__ == "__main__":
    import uvicorn
    port
