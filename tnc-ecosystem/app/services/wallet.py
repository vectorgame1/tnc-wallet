from decimal import Decimal, InvalidOperation
from sqlalchemy import or_, select
from app.database.models import Wallet, Transaction
UNIT=10**6
def amount_units(value):
    try: n=Decimal(str(value))
    except (InvalidOperation,ValueError): raise ValueError("Некорректная сумма.")
    if not n.is_finite() or n<=0 or n*UNIT!=(n*UNIT).to_integral_value(): raise ValueError("Сумма должна быть положительной, максимум 6 знаков после запятой.")
    if n>Decimal("1000000"): raise ValueError("Лимит одной операции — 1 000 000 TNC.")
    return int(n*UNIT)
def fmt(n): return f"{Decimal(n)/UNIT:,.6f}".replace(","," ")
def balance(db,uid):
    w=db.get(Wallet,int(uid))
    if not w: raise ValueError("Кошелёк не найден.")
    return w.balance_units
def send(db,sender,receiver,amount):
    sender=int(sender); receiver=int(receiver); units=amount_units(amount)
    if sender==receiver: raise ValueError("Нельзя отправить самому себе.")
    try:
        a=db.execute(select(Wallet).where(Wallet.user_id==sender).with_for_update()).scalar_one_or_none()
        b=db.execute(select(Wallet).where(Wallet.user_id==receiver).with_for_update()).scalar_one_or_none()
        if a is None or b is None: raise ValueError("Отправитель или получатель не найден.")
        if a.balance_units<units: raise ValueError("Недостаточно средств.")
        a.balance_units-=units; b.balance_units+=units
        tx=Transaction(sender_id=sender,receiver_id=receiver,amount_units=units,kind="transfer",description="Перевод TNC")
        db.add(tx); db.commit(); db.refresh(tx); return tx
    except Exception: db.rollback(); raise
def history(db,uid,limit=10):
    return db.execute(select(Transaction).where(or_(Transaction.sender_id==uid,Transaction.receiver_id==uid)).order_by(Transaction.id.desc()).limit(max(1,min(limit,50)))).scalars().all()
