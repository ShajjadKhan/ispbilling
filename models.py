from sqlalchemy import Column, Integer, String
from database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone = Column(String, unique=True, index=True)
    status = Column(String, default="active")
    package = Column(String, nullable=True)
    expiry_date = Column(String, nullable=True)
