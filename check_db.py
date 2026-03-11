from sqlmodel import Session, select
from app.database import engine
from app.models import Block, SyncState

with Session(engine) as s:
    state = s.exec(select(SyncState)).first()
    print("State:", state)
    blocks = len(s.exec(select(Block)).all())
    print("Blocks in DB:", blocks)
