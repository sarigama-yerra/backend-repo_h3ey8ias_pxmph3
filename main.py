import os
from datetime import datetime, date
from typing import Optional, List
from uuid import uuid4
import hashlib
import secrets

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from database import db, create_document, get_documents
from schemas import (
    Devoteeuser,
    Seva,
    Room,
    Sevabooking,
    Roombooking,
    Newspost,
    Contactmessage,
)

app = FastAPI(title="Sri Raghavendra Swamy Matha API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# Utils
# ------------------------

def serialize_doc(doc):
    if not doc:
        return doc
    doc = dict(doc)
    _id = doc.pop("_id", None)
    if _id is not None:
        doc["id"] = str(_id)
    # Convert datetime/date to isoformat
    for k, v in list(doc.items()):
        if isinstance(v, (datetime, date)):
            doc[k] = v.isoformat()
    return doc


# Simple password hashing (PBKDF2)
# Stored format: "salt$hexhash"

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hexhash = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return dk.hex() == hexhash
    except Exception:
        return False


# ------------------------
# Auth models
# ------------------------

class RegisterPayload(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    name: str
    email: EmailStr
    is_admin: bool


# ------------------------
# Auth helpers
# ------------------------

def get_user_by_token(token: Optional[str] = Header(default=None, alias="Authorization")):
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    # Support formats: "Bearer <token>" or raw token
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    user = db["devoteeuser"].find_one({"session_token": token})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_admin(user=Depends(get_user_by_token)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ------------------------
# Root + health
# ------------------------

@app.get("/")
def read_root():
    return {"message": "Sri Raghavendra Swamy Matha API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()[:10]
            response["database"] = "✅ Connected & Working"
    except Exception as e:
        response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
    return response


# ------------------------
# Auth endpoints
# ------------------------

@app.post("/api/auth/register", response_model=TokenResponse)
def register(payload: RegisterPayload):
    existing = db["devoteeuser"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    password_hash = hash_password(payload.password)
    token = uuid4().hex
    user_model = Devoteeuser(
        name=payload.name,
        email=payload.email,
        password_hash=password_hash,
        phone=payload.phone,
        is_admin=False,
    )
    to_insert = {**user_model.model_dump(), "session_token": token, "token_issued_at": datetime.utcnow()}
    create_document("devoteeuser", to_insert)
    return TokenResponse(token=token, name=user_model.name, email=user_model.email, is_admin=False)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginPayload):
    user = db["devoteeuser"].find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = uuid4().hex
    db["devoteeuser"].update_one({"_id": user["_id"]}, {"$set": {"session_token": token, "token_issued_at": datetime.utcnow()}})
    return TokenResponse(token=token, name=user.get("name"), email=user.get("email"), is_admin=bool(user.get("is_admin", False)))


@app.get("/api/auth/me")
def me(user=Depends(get_user_by_token)):
    return serialize_doc(user)


# ------------------------
# Sevas & Rooms
# ------------------------

@app.get("/api/sevas")
def list_sevas():
    items = get_documents("seva")
    return [serialize_doc(i) for i in items]


class SevaCreate(BaseModel):
    title: str
    description: Optional[str] = None
    time: str
    cost: float


@app.post("/api/sevas")
def create_seva(payload: SevaCreate, admin=Depends(require_admin)):
    model = Seva(**payload.model_dump())
    _id = create_document("seva", model)
    return {"id": _id}


@app.get("/api/rooms")
def list_rooms():
    items = get_documents("room")
    return [serialize_doc(i) for i in items]


class RoomCreate(BaseModel):
    name: str
    capacity: int
    price: float
    amenities: Optional[List[str]] = []


@app.post("/api/rooms")
def create_room(payload: RoomCreate, admin=Depends(require_admin)):
    model = Room(**payload.model_dump())
    _id = create_document("room", model)
    return {"id": _id}


# ------------------------
# Bookings
# ------------------------

class SevaBookingCreate(BaseModel):
    seva_id: str
    date: date
    quantity: int = 1


@app.post("/api/book/seva")
def book_seva(payload: SevaBookingCreate, user=Depends(get_user_by_token)):
    from bson import ObjectId
    seva = db["seva"].find_one({"_id": ObjectId(payload.seva_id)})
    if not seva:
        raise HTTPException(status_code=404, detail="Seva not found")
    amount = float(seva.get("cost", 0)) * payload.quantity
    model = Sevabooking(
        user_email=user.get("email"),
        seva_id=payload.seva_id,
        date=payload.date,
        quantity=payload.quantity,
        amount=amount,
        status="confirmed",
    )
    _id = create_document("sevabooking", model)
    return {"id": _id}


class RoomBookingCreate(BaseModel):
    room_id: str
    check_in: date
    check_out: date
    guests: int


@app.post("/api/book/room")
def book_room(payload: RoomBookingCreate, user=Depends(get_user_by_token)):
    from bson import ObjectId
    room = db["room"].find_one({"_id": ObjectId(payload.room_id)})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    nights = (payload.check_out - payload.check_in).days
    if nights <= 0:
        raise HTTPException(status_code=400, detail="Check-out must be after check-in")
    amount = float(room.get("price", 0)) * max(1, nights)
    model = Roombooking(
        user_email=user.get("email"),
        room_id=payload.room_id,
        check_in=payload.check_in,
        check_out=payload.check_out,
        guests=payload.guests,
        amount=amount,
        status="confirmed",
    )
    _id = create_document("roombooking", model)
    return {"id": _id}


@app.get("/api/bookings")
def my_bookings(kind: Optional[str] = None, user=Depends(get_user_by_token)):
    filt = {"user_email": user.get("email")}
    collection = "sevabooking" if kind == "seva" else "roombooking" if kind == "room" else None
    results = []
    if collection:
        results = [serialize_doc(x) for x in db[collection].find(filt).sort("created_at", -1)]
    else:
        results = {
            "sevas": [serialize_doc(x) for x in db["sevabooking"].find(filt).sort("created_at", -1)],
            "rooms": [serialize_doc(x) for x in db["roombooking"].find(filt).sort("created_at", -1)],
        }
    return results


# ------------------------
# News & Contact
# ------------------------

@app.get("/api/news")
def list_news():
    posts = db["newspost"].find().sort("published_on", -1)
    return [serialize_doc(p) for p in posts]


class NewsCreate(BaseModel):
    title: str
    content: str
    published_on: date
    tags: Optional[List[str]] = []


@app.post("/api/news")
def create_news(payload: NewsCreate, admin=Depends(require_admin)):
    model = Newspost(**payload.model_dump())
    _id = create_document("newspost", model)
    return {"id": _id}


class ContactPayload(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    message: str


@app.post("/api/contact")
def contact(payload: ContactPayload):
    model = Contactmessage(**payload.model_dump())
    _id = create_document("contactmessage", model)
    return {"ok": True, "id": _id}


# ------------------------
# Seed endpoint (optional)
# ------------------------

@app.post("/api/seed")
def seed_basic(admin=Depends(require_admin)):
    if db["seva"].count_documents({}) == 0:
        sevas = [
            {"title": "Suprabhatam Seva", "description": "Morning worship", "time": "6:30 AM", "cost": 100.0},
            {"title": "Maha Mangalarati", "description": "Evening aarti", "time": "7:00 PM", "cost": 150.0},
            {"title": "Annadan Seva", "description": "Food offering", "time": "12:30 PM", "cost": 250.0},
        ]
        for s in sevas:
            create_document("seva", Seva(**s))
    if db["room"].count_documents({}) == 0:
        rooms = [
            {"name": "Standard Room", "capacity": 2, "price": 800.0, "amenities": ["Fan", "Attached Bath"]},
            {"name": "AC Room", "capacity": 3, "price": 1500.0, "amenities": ["AC", "Geyser", "Attached Bath"]},
        ]
        for r in rooms:
            create_document("room", Room(**r))
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
