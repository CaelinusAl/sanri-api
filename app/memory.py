from pathlib import Path
from app.storage import MemoryStore
import app.storage as s

print("MEMORY MODULE:", _file_)
print("STORAGE MODULE:", s._file_)
print("MEMORYSTORE ATTRS:", [a for a in dir(s.MemoryStore) if "data" in a.lower()])

_store = MemoryStore(Path("data"))