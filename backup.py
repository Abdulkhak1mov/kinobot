"""Offline backup/restore. Never includes bot tokens or movie file bytes."""
import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from runtime import InstanceLock

REQUIRED={'users','activity','admins','movies','assets','marks','ratings','deliveries','channels','states','reports','imports','jobs','queue'}

def validate_backup(path):
    if not Path(path).is_file(): raise ValueError('Zaxira fayli topilmadi.')
    uri=Path(path).resolve().as_uri()+'?mode=ro'
    with sqlite3.connect(uri,uri=True) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Zaxira fayli buzilgan.')
        names={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED <= names: raise ValueError('Bu fayl Kino Bot zaxirasi emas.')
        if source.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Zaxirada bog‘lanish xatosi bor.')

def copy_database(source,destination):
    with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(destination) as dst:
        src.backup(dst)

def restore(source,database):
    validate_backup(source)
    if Path(source).resolve()==Path(database).resolve(): raise ValueError('Manba va maqsad bir xil bo‘lmasin.')
    Path(database).parent.mkdir(parents=True,exist_ok=True)
    with InstanceLock(database):
        previous=None
        if Path(database).is_file():
            previous=str(database)+'.before-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.db'
            copy_database(database,previous)
        copy_database(source,database)
        # Restore must not unexpectedly resend old bulk messages or resume drafts.
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE queue SET state='skipped' WHERE state IN ('pending','sending')")
            conn.execute('DELETE FROM states')
            conn.execute('UPDATE users SET pending=NULL')
    return previous

def main():
    load_dotenv()
    parser=argparse.ArgumentParser(description='Kino Bot zaxira va tiklash')
    parser.add_argument('action',choices=['backup','restore'])
    parser.add_argument('file')
    args=parser.parse_args()
    database=os.getenv('DATABASE_PATH','data/kino.db')
    if args.action=='backup':
        if Path(args.file).exists(): raise SystemExit('Maqsad fayl mavjud. Yangi fayl nomi bering.')
        if Path(args.file).resolve()==Path(database).resolve(): raise SystemExit('Boshqa fayl nomi bering.')
        copy_database(database,args.file)
        print('Zaxira saqlandi:',args.file)
    else:
        previous=restore(args.file,database)
        print('Tiklandi. Oldingi holat zaxirasi:',previous or 'mavjud emas')

if __name__=='__main__': main()
