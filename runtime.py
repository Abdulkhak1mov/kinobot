"""Cross-platform process lock: one polling bot and one queue worker per database."""
import os
from pathlib import Path

class InstanceLock:
    def __init__(self,database_path):
        self.path=Path(str(database_path)+'.lock')
        self.file=None

    def acquire(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=open(self.path,'a+b')
        self.file.seek(0)
        if not self.file.read(1):
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as e:
            self.file.close(); self.file=None
            raise RuntimeError('Bot allaqachon ishlayapti. Avval oldingi jarayonni to‘xtating.') from e
        return self

    def release(self):
        if self.file:
            self.file.close(); self.file=None

    def __enter__(self): return self.acquire()
    def __exit__(self,*args): self.release()
