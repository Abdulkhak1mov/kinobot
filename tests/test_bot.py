import asyncio
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest,TelegramForbiddenError,TelegramRetryAfter
from aiogram.methods import GetChatMember,SendMessage,SendVideo,SendPhoto,SendDocument,CopyMessage,AnswerCallbackQuery
from aiogram.types import ChatMemberMember,ChatMemberLeft,Message,Update,User,Chat

from bot import App,Guard
from core import allowed,code_value,is_member,parse_channel_caption,validate,SELECTED
from storage import Store
from runtime import InstanceLock
from backup import restore,validate_backup

def movie(code='101',kind='movie',title='Sinov kinosi'):
    return dict(code=code,title=title,kind=kind,genre='Komediya',year=2024,country='O‘zbekiston',
                description='Sinov tavsifi',duration=100,poster='',trailer='')

def asset(**kw):
    return dict(language='O‘zbekcha',quality='720p',season=0,episode=0,file_id='video-file-id',media_type='video')|kw

class CoreTests(unittest.TestCase):
    def test_selection_has_41_unique_features(self):
        self.assertEqual(len(SELECTED),41); self.assertEqual(len(set(SELECTED)),41)
    def test_code_normalizes_and_rejects_unsafe_input(self):
        self.assertEqual(code_value(' ab-12 '),'AB-12')
        for value in ('','x'*33,"101';DROP TABLE users;--",'salom dunyo','кино'):
            with self.assertRaises(ValueError): code_value(value)
    def test_fields(self):
        self.assertEqual(validate('year','2024'),2024)
        self.assertEqual(validate('year','/skip'),0)
        self.assertEqual(validate('kind','serial'),'series')
        for field,val in [('year','999'),('season','0'),('duration','-1'),('trailer','javascript:alert(1)'),('genre','x'*41)]:
            with self.assertRaises(ValueError): validate(field,val)
    def test_membership_real_enum_and_restricted(self):
        for status in (ChatMemberStatus.MEMBER,ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.CREATOR):
            self.assertTrue(is_member(SimpleNamespace(status=status)))
        for status in (ChatMemberStatus.LEFT,ChatMemberStatus.KICKED):
            self.assertFalse(is_member(SimpleNamespace(status=status)))
        self.assertTrue(is_member(SimpleNamespace(status=ChatMemberStatus.RESTRICTED,is_member=True)))
        self.assertFalse(is_member(SimpleNamespace(status=ChatMemberStatus.RESTRICTED,is_member=False)))
    def test_permissions(self):
        self.assertTrue(allowed('editor','catalog'))
        self.assertFalse(allowed('editor','broadcast'))
        self.assertFalse(allowed('manager','admins'))
        self.assertFalse(allowed('manager','backup'))
        self.assertTrue(allowed('owner','backup'))
        self.assertFalse(allowed('','catalog'))
    def test_caption_parser(self):
        data=parse_channel_caption('#kino\ncode: 001\ntitle: Sinov\nkind: movie\nlanguage: Uzbek\nquality: 720p')
        self.assertEqual(data['code'],'001'); self.assertEqual(data['season'],0)
        self.assertIsNone(parse_channel_caption('Oddiy post'))
        for cap in ('#kino\ncode: 1','#kino\ncode:1\ncode:2','#kino\nwrong:1'):
            with self.assertRaises(ValueError): parse_channel_caption(cap)
        with self.assertRaises(ValueError):
            parse_channel_caption('#kino\ncode:1\ntitle:Test\nkind:series\nlanguage:Uz\nquality:720p')

class StorageTests(unittest.TestCase):
    def setUp(self): self.db=Store(':memory:'); self.db.touch(1); self.db.touch(2)
    def tearDown(self): self.db.close()
    def test_movie_and_asset_atomic(self):
        mid=self.db.create_with_asset(movie(),asset())
        self.assertEqual(self.db.movie(mid)['code'],'101')
        with self.assertRaises(ValueError): self.db.create_with_asset(movie(),asset())
        with self.assertRaises(ValueError): self.db.create_with_asset(movie('102','series'),asset())
        self.assertIsNone(self.db.by_code('102',False))
    def test_duplicate_code_cannot_overwrite(self):
        self.db.create_movie(movie())
        with self.assertRaises(sqlite3.IntegrityError): self.db.create_movie(movie(title='Boshqa kino'))
        self.assertEqual(self.db.by_code('101')['title'],'Sinov kinosi')
    def test_unique_variants_and_deletion_cascade(self):
        mid=self.db.create_with_asset(movie(),asset())
        with self.assertRaises(sqlite3.IntegrityError): self.db.add_asset(mid,asset())
        self.db.add_asset(mid,asset(language='Ruscha'))
        self.db.mark(1,mid,'favorite')
        self.db.run('INSERT INTO ratings VALUES(?,?,?)',(1,mid,5))
        self.db.run('DELETE FROM movies WHERE id=?',(mid,))
        self.assertFalse(self.db.all('SELECT * FROM assets'))
        self.assertFalse(self.db.all('SELECT * FROM marks'))
        self.assertFalse(self.db.all('SELECT * FROM ratings'))
    def test_hidden_movie_not_public(self):
        mid=self.db.create_movie(movie()); self.db.run('UPDATE movies SET hidden=1 WHERE id=?',(mid,))
        self.assertIsNone(self.db.movie(mid)); self.assertIsNone(self.db.by_code('101'))
        self.assertIsNotNone(self.db.movie(mid,False))
    def test_marks_toggle_and_rating_upsert(self):
        mid=self.db.create_movie(movie())
        for kind in ('favorite','later','follow'):
            self.assertTrue(self.db.mark(1,mid,kind)); self.assertFalse(self.db.mark(1,mid,kind))
        self.db.run('INSERT INTO ratings VALUES(?,?,?)',(1,mid,4))
        self.db.run('INSERT INTO ratings VALUES(?,?,?) ON CONFLICT(user_id,movie_id) DO UPDATE SET score=excluded.score',(1,mid,2))
        self.assertEqual(self.db.one('SELECT * FROM ratings')['score'],2)
    def test_daily_activity_is_unique(self):
        self.db.touch(1); self.db.touch(1)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM activity')['n'],2)
    def test_broadcast_excludes_optout_and_blocked(self):
        self.db.touch(3); self.db.run('UPDATE users SET notifications=0 WHERE id=2'); self.db.run('UPDATE users SET blocked=1 WHERE id=3')
        jid=self.db.broadcast(1,55,1)
        self.assertEqual([r['user_id'] for r in self.db.all('SELECT * FROM queue WHERE job_id=?',(jid,))],[1])
    def test_episode_notification_only_once_per_episode(self):
        mid=self.db.create_movie(movie(kind='series')); self.db.mark(1,mid,'follow'); self.db.mark(2,mid,'follow')
        self.db.run('UPDATE users SET notifications=0 WHERE id=2')
        self.db.add_asset(mid,asset(season=1,episode=1))
        self.db.add_asset(mid,asset(season=1,episode=1,quality='1080p'))
        self.assertEqual(len(self.db.all('SELECT * FROM queue')),1)
        self.db.add_asset(mid,asset(season=1,episode=2))
        self.assertEqual(len(self.db.all('SELECT * FROM queue')),2)
    def test_import_idempotent_and_rolls_back(self):
        data=movie()|asset()
        mid=self.db.import_post(-100,5,data)
        self.assertEqual(mid,1); self.assertIsNone(self.db.import_post(-100,5,data))
        with self.assertRaises(ValueError): self.db.import_post(-100,6,data|{'title':'Boshqa'})
        with self.assertRaises(sqlite3.IntegrityError): self.db.import_post(-100,7,data)
        self.assertEqual(len(self.db.all('SELECT * FROM imports')),1)
    def test_persisted_state(self):
        self.db.set_state(1,{'type':'new','data':{'title':'O‘zbekcha'}})
        self.assertEqual(self.db.state(1)['data']['title'],'O‘zbekcha')
        self.db.set_state(1,None); self.assertIsNone(self.db.state(1))
    def test_backup_restore_and_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.db'; backup=Path(temp)/'saved.db'; target=Path(temp)/'target.db'
            db=Store(source); db.touch(1); db.create_movie(movie()); db.broadcast(1,10,1); db.backup(backup); db.close()
            validate_backup(backup)
            restore(backup,target)
            result=Store(target)
            self.assertIsNotNone(result.by_code('101'))
            self.assertEqual(result.one('SELECT state FROM queue')['state'],'skipped'); result.close()
            with InstanceLock(target):
                with self.assertRaises(RuntimeError): restore(backup,target)
            previous=restore(backup,target)
            self.assertTrue(Path(previous).is_file())

class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=Store(':memory:'); self.db.touch(1); self.db.touch(2)
        self.bot=SimpleNamespace(id=123,
            send_message=AsyncMock(),send_video=AsyncMock(),send_document=AsyncMock(),send_photo=AsyncMock(),
            copy_message=AsyncMock(),get_chat_member=AsyncMock(return_value=SimpleNamespace(status=ChatMemberStatus.MEMBER)))
        self.app=App(self.bot,self.db,{1}); self.app.username='test_bot'
        self.mid=self.db.create_with_asset(movie(),asset())
    async def asyncTearDown(self): self.db.close()
    def msg(self,uid=1,text='',**kw):
        return SimpleNamespace(from_user=SimpleNamespace(id=uid),text=text,photo=None,video=None,document=None,
                               animation=None,chat=SimpleNamespace(id=uid),message_id=7,media_group_id=None,**kw)
    async def callback(self,data,uid=2):
        await self.app.callback(SimpleNamespace(from_user=SimpleNamespace(id=uid),data=data,answer=AsyncMock()))
    async def test_code_delivers_and_records_only_success(self):
        await self.app.open_code(2,'101')
        self.bot.send_video.assert_awaited_once()
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM deliveries')['n'],1)
        self.bot.send_video.side_effect=TelegramBadRequest(method=SendVideo(chat_id=2,video='x'),message='bad file')
        await self.app.open_code(2,'101')
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM deliveries')['n'],1)
    async def test_hidden_asset_direct_callback_blocked(self):
        self.db.run('UPDATE movies SET hidden=1 WHERE id=?',(self.mid,))
        await self.app.send_asset(2,1)
        self.bot.send_video.assert_not_awaited()
    async def test_membership_pending_and_resume(self):
        self.db.run('INSERT INTO channels(chat_id,title,url,required) VALUES(?,?,?,1)',(-100,'Kanal','https://t.me/test'))
        self.bot.get_chat_member.return_value=SimpleNamespace(status=ChatMemberStatus.LEFT)
        await self.app.open_code(2,'101')
        self.bot.send_video.assert_not_awaited()
        self.assertEqual(self.db.one('SELECT pending FROM users WHERE id=2')['pending'],f'open:{self.mid}')
        self.bot.get_chat_member.return_value=SimpleNamespace(status=ChatMemberStatus.MEMBER)
        await self.callback('check')
        self.bot.send_video.assert_awaited_once()
        self.assertIsNone(self.db.one('SELECT pending FROM users WHERE id=2')['pending'])
    async def test_membership_fails_closed_on_api_error(self):
        self.db.run('INSERT INTO channels(chat_id,title,url,required) VALUES(?,?,?,1)',(-100,'Kanal','https://t.me/test'))
        self.bot.get_chat_member.side_effect=TelegramBadRequest(method=GetChatMember(chat_id=-100,user_id=2),message='forbidden')
        await self.app.send_asset(2,1)
        self.bot.send_video.assert_not_awaited()
    async def test_all_required_channels_checked(self):
        for i in (1,2): self.db.run('INSERT INTO channels(chat_id,title,url,required) VALUES(?,?,?,1)',(-100-i,'Kanal','https://t.me/test'))
        self.bot.get_chat_member.side_effect=[SimpleNamespace(status=ChatMemberStatus.MEMBER),SimpleNamespace(status=ChatMemberStatus.LEFT)]
        self.assertFalse(await self.app.gate(2,'asset:1'))
        self.assertEqual(self.bot.get_chat_member.await_count,2)
    async def test_forged_admin_callback_denied(self):
        await self.callback('a:delete_yes:1')
        self.assertIsNotNone(self.db.movie(1))
    async def test_role_revoked_during_workflow(self):
        self.db.run('INSERT INTO admins VALUES(?,?)',(2,'editor'))
        await self.app.admin_action(2,['add'])
        self.assertIsNotNone(self.db.state(2))
        self.db.run('DELETE FROM admins WHERE user_id=2')
        await self.app.message(self.msg(uid=2,text='200'))
        self.assertIsNone(self.db.state(2))
        self.assertIsNone(self.db.by_code('200'))
    async def test_editor_cannot_broadcast_or_backup(self):
        self.db.run('INSERT INTO admins VALUES(?,?)',(2,'editor'))
        await self.app.admin_action(2,['broadcast'])
        self.assertIsNone(self.db.state(2))
        await self.app.admin_action(2,['backup'])
        self.bot.send_document.assert_not_awaited()
    async def test_broadcast_confirmation_consumed_once(self):
        self.db.set_state(1,{'type':'broadcast_confirm','permission':'broadcast','chat_id':1,'message_id':10})
        await self.app.admin_action(1,['broadcast_send','10']); await self.app.admin_action(1,['broadcast_send','10'])
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM jobs')['n'],1)
    async def test_old_broadcast_button_cannot_send_new_draft(self):
        self.db.set_state(1,{'type':'broadcast_confirm','permission':'broadcast','chat_id':1,'message_id':20})
        await self.app.admin_action(1,['broadcast_send','10'])
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM jobs')['n'],0)
    async def test_deleted_movie_ids_never_reused(self):
        self.db.run('DELETE FROM movies WHERE id=?',(self.mid,))
        new=self.db.create_with_asset(movie('999'),asset())
        self.assertGreater(new,self.mid)
        await self.app.send_asset(2,1)
        self.bot.send_video.assert_not_awaited()
    async def test_worker_retries_rate_limits_and_network_errors(self):
        jid=self.db.broadcast(1,55,1)
        self.db.run('DELETE FROM queue WHERE user_id!=2')
        self.bot.copy_message.side_effect=TelegramRetryAfter(method=CopyMessage(chat_id=2,from_chat_id=1,message_id=55),message='slow',retry_after=0)
        worker=asyncio.create_task(self.app.queue_worker())
        await asyncio.sleep(.02)
        worker.cancel()
        with self.assertRaises(asyncio.CancelledError): await worker
        row=self.db.one('SELECT * FROM queue WHERE job_id=?',(jid,))
        self.assertEqual(row['state'],'pending'); self.assertGreater(row['next_at'],0)
        self.db.run('UPDATE queue SET next_at=0')
        self.bot.copy_message.side_effect=OSError('offline')
        worker=asyncio.create_task(self.app.queue_worker())
        await asyncio.sleep(.02); worker.cancel()
        with self.assertRaises(asyncio.CancelledError): await worker
        row=self.db.one('SELECT * FROM queue WHERE job_id=?',(jid,))
        self.assertEqual(row['state'],'pending'); self.assertEqual(row['attempts'],1)
    async def test_worker_marks_blocked_telegram_recipient_unreachable(self):
        self.db.broadcast(1,55,1); self.db.run('DELETE FROM queue WHERE user_id!=2')
        self.bot.copy_message.side_effect=TelegramForbiddenError(method=CopyMessage(chat_id=2,from_chat_id=1,message_id=55),message='blocked')
        worker=asyncio.create_task(self.app.queue_worker())
        await asyncio.sleep(.02); worker.cancel()
        with self.assertRaises(asyncio.CancelledError): await worker
        self.assertEqual(self.db.one('SELECT state FROM queue')['state'],'failed')
        self.assertEqual(self.db.one('SELECT reachable FROM users WHERE id=2')['reachable'],0)
    async def test_queue_rechecks_optout_block_and_hidden(self):
        row={'kind':'broadcast','user_id':2,'payload':json.dumps({'chat_id':1,'message_id':5,'creator':1})}
        self.db.run('UPDATE users SET notifications=0 WHERE id=2')
        self.assertEqual(await self.app.queue_item(row),'skipped')
        self.bot.copy_message.assert_not_awaited()
        self.db.run('UPDATE users SET notifications=1,blocked=1 WHERE id=2')
        self.assertEqual(await self.app.queue_item(row),'skipped')
        self.db.run('UPDATE users SET blocked=0 WHERE id=2')
        self.assertEqual(await self.app.queue_item(row),'sent')
        self.bot.copy_message.assert_awaited_once()
    async def test_catalog_filters_lists_and_pagination(self):
        for n in range(10): self.db.create_movie(movie(str(200+n)))
        self.db.mark(2,self.mid,'favorite'); self.db.mark(2,self.mid,'later')
        for mode in ('all','top','series','genre','year','country','favorite','later','history'):
            await self.app.listing(2,mode,self.mid,0)
        for field in ('genre','year','country'): await self.app.filters(2,field,0)
        await self.app.listing(2,'all',0,0)
        rows=self.bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard
        self.assertTrue(any('Keyingi' in b.text for row in rows for b in row))
    async def test_serial_seasons_episodes_languages_quality(self):
        mid=self.db.create_with_asset(movie('300','series'),asset(season=1,episode=1))
        self.db.add_asset(mid,asset(season=1,episode=1,language='Russian',quality='1080p'))
        await self.app.play(2,mid); await self.app.episodes(2,mid,1,0); await self.app.variants(2,mid,1,1,0)
        rows=self.bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard
        self.assertIn('Russian · 1080p',[b.text for row in rows for b in row])
    async def test_wizard_creates_full_movie(self):
        await self.app.admin_action(1,['add'])
        for value in ['777','Yangi kino','movie','Drama','2020','AQSH','Tavsif','120','/skip','/skip','Uzbek','720p']:
            await self.app.message(self.msg(text=value))
        m=self.msg(); m.video=SimpleNamespace(file_id='fresh-file')
        await self.app.message(m)
        self.assertIsNotNone(self.db.by_code('777'))
        self.assertIsNone(self.db.state(1))
    async def test_caption_import_requires_configured_source(self):
        m=SimpleNamespace(chat=SimpleNamespace(id=-100),message_id=10,text=None,caption='#kino\ncode:555\ntitle:Channel kino\nkind:movie\nlanguage:Uzbek\nquality:720p',video=SimpleNamespace(file_id='import-file'),document=None)
        await self.app.channel_post(m)
        self.assertIsNone(self.db.by_code('555'))
        self.db.run('INSERT INTO channels(chat_id,title,url,source) VALUES(?,?,?,1)',(-100,'Source','https://t.me/test'))
        await self.app.channel_post(m); await self.app.channel_post(m)
        self.assertIsNotNone(self.db.by_code('555'))
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM imports')['n'],1)
    async def test_settings_rating_report_and_stats(self):
        await self.callback('notify')
        self.assertEqual(self.db.one('SELECT notifications FROM users WHERE id=2')['notifications'],0)
        await self.callback('vote:1:5'); await self.callback('vote:1:3')
        self.assertEqual(self.db.one('SELECT score FROM ratings')['score'],3)
        await self.callback('report:1'); await self.app.message(self.msg(uid=2,text='Video ishlamayapti'))
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM reports')['n'],1)
        await self.app.stats(1); await self.app.stats(1,1)
    async def test_guard_blocks_user_and_flood(self):
        guard=Guard(self.app); handler=AsyncMock()
        m=Message(message_id=1,date=datetime.now(timezone.utc),chat=Chat(id=2,type='private'),from_user=User(id=2,is_bot=False,first_name='Test'),text='101')
        self.db.run('UPDATE users SET blocked=1 WHERE id=2')
        # Use a real bound bot for Message.answer in this middleware branch.
        session=FakeSession(); real_bot=Bot('123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk',session=session)
        m=m.as_(real_bot)
        await guard(handler,m,{})
        handler.assert_not_awaited()
        self.db.run('UPDATE users SET blocked=0 WHERE id=2')
        for _ in range(20): await guard(handler,m,{})
        self.assertLessEqual(handler.await_count,8)
        await real_bot.session.close()

class FakeSession(BaseSession):
    def __init__(self): super().__init__(); self.methods=[]
    async def close(self): pass
    async def stream_content(self,*args,**kwargs):
        yield b''
    async def make_request(self,bot,method,timeout=None):
        self.methods.append(method)
        if isinstance(method,AnswerCallbackQuery): return True
        if isinstance(method,GetChatMember): return ChatMemberMember(user=User(id=method.user_id,is_bot=False,first_name='Test'))
        if isinstance(method,CopyMessage):
            from aiogram.types import MessageId
            return MessageId(message_id=len(self.methods))
        if isinstance(method,(SendMessage,SendVideo,SendPhoto,SendDocument)):
            return Message(message_id=len(self.methods),date=datetime.now(timezone.utc),chat=Chat(id=int(method.chat_id),type='private'),text=getattr(method,'text',None))
        raise AssertionError(type(method).__name__)

class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_dispatcher_deeplink_and_admin_route(self):
        session=FakeSession(); bot=Bot('123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk',session=session)
        db=Store(':memory:'); db.create_with_asset(movie(),asset()); app=App(bot,db,{1}); app.username='test_bot'
        for i,(uid,text) in enumerate([(2,'/start film_101'),(1,'/admin')],1):
            msg=Message(message_id=i,date=datetime.now(timezone.utc),chat=Chat(id=uid,type='private'),from_user=User(id=uid,is_bot=False,first_name='Test'),text=text)
            await app.dp.feed_update(bot,Update(update_id=i,message=msg))
        self.assertTrue(any(isinstance(m,SendVideo) for m in session.methods))
        self.assertTrue(any(isinstance(m,SendMessage) and 'Admin panel' in m.text for m in session.methods))
        self.assertEqual(db.one('SELECT COUNT(*) n FROM deliveries')['n'],1)
        db.close(); await bot.session.close()

if __name__=='__main__': unittest.main()
