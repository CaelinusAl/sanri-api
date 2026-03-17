from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from app.db import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)

    # kullanıcı bağlantısı
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # memory tipi (kontrollü kullan)
    type = Column(String, nullable=False, default="auto")  
    # matrix | ritual | insight | system | auto

    # AI context (json data)
    context = Column(JSON, nullable=True)

    # kullanıcı input / sanrı output
    input_text = Column(Text, nullable=False)
    output_text = Column(Text, nullable=False)

    # ekstra AI alanları
    emotion = Column(String, nullable=True) # örn: "korku", "açılım"
    frequency = Column(String, nullable=True) # örn: "yumuşama", "uyanış"

    created_at = Column(DateTime(timezone=True), server_default=func.now())