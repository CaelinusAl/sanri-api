from sqlalchemy.orm import Session
from app.models.user import User

def get_or_create_user(db: Session, external_id: str) -> User:
    u = db.query(User).filter(User.external_id == external_id).first()
    if u:
        return u
    u = User(external_id=external_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u
