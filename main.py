import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select, Relationship
import redis
import json

# --- KONFIGURASI ---
DATABASE_URL = os.getenv("postgresql://postgres:OcoHWhOsbEUfJcMo@db.yhybaqdxhgdrjcfhizds.supabase.co:5432/postgres")
REDIS_URL = os.getenv("renewed-eagle-121073.upstash.io:6379")
REDIS_PASSWORD = os.getenv("gQAAAAAAAdjxAAIgcDJiNjNmNWVkODIzNTg0YmFiYjM2N2IwMTI4NTFkOGJmNQ")

# Engine dengan pool_pre_ping agar koneksi tidak mudah putus
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

app = FastAPI(title="Sistem KRS API")

# --- WAJIB: Aktifkan CORS agar Frontend bisa akses ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODEL DATA ---
class Dosen(SQLModel, table=True):
    __tablename__ = "tb_dosen"
    id: Optional[int] = Field(default=None, primary_key=True)
    nip: str = Field(unique=True, index=True)
    nama: str
    gelar: Optional[str] = None
    no_hp: Optional[str] = None
    email: Optional[str] = None
    mahasiswa_bimbingan: List["Mahasiswa"] = Relationship(back_populates="dpa")

class Mahasiswa(SQLModel, table=True):
    __tablename__ = "tb_mahasiswa"
    id: Optional[int] = Field(default=None, primary_key=True)
    nim: str = Field(unique=True, index=True)
    nama: str
    angkatan: int
    id_dpa: Optional[int] = Field(default=None, foreign_key="tb_dosen.id")
    dpa: Optional[Dosen] = Relationship(back_populates="mahasiswa_bimbingan")

def get_session():
    with Session(engine) as session:
        yield session

@app.get("/")
def root():
    return {"message": "Backend Sistem KRS Berjalan Lancar!"}

@app.get("/mahasiswa/")
def read_mahasiswa(session: Session = Depends(get_session)):
    results = session.exec(select(Mahasiswa)).all()
    data = []
    for m in results:
        data.append({
            "id": m.id,
            "nim": m.nim,
            "nama": m.nama,
            "nama_dpa": m.dpa.nama if m.dpa else "Belum Ada"
        })
    return data

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
