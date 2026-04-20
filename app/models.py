from pydantic import BaseModel


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class SaveProductRequest(BaseModel):
    name: str
    hts_code: str
    description: str
    duty_rate: str
    origin: str = ""


class UpdateProfileRequest(BaseModel):
    name: str
