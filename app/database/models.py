import time, uuid
from sqlalchemy import BigInteger, Integer, String, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.connection import Base
def ts(): return int(time.time())
class User(Base):
    __tablename__="users"
    telegram_id: Mapped[int]=mapped_column(BigInteger,primary_key=True)
    username: Mapped[str|None]=mapped_column(String(64),nullable=True)
    first_name: Mapped[str]=mapped_column(String(128),default="")
    created_at: Mapped[int]=mapped_column(Integer,default=ts)
    blocked: Mapped[bool]=mapped_column(default=False)
    wallet: Mapped["Wallet|None"]=relationship(back_populates="user",uselist=False)
class Wallet(Base):
    __tablename__="tnc_wallets"
    __table_args__=(CheckConstraint("balance_units >= 0"),)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.telegram_id"),primary_key=True)
    balance_units: Mapped[int]=mapped_column(BigInteger,default=0)
    user: Mapped[User]=relationship(back_populates="wallet")
class Transaction(Base):
    __tablename__="tnc_transactions"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    operation_id: Mapped[str]=mapped_column(String(36),default=lambda:str(uuid.uuid4()),unique=True)
    sender_id: Mapped[int|None]=mapped_column(BigInteger,nullable=True)
    receiver_id: Mapped[int|None]=mapped_column(BigInteger,nullable=True)
    amount_units: Mapped[int]=mapped_column(BigInteger)
    kind: Mapped[str]=mapped_column(String(24),default="transfer")
    description: Mapped[str]=mapped_column(String(255),default="")
    created_at: Mapped[int]=mapped_column(Integer,default=ts)
