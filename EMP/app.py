from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from models import db, User, Course, Exam, Rubric, Slot, Booking, RubricScore

app = Flask(__name__)
app.config['SECRET_KEY'] = 'emp-secret-key-change-me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///emp.db'

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------- Role based access ----------
def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.role != role:
                flash('Access denied.', 'danger')
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ---------- Auth routes ----------
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for(current_user.role + '_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash('Invalid email or password.', 'danger')
        elif not user.is_active_user:
            flash('Your account is deactivated. Contact admin.', 'warning')
        else:
            login_user(user)
            return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        role = request.form['role']
        contact = request.form.get('contact', '').strip()
        department = request.form.get('department', '').strip()

        if role not in ('student', 'examiner'):
            flash('Invalid role.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        else:
            user = User(
                name=name, email=email,
                password=generate_password_hash(password),
                role=role, contact=contact, department=department,
                is_approved=(role == 'student')   # examiner needs admin approval
            )
            db.session.add(user)
            db.session.commit()
            if role == 'examiner':
                flash('Registered! Wait for admin approval before using dashboard.', 'info')
            else:
                flash('Registered successfully. Please login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------- Dashboards (abhi placeholder, aage fill karenge) ----------
@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    stats = {
        'courses': Course.query.count(),
        'exams': Exam.query.count(),
        'examiners': User.query.filter_by(role='examiner').count(),
        'students': User.query.filter_by(role='student').count(),
        'slots': Slot.query.count(),
        'bookings': Booking.query.count(),
        'pending': User.query.filter_by(role='examiner', is_approved=False).count(),
    }
    return render_template('admin/dashboard.html', stats=stats)



# ---------- Admin: Courses ----------
@app.route('/admin/courses')
@role_required('admin')
def admin_courses():
    q = request.args.get('q', '').strip()
    query = Course.query
    if q:
        query = query.filter(Course.name.ilike(f'%{q}%') | Course.code.ilike(f'%{q}%'))
    return render_template('admin/courses.html', courses=query.all(), q=q)


@app.route('/admin/courses/add', methods=['GET', 'POST'])
@role_required('admin')
def add_course():
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        name = request.form['name'].strip()
        if Course.query.filter_by(code=code).first():
            flash('Course code already exists.', 'danger')
        else:
            db.session.add(Course(code=code, name=name,
                                  description=request.form.get('description', ''),
                                  status=request.form['status']))
            db.session.commit()
            flash('Course added.', 'success')
            return redirect(url_for('admin_courses'))
    return render_template('admin/course_form.html', course=None)


@app.route('/admin/courses/<int:cid>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_course(cid):
    course = db.get_or_404(Course, cid)
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        clash = Course.query.filter(Course.code == code, Course.id != cid).first()
        if clash:
            flash('Course code already exists.', 'danger')
        else:
            course.code = code
            course.name = request.form['name'].strip()
            course.description = request.form.get('description', '')
            course.status = request.form['status']
            db.session.commit()
            flash('Course updated.', 'success')
            return redirect(url_for('admin_courses'))
    return render_template('admin/course_form.html', course=course)


@app.route('/admin/courses/<int:cid>/delete', methods=['POST'])
@role_required('admin')
def delete_course(cid):
    course = db.get_or_404(Course, cid)
    if Exam.query.filter_by(course_id=cid).first():
        flash('Is course ke exams bane hue hain, delete nahi ho sakta. Status Inactive kar do.', 'warning')
    else:
        db.session.delete(course)
        db.session.commit()
        flash('Course deleted.', 'success')
    return redirect(url_for('admin_courses'))


# ---------- Admin: Examiners ----------
@app.route('/admin/examiners')
@role_required('admin')
def admin_examiners():
    q = request.args.get('q', '').strip()
    query = User.query.filter_by(role='examiner')
    if q:
        if q.isdigit():
            query = query.filter(User.id == int(q))
        else:
            query = query.filter(User.name.ilike(f'%{q}%'))
    return render_template('admin/examiners.html', examiners=query.all(), q=q)


@app.route('/admin/examiners/<int:uid>/<action>', methods=['POST'])
@role_required('admin')
def examiner_action(uid, action):
    user = db.get_or_404(User, uid)
    if user.role != 'examiner':
        flash('Not an examiner.', 'danger')
    elif action == 'approve':
        user.is_approved = True
        flash('Examiner approved.', 'success')
    elif action == 'deactivate':
        user.is_active_user = False
        flash('Examiner deactivated.', 'warning')
    elif action == 'activate':
        user.is_active_user = True
        flash('Examiner activated.', 'success')
    db.session.commit()
    return redirect(url_for('admin_examiners'))

# ---------- Admin: Exams ----------
def parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date() if value else None


def fill_exam_from_form(exam):
    exam.course_id = int(request.form['course_id'])
    exam.examiner_id = int(request.form['examiner_id']) if request.form.get('examiner_id') else None
    exam.name = request.form['name'].strip()
    exam.exam_type = request.form['exam_type']
    exam.duration = int(request.form['duration'])
    exam.max_marks = int(request.form['max_marks'])
    exam.slot_create_start = parse_date(request.form.get('slot_create_start'))
    exam.slot_create_end = parse_date(request.form.get('slot_create_end'))
    exam.booking_start = parse_date(request.form.get('booking_start'))
    exam.booking_end = parse_date(request.form.get('booking_end'))


def date_error(exam):
    if exam.slot_create_start and exam.slot_create_end and exam.slot_create_start > exam.slot_create_end:
        return 'Slot creation end date, start date se pehle nahi ho sakti.'
    if exam.booking_start and exam.booking_end and exam.booking_start > exam.booking_end:
        return 'Booking end date, start date se pehle nahi ho sakti.'
    return None


@app.route('/admin/exams')
@role_required('admin')
def admin_exams():
    q = request.args.get('q', '').strip()
    query = Exam.query
    if q:
        if q.isdigit():
            query = query.filter(Exam.id == int(q))
        else:
            query = query.filter(Exam.name.ilike(f'%{q}%'))
    return render_template('admin/exams.html', exams=query.all(), q=q)


@app.route('/admin/exams/add', methods=['GET', 'POST'])
@role_required('admin')
def add_exam():
    courses = Course.query.filter_by(status='Active').all()
    examiners = User.query.filter_by(role='examiner', is_approved=True, is_active_user=True).all()
    if request.method == 'POST':
        exam = Exam()
        fill_exam_from_form(exam)
        err = date_error(exam)
        if err:
            flash(err, 'danger')
        else:
            db.session.add(exam)
            db.session.commit()
            flash('Exam created. Ab rubrics add karo.', 'success')
            return redirect(url_for('exam_rubrics', eid=exam.id))
    return render_template('admin/exam_form.html', exam=None, courses=courses, examiners=examiners)


@app.route('/admin/exams/<int:eid>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_exam(eid):
    exam = db.get_or_404(Exam, eid)
    courses = Course.query.all()
    examiners = User.query.filter_by(role='examiner', is_approved=True, is_active_user=True).all()
    if request.method == 'POST':
        fill_exam_from_form(exam)
        err = date_error(exam)
        if err:
            flash(err, 'danger')
            db.session.rollback()
        else:
            db.session.commit()
            flash('Exam updated.', 'success')
            return redirect(url_for('admin_exams'))
    return render_template('admin/exam_form.html', exam=exam, courses=courses, examiners=examiners)


@app.route('/admin/exams/<int:eid>/delete', methods=['POST'])
@role_required('admin')
def delete_exam(eid):
    exam = db.get_or_404(Exam, eid)
    if Slot.query.filter_by(exam_id=eid).first():
        flash('Is exam ke slots bane hue hain, delete nahi ho sakta. Status Closed kar do.', 'warning')
    else:
        Rubric.query.filter_by(exam_id=eid).delete()
        db.session.delete(exam)
        db.session.commit()
        flash('Exam deleted.', 'success')
    return redirect(url_for('admin_exams'))


@app.route('/admin/exams/<int:eid>/status', methods=['POST'])
@role_required('admin')
def exam_status(eid):
    exam = db.get_or_404(Exam, eid)
    status = request.form['status']
    if status in ('Draft', 'Slot Creation', 'Booking Open', 'Closed', 'Completed'):
        exam.status = status
        db.session.commit()
        flash(f'Status changed to {status}.', 'success')
    return redirect(url_for('admin_exams'))


# ---------- Admin: Rubrics ----------
@app.route('/admin/exams/<int:eid>/rubrics', methods=['GET', 'POST'])
@role_required('admin')
def exam_rubrics(eid):
    exam = db.get_or_404(Exam, eid)
    rubrics = Rubric.query.filter_by(exam_id=eid).all()
    total = sum(r.max_marks for r in rubrics)
    if request.method == 'POST':
        marks = int(request.form['max_marks'])
        if total + marks > exam.max_marks:
            flash(f'Rubric marks ka total exam ke max marks ({exam.max_marks}) se zyada nahi ho sakta.', 'danger')
        else:
            db.session.add(Rubric(exam_id=eid,
                                  criterion=request.form['criterion'].strip(),
                                  max_marks=marks,
                                  weightage=float(request.form.get('weightage') or 1),
                                  description=request.form.get('description', '')))
            db.session.commit()
            flash('Rubric added.', 'success')
            return redirect(url_for('exam_rubrics', eid=eid))
    return render_template('admin/rubrics.html', exam=exam, rubrics=rubrics, total=total)


@app.route('/admin/rubrics/<int:rid>/delete', methods=['POST'])
@role_required('admin')
def delete_rubric(rid):
    rubric = db.get_or_404(Rubric, rid)
    eid = rubric.exam_id
    db.session.delete(rubric)
    db.session.commit()
    flash('Rubric deleted.', 'success')
    return redirect(url_for('exam_rubrics', eid=eid))

# ---------- Examiner ----------
def examiner_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'examiner':
            flash('Access denied.', 'danger')
            return redirect(url_for('home'))
        if not current_user.is_approved:
            return redirect(url_for('examiner_dashboard'))
        return f(*args, **kwargs)
    return wrapper


def can_create_slot(exam):
    today = date.today()
    if exam.status != 'Slot Creation':
        return False
    if exam.slot_create_start and today < exam.slot_create_start:
        return False
    if exam.slot_create_end and today > exam.slot_create_end:
        return False
    return True


def can_modify_slot(slot):
    exam = slot.exam
    if slot.status in ('Cancelled', 'Completed'):
        return False
    if exam.status not in ('Draft', 'Slot Creation'):
        return False
    if exam.booking_start and date.today() >= exam.booking_start:
        return False
    active = Booking.query.filter(Booking.slot_id == slot.id,
                                  Booking.status.in_(['Booked', 'Completed'])).first()
    return active is None


def read_slot_form(slot_id=None):
    """Form padhta hai aur validate karta hai. (data, error) return karta hai."""
    try:
        d = parse_date(request.form['date'])
        st = datetime.strptime(request.form['start_time'], '%H:%M').time()
        en = datetime.strptime(request.form['end_time'], '%H:%M').time()
        cap = int(request.form['capacity'])
    except (ValueError, KeyError):
        return None, 'Date, time ya capacity galat hai.'
    if d < date.today():
        return None, 'Past date ka slot nahi bana sakte.'
    if en <= st:
        return None, 'End time, start time ke baad hona chahiye.'
    if cap < 1:
        return None, 'Capacity kam se kam 1 honi chahiye.'
    others = Slot.query.filter(Slot.examiner_id == current_user.id, Slot.date == d,
                               Slot.status != 'Cancelled', Slot.id != (slot_id or 0)).all()
    for s in others:
        if st < s.end_time and en > s.start_time:
            return None, 'Ye time aapke dusre slot se overlap kar raha hai.'
    return (d, st, en, cap), None


@app.route('/examiner/dashboard')
@role_required('examiner')
def examiner_dashboard():
    if not current_user.is_approved:
        return render_template('examiner/pending.html')
    exams = Exam.query.filter_by(examiner_id=current_user.id).all()
    slots = Slot.query.filter_by(examiner_id=current_user.id).all()
    ids = [s.id for s in slots]
    booked = Booking.query.filter(Booking.slot_id.in_(ids),
                                  Booking.status.in_(['Booked', 'Completed'])).count() if ids else 0
    pending = Booking.query.filter(Booking.slot_id.in_(ids),
                                   Booking.status == 'Booked').count() if ids else 0
    rows = [(e, can_create_slot(e)) for e in exams]
    return render_template('examiner/dashboard.html', rows=rows, n_slots=len(slots),
                           booked=booked, pending=pending)


@app.route('/examiner/slots')
@examiner_required
def examiner_slots():
    slots = Slot.query.filter_by(examiner_id=current_user.id)\
                      .order_by(Slot.date, Slot.start_time).all()
    rows = [(s, can_modify_slot(s)) for s in slots]
    return render_template('examiner/slots.html', rows=rows)


@app.route('/examiner/slots/add', methods=['GET', 'POST'])
@examiner_required
def add_slot():
    exams = [e for e in Exam.query.filter_by(examiner_id=current_user.id).all()
             if can_create_slot(e)]
    if request.method == 'POST':
        exam = db.session.get(Exam, int(request.form['exam_id']))
        if not exam or exam.examiner_id != current_user.id or not can_create_slot(exam):
            flash('Is exam ke liye abhi slot create nahi kar sakte.', 'danger')
            return redirect(url_for('examiner_slots'))
        data, err = read_slot_form()
        if err:
            flash(err, 'danger')
        else:
            d, st, en, cap = data
            db.session.add(Slot(exam_id=exam.id, examiner_id=current_user.id, date=d,
                                start_time=st, end_time=en, capacity=cap,
                                available_seats=cap, status='Available'))
            db.session.commit()
            flash('Slot created.', 'success')
            return redirect(url_for('examiner_slots'))
    return render_template('examiner/slot_form.html', slot=None, exams=exams)


@app.route('/examiner/slots/<int:sid>/edit', methods=['GET', 'POST'])
@examiner_required
def edit_slot(sid):
    slot = db.get_or_404(Slot, sid)
    if slot.examiner_id != current_user.id:
        flash('Ye aapka slot nahi hai.', 'danger')
        return redirect(url_for('examiner_slots'))
    if not can_modify_slot(slot):
        flash('Booking shuru hone ke baad ya booking hone par slot edit nahi ho sakta.', 'warning')
        return redirect(url_for('examiner_slots'))
    if request.method == 'POST':
        data, err = read_slot_form(slot_id=sid)
        if err:
            flash(err, 'danger')
        else:
            slot.date, slot.start_time, slot.end_time, slot.capacity = data
            slot.available_seats = slot.capacity
            db.session.commit()
            flash('Slot updated.', 'success')
            return redirect(url_for('examiner_slots'))
    return render_template('examiner/slot_form.html', slot=slot, exams=[])


@app.route('/examiner/slots/<int:sid>/delete', methods=['POST'])
@examiner_required
def delete_slot(sid):
    slot = db.get_or_404(Slot, sid)
    if slot.examiner_id != current_user.id:
        flash('Ye aapka slot nahi hai.', 'danger')
    elif not can_modify_slot(slot):
        flash('Booking shuru hone ke baad ya booking hone par slot remove nahi ho sakta.', 'warning')
    else:
        if Booking.query.filter_by(slot_id=sid).first():
            slot.status = 'Cancelled'      # purani cancelled bookings ka record bacha rahe
        else:
            db.session.delete(slot)
        db.session.commit()
        flash('Slot removed.', 'success')
    return redirect(url_for('examiner_slots'))


@app.route('/examiner/slots/<int:sid>/students')
@examiner_required
def slot_students(sid):
    slot = db.get_or_404(Slot, sid)
    if slot.examiner_id != current_user.id:
        flash('Ye aapka slot nahi hai.', 'danger')
        return redirect(url_for('examiner_slots'))
    bookings = Booking.query.filter_by(slot_id=sid).all()
    return render_template('examiner/slot_students.html', slot=slot, bookings=bookings)


@app.route('/examiner/evaluate/<int:bid>', methods=['GET', 'POST'])
@examiner_required
def evaluate(bid):
    booking = db.get_or_404(Booking, bid)
    slot = booking.slot
    if slot.examiner_id != current_user.id:
        flash('Aap sirf apne slots ke students evaluate kar sakte ho.', 'danger')
        return redirect(url_for('examiner_dashboard'))
    if booking.status == 'Cancelled':
        flash('Cancelled booking evaluate nahi ho sakti.', 'warning')
        return redirect(url_for('slot_students', sid=slot.id))
    rubrics = Rubric.query.filter_by(exam_id=slot.exam_id).all()
    if not rubrics:
        flash('Is exam ke rubrics admin ne abhi nahi banaye.', 'warning')
        return redirect(url_for('slot_students', sid=slot.id))
    scores = {s.rubric_id: s for s in RubricScore.query.filter_by(booking_id=bid).all()}

    if request.method == 'POST':
        values, total = {}, 0
        try:
            for r in rubrics:
                m = float(request.form[f'r_{r.id}'])
                if m < 0 or m > r.max_marks:
                    raise ValueError
                values[r.id] = m
                total += m
        except (ValueError, KeyError):
            flash('Har rubric ke marks 0 se us rubric ke max marks ke beech hone chahiye.', 'danger')
            return render_template('examiner/evaluate.html', booking=booking, rubrics=rubrics, scores=scores)
        for r in rubrics:
            if r.id in scores:
                scores[r.id].marks = values[r.id]
            else:
                db.session.add(RubricScore(booking_id=bid, rubric_id=r.id, marks=values[r.id]))
        booking.total_marks = total
        booking.remarks = request.form.get('remarks', '').strip()
        booking.status = 'Completed'
        db.session.commit()
        flash(f'Evaluation saved. Total: {total}/{slot.exam.max_marks}', 'success')
        return redirect(url_for('slot_students', sid=slot.id))
    return render_template('examiner/evaluate.html', booking=booking, rubrics=rubrics, scores=scores)

# ---------- Student ----------
def booking_open(exam):
    today = date.today()
    if exam.status != 'Booking Open':
        return False
    if exam.booking_start and today < exam.booking_start:
        return False
    if exam.booking_end and today > exam.booking_end:
        return False
    return True


def active_exam_ids(student_id):
    """Exams jinme student ki Booked/Completed booking hai (duplicate rokne ke liye)."""
    rows = Booking.query.filter(Booking.student_id == student_id,
                                Booking.status.in_(['Booked', 'Completed'])).all()
    return {b.slot.exam_id for b in rows}


@app.route('/student/dashboard')
@role_required('student')
def student_dashboard():
    today = date.today()
    exams = [e for e in Exam.query.all() if booking_open(e)]
    slots = Slot.query.filter(Slot.status == 'Available', Slot.available_seats > 0,
                              Slot.date >= today).order_by(Slot.date, Slot.start_time).all()
    slots = [s for s in slots if booking_open(s.exam)]
    mine = Booking.query.filter_by(student_id=current_user.id).all()
    upcoming = sorted([b for b in mine if b.status == 'Booked' and b.slot.date >= today],
                      key=lambda b: (b.slot.date, b.slot.start_time))
    results = [b for b in mine if b.status == 'Completed' and b.slot.exam.results_published]
    return render_template('student/dashboard.html', exams=exams, slots=slots,
                           upcoming=upcoming, results=results)


@app.route('/student/exams')
@role_required('student')
def student_exams():
    q = request.args.get('q', '').strip()
    etype = request.args.get('type', '')
    course_id = request.args.get('course_id', '')
    query = Exam.query.filter(Exam.status != 'Draft')
    if q:
        query = query.filter(Exam.name.ilike(f'%{q}%'))
    if etype:
        query = query.filter(Exam.exam_type == etype)
    if course_id.isdigit():
        query = query.filter(Exam.course_id == int(course_id))
    booked = active_exam_ids(current_user.id)
    rows = [(e, booking_open(e), e.id in booked) for e in query.all()]
    return render_template('student/exams.html', rows=rows, q=q, etype=etype,
                           course_id=course_id, courses=Course.query.all())


@app.route('/student/exams/<int:eid>/slots')
@role_required('student')
def exam_slots(eid):
    exam = db.get_or_404(Exam, eid)
    slots = Slot.query.filter(Slot.exam_id == eid, Slot.status != 'Cancelled',
                              Slot.date >= date.today())\
                      .order_by(Slot.date, Slot.start_time).all()
    return render_template('student/exam_slots.html', exam=exam, slots=slots,
                           is_open=booking_open(exam),
                           already=eid in active_exam_ids(current_user.id))


@app.route('/student/slots/<int:sid>/book', methods=['POST'])
@role_required('student')
def book_slot(sid):
    slot = db.get_or_404(Slot, sid)
    exam = slot.exam
    if not booking_open(exam):
        flash('Is exam ki booking abhi open nahi hai.', 'danger')
    elif slot.date < date.today():
        flash('Ye slot nikal chuka hai.', 'danger')
    elif slot.status != 'Available' or slot.available_seats < 1:
        flash('Ye slot full hai.', 'danger')
    elif exam.id in active_exam_ids(current_user.id):
        flash('Aap is exam ke liye pehle se book kar chuke ho.', 'warning')
    else:
        db.session.add(Booking(student_id=current_user.id, slot_id=sid, status='Booked'))
        slot.available_seats -= 1
        if slot.available_seats == 0:
            slot.status = 'Full'
        db.session.commit()
        flash('Slot book ho gaya! 🎉', 'success')
        return redirect(url_for('my_bookings'))
    return redirect(url_for('exam_slots', eid=exam.id))


@app.route('/student/bookings')
@role_required('student')
def my_bookings():
    bookings = Booking.query.filter_by(student_id=current_user.id)\
                            .order_by(Booking.booking_date.desc()).all()
    rows = []
    for b in bookings:
        exam = b.slot.exam
        can_cancel = (b.status == 'Booked' and
                      (not exam.booking_end or date.today() <= exam.booking_end))
        rows.append((b, can_cancel))
    return render_template('student/bookings.html', rows=rows)


@app.route('/student/bookings/<int:bid>/cancel', methods=['POST'])
@role_required('student')
def cancel_booking(bid):
    booking = db.get_or_404(Booking, bid)
    exam = booking.slot.exam
    if booking.student_id != current_user.id:
        flash('Ye aapki booking nahi hai.', 'danger')
    elif booking.status != 'Booked':
        flash('Sirf Booked status wali booking cancel ho sakti hai.', 'warning')
    elif exam.booking_end and date.today() > exam.booking_end:
        flash('Booking deadline nikal chuki hai, ab cancel nahi ho sakta.', 'danger')
    else:
        booking.status = 'Cancelled'
        slot = booking.slot
        slot.available_seats += 1
        if slot.status == 'Full':
            slot.status = 'Available'
        db.session.commit()
        flash('Booking cancel ho gayi.', 'success')
    return redirect(url_for('my_bookings'))


@app.route('/student/results')
@role_required('student')
def my_results():
    rows = [b for b in Booking.query.filter_by(student_id=current_user.id, status='Completed').all()
            if b.slot.exam.results_published]
    return render_template('student/results.html', rows=rows)


@app.route('/student/profile', methods=['GET', 'POST'])
@role_required('student')
def student_profile():
    if request.method == 'POST':
        name = request.form['name'].strip()
        new_pw = request.form.get('password', '')
        if not name:
            flash('Name khali nahi ho sakta.', 'danger')
        elif new_pw and len(new_pw) < 6:
            flash('Password kam se kam 6 characters ka ho.', 'danger')
        else:
            current_user.name = name
            current_user.contact = request.form.get('contact', '').strip()
            if new_pw:
                current_user.password = generate_password_hash(new_pw)
            db.session.commit()
            flash('Profile updated.', 'success')
            return redirect(url_for('student_profile'))
    return render_template('student/profile.html')


# ---------- Admin: results publish ----------
@app.route('/admin/exams/<int:eid>/publish', methods=['POST'])
@role_required('admin')
def publish_results(eid):
    exam = db.get_or_404(Exam, eid)
    exam.results_published = not exam.results_published
    db.session.commit()
    flash('Results published.' if exam.results_published else 'Results unpublished.', 'success')
    return redirect(url_for('admin_exams'))

# ---------- Admin: Students / Slots / Bookings ----------
@app.route('/admin/students')
@role_required('admin')
def admin_students():
    q = request.args.get('q', '').strip()
    query = User.query.filter_by(role='student')
    if q:
        if q.isdigit():
            query = query.filter(User.id == int(q))
        else:
            query = query.filter(User.name.ilike(f'%{q}%') | User.email.ilike(f'%{q}%'))
    return render_template('admin/students.html', students=query.all(), q=q)


@app.route('/admin/slots')
@role_required('admin')
def admin_slots():
    q = request.args.get('q', '').strip()
    query = Slot.query.join(Exam, Slot.exam_id == Exam.id)
    if q:
        if q.isdigit():
            query = query.filter(Slot.id == int(q))
        else:
            query = query.filter(Exam.name.ilike(f'%{q}%'))
    slots = query.order_by(Slot.date, Slot.start_time).all()
    return render_template('admin/slots.html', slots=slots, q=q)


@app.route('/admin/bookings')
@role_required('admin')
def admin_bookings():
    q = request.args.get('q', '').strip()
    query = Booking.query.join(User, Booking.student_id == User.id)
    if q:
        if q.isdigit():
            query = query.filter((Booking.id == int(q)) | (Booking.student_id == int(q)))
        else:
            query = query.filter(User.name.ilike(f'%{q}%'))
    return render_template('admin/bookings.html',
                           bookings=query.order_by(Booking.booking_date.desc()).all(), q=q)


@app.route('/admin/bookings/<int:bid>/reschedule', methods=['GET', 'POST'])
@role_required('admin')
def reschedule_booking(bid):
    booking = db.get_or_404(Booking, bid)
    old = booking.slot
    if booking.status != 'Booked':
        flash('Sirf Booked status wali booking reschedule ho sakti hai.', 'warning')
        return redirect(url_for('admin_bookings'))
    options = Slot.query.filter(Slot.exam_id == old.exam_id, Slot.id != old.id,
                                Slot.status == 'Available', Slot.available_seats > 0,
                                Slot.date >= date.today()).all()
    if request.method == 'POST':
        new = db.session.get(Slot, int(request.form['slot_id']))
        if not new or new not in options:
            flash('Ye slot select nahi ho sakta.', 'danger')
        else:
            old.available_seats += 1
            if old.status == 'Full':
                old.status = 'Available'
            new.available_seats -= 1
            if new.available_seats == 0:
                new.status = 'Full'
            booking.slot_id = new.id
            db.session.commit()
            flash('Booking reschedule ho gayi.', 'success')
            return redirect(url_for('admin_bookings'))
    return render_template('admin/reschedule.html', booking=booking, options=options)


@app.route('/admin/slots/<int:sid>/examiner', methods=['GET', 'POST'])
@role_required('admin')
def change_slot_examiner(sid):
    slot = db.get_or_404(Slot, sid)
    if slot.status in ('Cancelled', 'Completed'):
        flash('Is slot ka examiner nahi badal sakte.', 'warning')
        return redirect(url_for('admin_slots'))
    examiners = User.query.filter(User.role == 'examiner', User.is_approved == True,
                                  User.is_active_user == True, User.id != slot.examiner_id).all()
    if request.method == 'POST':
        new_id = int(request.form['examiner_id'])
        clash = Slot.query.filter(Slot.examiner_id == new_id, Slot.date == slot.date,
                                  Slot.status != 'Cancelled', Slot.id != slot.id).all()
        if any(slot.start_time < s.end_time and slot.end_time > s.start_time for s in clash):
            flash('Is examiner ka us time pe dusra slot hai.', 'danger')
        else:
            slot.examiner_id = new_id
            db.session.commit()
            flash('Examiner change ho gaya.', 'success')
            return redirect(url_for('admin_slots'))
    return render_template('admin/slot_examiner.html', slot=slot, examiners=examiners)

# ---------- DB create + admin seed ----------
def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(role='admin').first():
            admin = User(name='Admin', email='admin@emp.com',
                         password=generate_password_hash('admin123'),
                         role='admin', is_approved=True)
            db.session.add(admin)
            db.session.commit()


if __name__ == '__main__':
    init_db()
    app.run(debug=True)