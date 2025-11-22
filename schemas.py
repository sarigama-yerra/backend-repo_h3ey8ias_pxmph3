"""
Database Schemas for Sri Raghavendra Swamy Matha app

Each Pydantic model corresponds to a MongoDB collection whose name is the lowercase of the class name.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import date

class Devoteeuser(BaseModel):
    """
    Devotee users (login for booking history)
    Collection: "devoteeuser"
    """
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    phone: Optional[str] = Field(None, description="Phone number")
    is_admin: bool = Field(False, description="Admin access flag")

class Seva(BaseModel):
    """
    Daily sevas only
    Collection: "seva"
    """
    title: str = Field(..., description="Seva name")
    description: Optional[str] = Field(None, description="Short description")
    time: str = Field(..., description="Timing, e.g., 6:30 AM")
    cost: float = Field(..., ge=0, description="Cost in INR")

class Room(BaseModel):
    """
    Room types for booking
    Collection: "room"
    """
    name: str = Field(..., description="Room/Type name")
    capacity: int = Field(..., ge=1, description="Max guests")
    price: float = Field(..., ge=0, description="Price per night in INR")
    amenities: Optional[List[str]] = Field(default_factory=list, description="Amenities list")

class Sevabooking(BaseModel):
    """
    Seva bookings
    Collection: "sevabooking"
    """
    user_email: EmailStr = Field(...)
    seva_id: str = Field(..., description="Seva document _id as string")
    date: date = Field(..., description="Seva date")
    quantity: int = Field(1, ge=1, description="Number of persons")
    amount: float = Field(..., ge=0, description="Total amount in INR")
    status: str = Field("confirmed", description="confirmed/cancelled")
    receipt_no: Optional[str] = Field(None, description="Receipt number")

class Roombooking(BaseModel):
    """
    Room bookings
    Collection: "roombooking"
    """
    user_email: EmailStr = Field(...)
    room_id: str = Field(..., description="Room document _id as string")
    check_in: date = Field(...)
    check_out: date = Field(...)
    guests: int = Field(..., ge=1)
    amount: float = Field(..., ge=0)
    status: str = Field("confirmed", description="confirmed/cancelled")
    receipt_no: Optional[str] = None

class Newspost(BaseModel):
    """
    News & announcements
    Collection: "newspost"
    """
    title: str
    content: str
    published_on: date
    tags: Optional[List[str]] = Field(default_factory=list)

class Contactmessage(BaseModel):
    """
    Enquiries from contact form
    Collection: "contactmessage"
    """
    name: str
    email: EmailStr
    phone: Optional[str] = None
    message: str
