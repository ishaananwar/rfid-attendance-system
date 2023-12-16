import os
import pytz
import requests
from dotenv import load_dotenv
from flask import Flask, request, render_template, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, and_
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Length
from flask_security import Security, SQLAlchemyUserDatastore, current_user, uia_username_mapper, roles_accepted, hash_password
from flask_security.models import fsqla_v3 as fsqla
from datetime import datetime

app = Flask(__name__)
load_dotenv()
newUID = 0

#———————————————————— Config ————————————————————#

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT')
app.config['SECURITY_USERNAME_ENABLE'] = True
app.config['SECURITY_USER_IDENTITY_ATTRIBUTES'] = [{'username': {'mapper': uia_username_mapper}}]
app.config['SECURITY_POST_LOGIN_VIEW'] = '/attendances'
app.config['REMEMBER_COOKIE_SAMESITE'] = "strict"
app.config['SESSION_COOKIE_SAMESITE'] = "strict"
app.config['WTF_CSRF_ENABLED'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
}

db = SQLAlchemy(app)
fsqla.FsModels.set_db_info(db)

#———————————————————— Model ————————————————————#

db.metadata.clear()

class Student(db.Model):
    id = db.Column(db.Integer(), primary_key=True, autoincrement=False)
    fname = db.Column(db.String(20), unique=False, nullable=False)
    lname = db.Column(db.String(20), unique=False, nullable=True)
    grade = db.Column(db.Integer(), unique=False, nullable=False)
    sec = db.Column(db.String(1), unique = False, nullable = False)
    attendance = db.relationship('Attendance', back_populates='student')

    def to_dict(self):
        return {
            'id': self.id,
            'fname': self.fname,
            'lname': self.lname,
            'grade': self.grade,
            'sec': self.sec
        }

class Attendance(db.Model):
    rowid = db.Column(db.BigInteger(), primary_key=True, autoincrement=True)
    id = db.Column(db.Integer(), db.ForeignKey('student.id', ondelete='cascade', onupdate='cascade'), unique=False, nullable=False, autoincrement=False)
    date = db.Column(db.String(10), unique=False, nullable=False)
    time = db.Column(db.String(10), unique=False, nullable=False)
    type = db.Column(db.String(3), db.CheckConstraint("type = 'IN' OR type = 'OUT'"), unique=False, nullable=False)
    student = db.relationship('Student', back_populates='attendance')

    def to_dict(self):
        return {
            'id': self.id,
            'fname': self.student.fname,
            'lname': self.student.lname,
            'grade': self.student.grade,
            'sec': self.student.sec,
            'date': str(self.date),
            'time': str(self.time),
            'type': self.type
        }

class RolesUsers(db.Model):
    __tablename__ = 'roles_users'
    id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
    user_id = db.Column("user_id", db.Integer(), db.ForeignKey("user.id", ondelete="cascade"))
    role_id = db.Column("role_id", db.Integer(), db.ForeignKey("role.id"))
    username = db.Column(db.String(255), unique=True, nullable=True)
    role = db.Column(db.String(10), nullable=True)
    password = db.Column(db.String(1), nullable=True)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'username': self.username,
            'role': self.role,
            'password': self.password
        }

class Role(db.Model, fsqla.FsRoleMixin):
    __tablename__ = 'role'
    id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
    name = db.Column(db.String(10), unique=True)
    description = db.Column(db.String(255))

class User(db.Model, fsqla.FsUserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)
    active = db.Column(db.Boolean(), nullable=False)
    fs_uniquifier = db.Column(db.String(255), unique=True, nullable=False)
    roles = db.relationship('Role', secondary='roles_users', backref=db.backref('users', lazy='dynamic'))

user_datastore = SQLAlchemyUserDatastore(db, User, Role)
app.security = Security(app, user_datastore)

#———————————————————— Forms ————————————————————#

class AddStudent(FlaskForm):
    id = IntegerField('UID', validators=[DataRequired()], render_kw={'id': 'uid', 'readonly': False, 'placeholder': 'Please scan tag'})
    fname = StringField('First Name', validators=[DataRequired()])
    lname = StringField('Last Name')
    grade = IntegerField('Class', validators=[DataRequired(), NumberRange(min=1, max=12)])
    sec = StringField('Section', validators=[DataRequired(), Length(min=1, max=1)])
    submit = SubmitField('Add Student')

#———————————————————— Views ————————————————————#

@app.route('/')
def home():
    return redirect('/login')

@app.route('/attendances', methods=['GET'])
@roles_accepted('admin', 'viewer')
def attendances():
    return render_template('attendances.html', username = current_user.username, role = str(current_user.roles[0]))

@app.route('/attendances/data', methods=['GET', 'POST'])
def attendancedata():
    try:
        query = Attendance.query
        cols = ['id', 'fname', 'lname', 'grade', 'sec', 'date', 'time', 'type']

        search = request.args.get('search[value]')
        if search:
            query = query.filter(db.or_(
                Attendance.id.like(f'%{search}%'),
                Student.fname.like(f'%{search}%'),
                Student.lname.like(f'%{search}%'),
                Student.grade.like(f'%{search}%'),
                Student.sec.like(f'%{search}%'),
                Attendance.date.like(f'%{search}%'),
                Attendance.time.like(f'%{search}%'),
                Attendance.type.like(f'%{search}%')
            ))
        filtered = query.count()
    
        query = Sort(query, Attendance, cols)
        query = Pageinate(query)

        return jsonify({
            'data': [attendance._asdict() for attendance in query],
            'recordsFiltered': filtered,
            'recordsTotal': Attendance.query.count(),
            'draw': request.args.get('draw', type=int)
        })
    
    except Exception as e:
        print(str(e))
        return str(e)

@app.route('/attendances/upload', methods=['POST'])
def attendanceupload():
    try:
        uid = request.get_json()['id']
        print(uid)
        
        out=db.session.query(Attendance.type).filter(and_(Attendance.id==uid, Attendance.date==datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d'))).order_by(desc(Attendance.time)).first()

        if out == None or out[0] == 'OUT':
            t = 'IN'
        elif out[0] == 'IN':
            t = 'OUT'

        try:
            new = Attendance(
                id=uid,
                type=t,
                date=str(datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d')),
                time=str(datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S'))
            )
            db.session.add(new)
            db.session.commit()
            return '', 204
        except:
            with open('unknown.log', 'a') as f:
                f.write(f"Unknown tag {uid} was scanned on {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d')} at {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}\n")
            return('', 203)

    except Exception as e:
        print(str(e))
        return str(e)

@app.route('/students', methods=['GET'])
@roles_accepted('admin')
def students():
    return render_template('students.html', username = current_user.username)

@app.route('/students/data', methods=['GET', 'POST'])
def studentdata():
    try:
        query = Student.query
        cols = ['id', 'fname', 'lname', 'grade', 'sec']

        search = request.args.get('search[value]')
        if search:
            query = query.filter(db.or_(
                Student.fname.like(f'%{search}%'),
                Student.lname.like(f'%{search}%'),
                Student.grade.like(f'%{search}%'),
                Student.sec.like(f'%{search}%')
            ))
        filtered = query.count()

        query = Sort(query, Student, cols)
        query = Pageinate(query)

        return jsonify({
            'data': [student.to_dict() for student in query],
            'recordsFiltered': filtered,
            'recordsTotal': Student.query.count(),
            'draw': request.args.get('draw', type=int)
        })

    except Exception as e:
        print(str(e))
        return str(e)
    
@app.route('/students/add', methods=['GET', 'POST'])
def studentadd():
    global newUID
    form = AddStudent()
    if request.method == 'POST':
        if form.validate_on_submit():
            newUID = form.id.data
            fname = form.fname.data
            lname = form.lname.data
            grade = form.grade.data
            sec = form.sec.data
            new = Student(id=newUID, fname=fname, lname=lname, grade=grade, sec=sec)
            db.session.add(new)
            db.session.commit()
            newUID = 0
            return redirect(url_for('students'))
        elif not form.validate_on_submit():
            print('false')
            print(form.errors)
            return redirect(url_for('students'))
        
    elif request.method == 'GET':
        requests.post('http://192.168.184.30/')
        return render_template('addstudent.html', form=form)

@app.route('/students/add/getuid', methods=['GET', 'POST'])
def studentgetuid():
    global newUID
    if request.method == 'POST':
        newUID = request.get_json()['id']
        return '', 204
    elif request.method == 'GET':
        return jsonify({'id': newUID})

@app.route('/students/edit', methods=['GET'])
def studentedit():
    try:
        stuid = request.args.get('id')
        fname = request.args.get('fname')
        lname = request.args.get('lname')
        grade = request.args.get('grade')
        sec = request.args.get('sec')
        target = Student.query.filter_by(id=stuid).first()
        target.fname = fname
        target.lname = lname
        target.grade = grade
        target.sec = sec
        db.session.commit()
        return jsonify({
            'data': target.to_dict()
        })
    except Exception as e:
        print(e)
        return redirect(url_for('students'))
    
@app.route('/students/delete', methods=['GET'])
def studentdeletedelete():
    try:
        stuid = request.args.get('id')
        target = Student.query.filter_by(id=stuid).first()
        Student.query.filter_by(id=stuid).delete()
        db.session.commit()
        return jsonify({
            'data': target.to_dict()
        })
    except Exception as e:
        print(e)
        return redirect(url_for('students'))

@app.route('/users', methods=['GET'])
@roles_accepted('admin')
def users():
    return render_template('users.html', username = current_user.username)

@app.route('/users/data')
def userdata():
    try:
        query = RolesUsers.query
        cols = ['user_id', 'username', 'role', 'password']

        search = request.args.get('search[value]')
        if search:
            query = query.filter(db.or_(
                RolesUsers.user_id.like(f'%{search}%'),
                RolesUsers.username.like(f'%{search}%'),
                RolesUsers.role.like(f'%{search}%')
            ))
        filtered = query.count()

        query = Sort(query, RolesUsers, cols)
        query = Pageinate(query)

        return jsonify({
            'data': [user.to_dict() for user in query],
            'recordsFiltered': filtered,
            'recordsTotal': RolesUsers.query.count(),
            'draw': request.args.get('draw', type=int)
        })

    except Exception as e:
        return str(e)

@app.route('/users/add', methods=['GET'])
def useradd():
    try:
        username = request.args.get('username')
        password = request.args.get('password')
        role = request.args.get('role')
        user_datastore.create_user(username=username, password=hash_password(password), roles=[role])
        db.session.commit()
        userid = User.query.filter_by(username=username).first().id
        newuser = RolesUsers.query.filter_by(user_id=userid).first()
        newuser.username = username
        newuser.role = role
        db.session.commit()
        return jsonify({
            'data': newuser.to_dict()
        })
    except Exception as e:
        print(e)
        return redirect(url_for('home'))

@app.route('/users/edit', methods=['GET'])
def useredit():
    try:
        username = request.args.get('username')
        userid = request.args.get('user_id')
        role = request.args.get('role')
        roleid = Role.query.filter_by(name=role).first().id
        target = User.query.filter_by(id=userid).first()
        target.username = username
        target = RolesUsers.query.filter_by(user_id=userid).first()
        target.username = username
        target.role = role
        target.role_id = roleid
        db.session.commit()
        return jsonify({
            'data': target.to_dict()
        })
    except Exception as e:
        print(e)
        return redirect(url_for('home'))
    
@app.route('/users/delete', methods=['GET'])
def userdelete():
    try:
        userid = request.args.get('user_id')
        target = User.query.filter_by(id=userid).first()
        User.query.filter_by(id=userid).delete()
        db.session.commit()
        return jsonify({
            'data': target.to_dict()
        })
    except Exception as e:
        print(e)
        return redirect(url_for('home'))

#—————————————————— Functions ——————————————————#

def Sort(query, Table, columns):
    order = []
    i = 0
    while True:
        col_index = request.args.get(f'order[{i}][column]')
        if col_index is None:
            break
        col_name = request.args.get(f'columns[{col_index}][data]')
        if col_name not in columns:
            col_name = 'id'
        descending = request.args.get(f'order[{i}][dir]') == 'desc'
        col = getattr(Table, col_name)
        if descending:
            col = col.desc()
        order.append(col)
        i += 1
    if order:
        query = query.order_by(*order)
    return query

def Pageinate(query):
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    query = query.offset(start).limit(length)
    return query

with app.app_context():
    db.create_all()
    user_datastore.find_or_create_role(name='admin')
    user_datastore.find_or_create_role(name='viewer')
    db.session.commit()

if __name__ == '__main__':
    app.run(host='192.168.1.5', port=5000)