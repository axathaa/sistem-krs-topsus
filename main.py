import os
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select, Relationship
import redis
import json

# --- KONFIGURASI ---
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

# Validasi wajib saat startup, bukan saat import
if not DATABASE_URL:
    raise RuntimeError("Environment variable DATABASE_URL belum diset!")

# Engine dibuat SEKALI, tapi setelah validasi di atas
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

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

# --- REDIS CLIENT ---
def get_redis():
    if not REDIS_URL:
        return None
    try:
        r = redis.Redis.from_url(
            REDIS_URL,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        r.ping()
        return r
    except Exception:
        return None  # Redis gagal tidak crash app

redis_client = get_redis()

# --- LIFESPAN: buat tabel otomatis saat startup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield

app = FastAPI(title="Sistem KRS API", lifespan=lifespan)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DEPENDENCY ---
def get_session():
    with Session(engine) as session:
        yield session

# =====================
# ENDPOINT ROOT
# =====================
@app.get("/")
def root():
    return {"message": "Backend Sistem KRS Berjalan Lancar!"}

# =====================
# CRUD DOSEN
# =====================
@app.get("/dosen/")
def get_all_dosen(session: Session = Depends(get_session)):
    # Coba ambil dari cache Redis dulu
    if redis_client:
        cached = redis_client.get("dosen:all")
        if cached:
            return json.loads(cached)

    results = session.exec(select(Dosen)).all()
    data = [
        {
            "id": d.id,
            "nip": d.nip,
            "nama": d.nama,
            "gelar": d.gelar,
            "no_hp": d.no_hp,
            "email": d.email,
        }
        for d in results
    ]

    if redis_client:
        redis_client.setex("dosen:all", 300, json.dumps(data))  # cache 5 menit

    return data

@app.get("/dosen/{dosen_id}")
def get_dosen(dosen_id: int, session: Session = Depends(get_session)):
    dosen = session.get(Dosen, dosen_id)
    if not dosen:
        raise HTTPException(status_code=404, detail="Dosen tidak ditemukan")
    return dosen

@app.post("/dosen/", status_code=201)
def create_dosen(dosen: Dosen, session: Session = Depends(get_session)):
    session.add(dosen)
    session.commit()
    session.refresh(dosen)
    if redis_client:
        redis_client.delete("dosen:all")  # invalidate cache
    return dosen

@app.put("/dosen/{dosen_id}")
def update_dosen(dosen_id: int, dosen_data: Dosen, session: Session = Depends(get_session)):
    dosen = session.get(Dosen, dosen_id)
    if not dosen:
        raise HTTPException(status_code=404, detail="Dosen tidak ditemukan")
    dosen_data_dict = dosen_data.model_dump(exclude_unset=True)
    for key, value in dosen_data_dict.items():
        setattr(dosen, key, value)
    session.commit()
    session.refresh(dosen)
    if redis_client:
        redis_client.delete("dosen:all")
    return dosen

@app.delete("/dosen/{dosen_id}")
def delete_dosen(dosen_id: int, session: Session = Depends(get_session)):
    dosen = session.get(Dosen, dosen_id)
    if not dosen:
        raise HTTPException(status_code=404, detail="Dosen tidak ditemukan")
    session.delete(dosen)
    session.commit()
    if redis_client:
        redis_client.delete("dosen:all")
    return {"message": "Dosen berhasil dihapus"}

# =====================
# CRUD MAHASISWA
# =====================
@app.get("/mahasiswa/")
def get_all_mahasiswa(session: Session = Depends(get_session)):
    results = session.exec(select(Mahasiswa)).all()
    return [
        {
            "id": m.id,
            "nim": m.nim,
            "nama": m.nama,
            "angkatan": m.angkatan,
            "id_dpa": m.id_dpa,
            "nama_dpa": m.dpa.nama if m.dpa else "Belum Ada",
        }
        for m in results
    ]

@app.get("/mahasiswa/{mahasiswa_id}")
def get_mahasiswa(mahasiswa_id: int, session: Session = Depends(get_session)):
    mhs = session.get(Mahasiswa, mahasiswa_id)
    if not mhs:
        raise HTTPException(status_code=404, detail="Mahasiswa tidak ditemukan")
    return mhs

@app.post("/mahasiswa/", status_code=201)
def create_mahasiswa(mahasiswa: Mahasiswa, session: Session = Depends(get_session)):
    session.add(mahasiswa)
    session.commit()
    session.refresh(mahasiswa)
    return mahasiswa

@app.put("/mahasiswa/{mahasiswa_id}")
def update_mahasiswa(mahasiswa_id: int, mhs_data: Mahasiswa, session: Session = Depends(get_session)):
    mhs = session.get(Mahasiswa, mahasiswa_id)
    if not mhs:
        raise HTTPException(status_code=404, detail="Mahasiswa tidak ditemukan")
    for key, value in mhs_data.model_dump(exclude_unset=True).items():
        setattr(mhs, key, value)
    session.commit()
    session.refresh(mhs)
    return mhs

@app.delete("/mahasiswa/{mahasiswa_id}")
def delete_mahasiswa(mahasiswa_id: int, session: Session = Depends(get_session)):
    mhs = session.get(Mahasiswa, mahasiswa_id)
    if not mhs:
        raise HTTPException(status_code=404, detail="Mahasiswa tidak ditemukan")
    session.delete(mhs)
    session.commit()
    return {"message": "Mahasiswa berhasil dihapus"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
