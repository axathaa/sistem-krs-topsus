import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from sqlmodel import SQLModel, Field, create_engine, Session, select, Relationship
import redis
import json

# --- KONFIGURASI DATABASE & REDIS ---
DATABASE_URL = os.getenv("postgresql://postgres:OcoHWhOsbEUfJcMo@db.yhybaqdxhgdrjcfhizds.supabase.co:5432/postgres")
REDIS_URL = os.getenv("renewed-eagle-121073.upstash.io:6379")
REDIS_PASSWORD = os.getenv("gQAAAAAAAdjxAAIgcDJiNjNmNWVkODIzNTg0YmFiYjM2N2IwMTI4NTFkOGJmNQ")

# Koneksi Database
engine = create_engine(DATABASE_URL)

# Koneksi Redis untuk Caching
cache = redis.Redis(
    host=REDIS_URL,
    port=6379,
    password=REDIS_PASSWORD,
    decode_responses=True
)

app = FastAPI(title="Sistem KRS API")

# --- MODEL DATA (TABEL) ---

class Dosen(SQLModel, table=True):
    __tablename__ = "tb_dosen"
    id: Optional[int] = Field(default=None, primary_key=True)
    nip: str = Field(unique=True, index=True)
    nama: str
    gelar: Optional[str] = None
    no_hp: Optional[str] = None
    email: Optional[str] = None
    
    # Relasi ke Mahasiswa
    mahasiswa_bimbingan: List["Mahasiswa"] = Relationship(back_populates="dpa")

class Mahasiswa(SQLModel, table=True):
    __tablename__ = "tb_mahasiswa"
    id: Optional[int] = Field(default=None, primary_key=True)
    nim: str = Field(unique=True, index=True)
    nama: str
    angkatan: int
    no_hp: Optional[str] = None
    email: Optional[str] = None
    
    # Foreign Key ke Dosen
    id_dpa: Optional[int] = Field(default=None, foreign_key="tb_dosen.id")
    dpa: Optional[Dosen] = Relationship(back_populates="mahasiswa_bimbingan")

# --- DEPENDENCY ---
def get_session():
    with Session(engine) as session:
        yield session

# --- ENDPOINTS CRUD DOSEN ---

@app.post("/dosen/", response_model=Dosen)
def create_dosen(dosen: Dosen, session: Session = Depends(get_session)):
    session.add(dosen)
    session.commit()
    session.refresh(dosen)
    # Hapus cache setiap ada perubahan data
    cache.delete("daftar_dosen")
    return dosen

@app.get("/dosen/", response_model=List[Dosen])
def read_dosen(session: Session = Depends(get_session)):
    # Cek Cache Redis dulu
    cached_data = cache.get("daftar_dosen")
    if cached_data:
        return json.loads(cached_data)
    
    # Jika tidak ada di cache, ambil dari database
    db_data = session.exec(select(Dosen)).all()
    # Simpan ke cache selama 5 menit (300 detik)
    cache.setex("daftar_dosen", 300, json.dumps([d.dict() for d in db_data]))
    return db_data

# --- ENDPOINTS CRUD MAHASISWA ---

@app.post("/mahasiswa/", response_model=Mahasiswa)
def create_mahasiswa(mhs: Mahasiswa, session: Session = Depends(get_session)):
    session.add(mhs)
    session.commit()
    session.refresh(mhs)
    return mhs

@app.get("/mahasiswa/", response_model=List[dict])
def read_mahasiswa(session: Session = Depends(get_session)):
    statement = select(Mahasiswa)
    results = session.exec(statement).all()
    
    # Format data agar memunculkan nama DPA nya
    data = []
    for m in results:
        m_dict = m.dict()
        m_dict["nama_dpa"] = m.dpa.nama if m.dpa else "Belum Ditentukan"
        data.append(m_dict)
    return data

@app.delete("/mahasiswa/{mhs_id}")
def delete_mahasiswa(mhs_id: int, session: Session = Depends(get_session)):
    mhs = session.get(Mahasiswa, mhs_id)
    if not mhs:
        raise HTTPException(status_code=404, detail="Mahasiswa tidak ditemukan")
    session.delete(mhs)
    session.commit()
    return {"status": "Berhasil dihapus"}

@app.get("/")
def root():
    return {"message": "Backend Sistem KRS Berjalan Lancar!"}