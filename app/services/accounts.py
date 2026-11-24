from app.database.models import User, Wallet


def get_or_create_user(db, data):
    uid = int(data["id"])
    user = db.get(User, uid)

    if user is None:
        user = User(
            telegram_id=uid,
            username=data.get("username"),
            first_name=(data.get("first_name") or "TNC User")[:128],
        )
        db.add(user)
        db.flush()
    else:
        if user.blocked:
            raise ValueError("Аккаунт заблокирован.")

        user.username = data.get("username")
        user.first_name = (
            data.get("first_name") or user.first_name
        )[:128]

    wallet = db.get(Wallet, uid)
    if wallet is None:
        db.add(Wallet(user_id=uid, balance_units=0))
        db.flush()

    return user