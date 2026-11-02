import os,io,csv,re,secrets,hashlib,calendar
from datetime import datetime,date,timedelta,timezone
from pathlib import Path
from fastapi import FastAPI,HTTPException,Depends,Request,Response
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine,Column,String,Integer,Boolean,DateTime,ForeignKey,UniqueConstraint,select
from sqlalchemy.orm import declarative_base,sessionmaker
from sqlalchemy.types import JSON
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
P=Path(__file__).parent
if not os.getenv('DATABASE_URL'):raise RuntimeError('DATABASE_URL PostgreSQL 未設定')
engine=create_engine(os.environ['DATABASE_URL'].replace('postgres://','postgresql://',1),pool_pre_ping=True);Session=sessionmaker(engine);Base=declarative_base();ph=PasswordHasher()
def now():return datetime.now(timezone.utc)
def uid():return secrets.token_hex(12)
def digest(t):return hashlib.sha256(t.encode()).hexdigest()
def month(s,n):
 d=date.fromisoformat(s);y=d.year+(d.month-1+n)//12;m=(d.month-1+n)%12+1;return date(y,m,min(d.day,calendar.monthrange(y,m)[1])).isoformat()
def strong(p):return len(p)>=10 and all(re.search(x,p) for x in ['[A-Z]','[a-z]','[0-9]','[^A-Za-z0-9]'])
def pwcheck(p):
 if not strong(p):raise HTTPException(400,'密碼至少10碼，需含大小寫、數字及特殊符號')
class User(Base):
 __tablename__='users';id=Column(String,primary_key=True,default=uid);username=Column(String,unique=True);name=Column(String);password_hash=Column(String);role=Column(String);active=Column(Boolean,default=True);student_id=Column(String)
class Student(Base):
 __tablename__='students';id=Column(String,primary_key=True,default=uid);name=Column(String);number=Column(String);campus=Column(String);parentName=Column(String);parentPhone=Column(String);studentType=Column(String);planType=Column(String);purchaseDate=Column(String);expiryDate=Column(String);totalClasses=Column(Integer);remainingClasses=Column(Integer);totalLeaves=Column(Integer);remainingLeaves=Column(Integer);equipment=Column(JSON)
class Attendance(Base):
 __tablename__='attendance';id=Column(String,primary_key=True,default=uid);student_id=Column(String,ForeignKey('students.id'));date=Column(String);campus=Column(String);status=Column(String);note=Column(String);__table_args__=(UniqueConstraint('student_id','date'),)
class Renewal(Base):
 __tablename__='renewals';id=Column(String,primary_key=True,default=uid);student_id=Column(String,ForeignKey('students.id'));planType=Column(String);bankLast5=Column(String);requestTime=Column(String);status=Column(String);confirmTime=Column(String);prevExpiryDate=Column(String);newExpiryDate=Column(String)
class Audit(Base):
 __tablename__='audit';id=Column(String,primary_key=True,default=uid);actor=Column(String);action=Column(String);student_id=Column(String);detail=Column(String);time=Column(DateTime(timezone=True),default=now)
class SessionToken(Base):
 __tablename__='sessions';token_hash=Column(String,primary_key=True);user_id=Column(String,ForeignKey('users.id'));expires=Column(DateTime(timezone=True))
def dbdep():
 with Session() as db:yield db
def auth(request:Request,db=Depends(dbdep)):
 t=request.cookies.get('magic_session');s=db.get(SessionToken,digest(t)) if t else None
 if not s or s.expires<now():raise HTTPException(401,'請重新登入')
 u=db.get(User,s.user_id)
 if not u or not u.active:raise HTTPException(401,'帳號已停用')
 return u
def roles(u,*allowed):
 if u.role not in allowed:raise HTTPException(403,'權限不足')
def own(u,sid):
 if u.role=='parent' and u.student_id!=sid:raise HTTPException(403,'無權讀取')
def log(db,u,action,sid='',detail=''):db.add(Audit(actor=u.username,action=action,student_id=sid,detail=detail))
def eqdefault():return {k:{'size':'','issued':False,'date':''} for k in ['jersey','pants','practiceShirt','hat','belt','towel']}
def student(db,sid,lock=False):
 q=select(Student).where(Student.id==sid)
 if lock:q=q.with_for_update()
 s=db.scalar(q)
 if not s:raise HTTPException(404,'學員不存在')
 return s
def public(db,s):
 eq={**eqdefault(),**(s.equipment or {})};n=sum(bool(eq[k].get('issued')) for k in eqdefault());eq['status']='已領取' if n==6 else '部分領取' if n else '未領取'
 a=db.scalars(select(Attendance).where(Attendance.student_id==s.id).order_by(Attendance.date.desc())).all();r=db.scalars(select(Renewal).where(Renewal.student_id==s.id).order_by(Renewal.requestTime.desc())).all()
 return {**{k:getattr(s,k) for k in ['id','name','number','campus','parentName','parentPhone','studentType','planType','purchaseDate','expiryDate','totalClasses','remainingClasses','totalLeaves','remainingLeaves']},'equipment':eq,'attendanceHistory':[{k:getattr(x,k) for k in ['id','date','campus','status','note']} for x in a],'renewalRequests':[{k:getattr(x,k) for k in ['id','planType','bankLast5','requestTime','status','confirmTime','prevExpiryDate','newExpiryDate']} for x in r]}
@asynccontextmanager
async def lifespan(app):
 Base.metadata.create_all(engine)
 initial=os.getenv('BOOTSTRAP_ADMIN_PASSWORD','')
 if initial:
  if not strong(initial):raise RuntimeError('BOOTSTRAP_ADMIN_PASSWORD 密碼強度不足')
  with Session() as db:
   if not db.scalar(select(User).where(User.role=='superadmin')):
    db.add(User(username=os.getenv('BOOTSTRAP_ADMIN_USERNAME','superadmin'),name='超級管理員',password_hash=ph.hash(initial),role='superadmin',active=True));db.commit()
 yield
app=FastAPI(docs_url=None,redoc_url=None,lifespan=lifespan)
@app.middleware('http')
async def protect_mutations(request:Request,call_next):
 if request.method in ('POST','PUT','PATCH','DELETE') and request.url.path.startswith('/api/'):
  origin=request.headers.get('origin')
  if origin:
   from urllib.parse import urlparse
   host=urlparse(origin).netloc.lower()
   allowed={request.headers.get('host','').lower(),os.getenv('RENDER_EXTERNAL_HOSTNAME','').lower()}
   if host not in allowed or urlparse(origin).scheme!='https' and os.getenv('RENDER')=='true':
    return Response('Origin not allowed',status_code=403)
 return await call_next(request)
app.mount('/static',StaticFiles(directory=P/'static'),name='static')
@app.get('/healthz')
def healthz():
 with engine.connect() as conn:conn.execute(select(1))
 return {'status':'ok'}
@app.get('/')
def index():return FileResponse(P/'static'/'index.html')
class Login(BaseModel):username:str;password:str
@app.post('/api/login')
def login(p:Login,response:Response,db=Depends(dbdep)):
 u=db.scalar(select(User).where(User.username==p.username,User.active==True))
 try:
  if not u or not ph.verify(u.password_hash,p.password):raise ValueError()
 except (ValueError,VerificationError):raise HTTPException(401,'帳號或密碼錯誤')
 t=secrets.token_urlsafe(40);db.add(SessionToken(token_hash=digest(t),user_id=u.id,expires=now()+timedelta(hours=12)));db.commit();response.set_cookie('magic_session',t,httponly=True,secure=os.getenv('COOKIE_SECURE','1')=='1',samesite='lax',max_age=43200);return {'role':u.role,'name':u.name}
@app.post('/api/logout')
def logout(request:Request,response:Response,db=Depends(dbdep)):
 t=request.cookies.get('magic_session');s=db.get(SessionToken,digest(t)) if t else None
 if s:db.delete(s);db.commit()
 response.delete_cookie('magic_session');return {'ok':True}
@app.get('/api/me')
def me(u=Depends(auth)):return {'role':u.role,'name':u.name,'username':u.username}
@app.get('/api/students')
def students(db=Depends(dbdep),u=Depends(auth)):
 q=select(Student).order_by(Student.campus,Student.number)
 if u.role=='parent':q=q.where(Student.id==u.student_id)
 return [public(db,s) for s in db.scalars(q)]
class StudentIn(BaseModel):name:str;number:str='';campus:str='仁德學院';parentName:str='';parentPhone:str;password:str;studentType:str='新生';planType:str='A';purchaseDate:str;equipment:dict|None=None
@app.post('/api/students')
def addstudent(p:StudentIn,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'admin','superadmin');pwcheck(p.password)
 if not p.name.strip() or not p.parentPhone.strip():raise HTTPException(400,'請填寫學員姓名與家長手機')
 if p.planType not in ('A','B'):raise HTTPException(400,'方案錯誤')
 if db.scalar(select(User).where(User.username==p.parentPhone)):raise HTTPException(409,'家長帳號已存在，暫不支援共用手機多位學員')
 c,l,m=(11,4,4) if p.planType=='A' else (12,8,6);s=Student(name=p.name,number=p.number,campus=p.campus,parentName=p.parentName,parentPhone=p.parentPhone,studentType=p.studentType,planType=p.planType,purchaseDate=p.purchaseDate,expiryDate=month(p.purchaseDate,m),totalClasses=c,remainingClasses=c,totalLeaves=l,remainingLeaves=l,equipment={k:{'size':str((p.equipment or {}).get(k,{}).get('size',''))[:30],'issued':False,'date':''} for k in eqdefault()});db.add(s);db.flush();db.add(User(username=p.parentPhone,name=p.parentName or p.name,role='parent',password_hash=ph.hash(p.password),student_id=s.id));log(db,u,'add_student',s.id);db.commit();return {'id':s.id}
class AttendanceIn(BaseModel):date:str;status:str;note:str=''
@app.post('/api/students/{sid}/attendance')
def attendance(sid:str,p:AttendanceIn,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'admin','superadmin')
 if p.status not in ('present','leave','absent'):raise HTTPException(400,'狀態錯誤')
 s=student(db,sid,True)
 if db.scalar(select(Attendance).where(Attendance.student_id==sid,Attendance.date==p.date)):raise HTTPException(409,'當日已點名')
 k='remainingLeaves' if p.status=='leave' else 'remainingClasses'
 if getattr(s,k)<1:raise HTTPException(409,'剩餘額度不足')
 setattr(s,k,getattr(s,k)-1);db.add(Attendance(student_id=sid,date=p.date,campus=s.campus,status=p.status,note=p.note));log(db,u,'attendance',sid,p.status);db.commit();return {'ok':True}
@app.delete('/api/students/{sid}/attendance/{day}')
def cancel(sid:str,day:str,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'admin','superadmin');s=student(db,sid,True);a=db.scalar(select(Attendance).where(Attendance.student_id==sid,Attendance.date==day))
 if not a:raise HTTPException(404,'找不到紀錄')
 k='remainingLeaves' if a.status=='leave' else 'remainingClasses';setattr(s,k,getattr(s,k)+1);db.delete(a);log(db,u,'cancel_attendance',sid,day);db.commit();return {'ok':True}
class NoteIn(BaseModel):note:str
@app.patch('/api/students/{sid}/attendance/{day}')
def note(sid:str,day:str,p:NoteIn,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'admin','superadmin');a=db.scalar(select(Attendance).where(Attendance.student_id==sid,Attendance.date==day))
 if not a:raise HTTPException(404,'請先點名')
 a.note=p.note;log(db,u,'note',sid);db.commit();return {'ok':True}
class EquipmentIn(BaseModel):equipment:dict
@app.put('/api/students/{sid}/equipment')
def equipment(sid:str,p:EquipmentIn,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'admin','superadmin');s=student(db,sid,True);s.equipment={k:{'size':str(p.equipment.get(k,{}).get('size','')),'issued':bool(p.equipment.get(k,{}).get('issued',False)),'date':str(p.equipment.get(k,{}).get('date',''))} for k in eqdefault()};log(db,u,'equipment',sid);db.commit();return {'ok':True}
class Balance(BaseModel):remainingClasses:int;remainingLeaves:int;reason:str=''
@app.patch('/api/students/{sid}/balance')
def balance(sid:str,p:Balance,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'superadmin')
 if min(p.remainingClasses,p.remainingLeaves)<0:raise HTTPException(400,'不可為負數')
 s=student(db,sid,True);s.remainingClasses=p.remainingClasses;s.remainingLeaves=p.remainingLeaves;log(db,u,'adjust_balance',sid,p.reason);db.commit();return {'ok':True}
class RenewalIn(BaseModel):planType:str;bankLast5:str
@app.post('/api/students/{sid}/renewals')
def renewal(sid:str,p:RenewalIn,db=Depends(dbdep),u=Depends(auth)):
 own(u,sid)
 if p.planType not in ('A','B') or not re.fullmatch('[0-9]{5}',p.bankLast5):raise HTTPException(400,'輸入不正確')
 s=student(db,sid,True)
 if db.scalar(select(Renewal).where(Renewal.student_id==sid,Renewal.status=='pending')):raise HTTPException(409,'已有待審核續約')
 db.add(Renewal(student_id=sid,planType=p.planType,bankLast5=p.bankLast5,requestTime=now().isoformat(),status='pending',confirmTime='',prevExpiryDate=s.expiryDate,newExpiryDate=month(s.expiryDate,4 if p.planType=='A' else 6)));log(db,u,'renewal_request',sid);db.commit();return {'ok':True}
@app.post('/api/renewals/{rid}/approve')
def approve(rid:str,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'superadmin');r=db.scalar(select(Renewal).where(Renewal.id==rid).with_for_update())
 if not r or r.status!='pending':raise HTTPException(409,'無待審核資料')
 s=student(db,r.student_id,True);c,l,m=(11,4,4) if r.planType=='A' else (12,8,6);r.prevExpiryDate=s.expiryDate;r.newExpiryDate=month(s.expiryDate,m);s.expiryDate=r.newExpiryDate;s.planType=r.planType;s.totalClasses+=c;s.remainingClasses+=c;s.totalLeaves+=l;s.remainingLeaves+=l;r.status='approved';r.confirmTime=now().isoformat();log(db,u,'approve_renewal',s.id);db.commit();return {'ok':True}
class PasswordIn(BaseModel):oldPassword:str;newPassword:str
@app.post('/api/password')
def password(p:PasswordIn,db=Depends(dbdep),u=Depends(auth)):
 pwcheck(p.newPassword)
 try:ph.verify(u.password_hash,p.oldPassword)
 except VerificationError:raise HTTPException(400,'舊密碼錯誤')
 u.password_hash=ph.hash(p.newPassword);log(db,u,'change_password');db.commit();return {'ok':True}
class AdminIn(BaseModel):username:str;name:str;password:str
@app.get('/api/admins')
def admins(db=Depends(dbdep),u=Depends(auth)):
 roles(u,'superadmin');return [{'id':x.id,'username':x.username,'name':x.name,'active':x.active} for x in db.scalars(select(User).where(User.role=='admin'))]
@app.post('/api/admins')
def addadmin(p:AdminIn,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'superadmin');pwcheck(p.password)
 if db.scalar(select(User).where(User.username==p.username)):raise HTTPException(409,'帳號已存在')
 db.add(User(username=p.username,name=p.name,role='admin',password_hash=ph.hash(p.password),active=True));log(db,u,'add_admin',detail=p.username);db.commit();return {'ok':True}
@app.patch('/api/admins/{aid}/toggle')
def toggle(aid:str,db=Depends(dbdep),u=Depends(auth)):
 roles(u,'superadmin');a=db.get(User,aid)
 if not a or a.role!='admin':raise HTTPException(404,'帳號不存在')
 a.active=not a.active;log(db,u,'toggle_admin',detail=a.username);db.commit();return {'ok':True}
@app.get('/api/export.xlsx')
def export(db=Depends(dbdep),u=Depends(auth)):
 roles(u,'admin','superadmin')
 from openpyxl import Workbook
 w=Workbook();w.remove(w.active)
 for name,model,fields in [('學員名冊',Student,['id','name','number','campus','parentName','parentPhone','studentType','planType','purchaseDate','expiryDate','totalClasses','remainingClasses','totalLeaves','remainingLeaves']),('點名紀錄',Attendance,['student_id','date','campus','status','note']),('續約紀錄',Renewal,['student_id','planType','bankLast5','requestTime','status','confirmTime','prevExpiryDate','newExpiryDate'])]:
  sh=w.create_sheet(name);sh.append(fields)
  for x in db.scalars(select(model)):sh.append([getattr(x,k) for k in fields])
 sh=w.create_sheet('裝備領用');sh.append(['學員ID','項目','尺寸','已領取','日期'])
 for s in db.scalars(select(Student)):
  for k,v in (s.equipment or {}).items():sh.append([s.id,k,v.get('size',''),v.get('issued',False),v.get('date','')])
 b=io.BytesIO();w.save(b);b.seek(0);return StreamingResponse(b,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="magic_baseball.xlsx"'})
