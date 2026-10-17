from pydantic import BaseModel, EmailStr

class PostCreate(BaseModel):
    name: str
    age: int
    city: str
    email: EmailStr
    course: str
    bio: str


class PostResponse(BaseModel):
    id: int
    name: str
    age: int
    city: str
    email: EmailStr
    course: str
    bio: str