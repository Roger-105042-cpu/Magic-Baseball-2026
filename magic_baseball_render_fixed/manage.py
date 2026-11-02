import argparse,csv,re,os,getpass
from pathlib import Path
from sqlalchemy import select
from server import Base,engine,Session,User,Student,Attendance,ph,month,eqdefault,strong
p=argparse.ArgumentParser();p.add_argument('command',choices=['init','import-csv']);p.add_argument('--file');p.add_argument('--admin',default='superadmin');a=p.parse_args();Base.metadata.create_all(engine)
if a.command=='init':
 with Session() as db:
  if db.scalar(select(User).where(User.username==a.admin)):raise SystemExit('管理者已存在')
  pwd=getpass.getpass('新管理者密碼 (至少10碼、大小寫、數字、特殊符號): ')
  if not strong(pwd):raise SystemExit('密碼強度不足')
  db.add(User(username=a.admin,name='超級管理員',password_hash=ph.hash(pwd),role='superadmin',active=True));db.commit();print('管理者建立完成')
else:
 if not a.file:raise SystemExit('請提供 --file CSV路徑')
 with open(a.file,encoding='utf-8-sig',newline='') as f,Session() as db:
  count=0
  for row in csv.DictReader(f):
   sid=row['學員ID'];phone=row['家長電話'];existing=db.get(Student,sid)
   if existing:continue
   plan='B' if 'B' in row['方案'] else 'A';start=row['購買生效日'];eq=eqdefault()
   for key,col in [('jersey','制服尺寸/領用'),('pants','球褲尺寸/領用'),('practiceShirt','練習衣尺寸/領用'),('hat','帽子發放'),('belt','皮帶發放'),('towel','毛巾發放')]:
    val=row[col];m=re.search(r'\d{4}-\d{2}-\d{2}',val);eq[key]={'size':val.split(' (')[0] if key in ('jersey','pants','practiceShirt') else '','issued':('未領' not in val and '領取' in val),'date':m.group() if m else ''}
   s=Student(id=sid,name=row['姓名'],number=row['背號'],campus=row['場域'],parentName=row['家長姓名'],parentPhone=phone,studentType='舊生',planType=plan,purchaseDate=start,expiryDate=row['到期日'],totalClasses=int(row['總堂數']),remainingClasses=int(row['剩餘堂數']),totalLeaves=4 if plan=='A' else 8,remainingLeaves=int(row['剩餘請假']),equipment=eq);db.add(s)
   # Never import plaintext passwords from CSV. Parents need an individually assigned reset password.
   if not db.scalar(select(User).where(User.username==phone)):
    import secrets
    db.add(User(username=phone,name=row['家長姓名'],password_hash=ph.hash(secrets.token_urlsafe(32)),role='parent',active=False,student_id=sid))
   count+=1
  db.commit();print('已匯入',count,'位學員；家長帳號預設停用，須另行啟用並重設密碼')
