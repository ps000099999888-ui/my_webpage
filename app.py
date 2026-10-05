

import sys
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ---------- .env loader ----------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[OmniCart] python-dotenv not installed. Run: pip install python-dotenv")

# ============================================================
# OmniCart - Complete E-Commerce PDF Notes Platform
# Copyright (c) 2026 PATEL KARKHANA PVT.LTD.
# ALL RIGHTS RESERVED
# ============================================================
import smtplib
import os
import io
import re
import uuid
import base64
import secrets
import hashlib
import hmac
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, abort, session, send_file,
                   make_response, g)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_bcrypt import Bcrypt
from sqlalchemy import or_, func, Index
from sqlalchemy import or_, func, Index

# ============================================================
# FIREBASE ADMIN SDK (NEW)
# ============================================================
try:
    import firebase_admin
    from firebase_admin import credentials, auth as firebase_auth
    FIREBASE_ADMIN_AVAILABLE = True
except ImportError:
    FIREBASE_ADMIN_AVAILABLE = False
    print("[OmniCart] firebase-admin not installed. Run: pip install firebase-admin")

# ---------- Optional libraries ----------
try:
    import razorpay
    RAZORPAY_AVAILABLE = True
except ImportError:
    RAZORPAY_AVAILABLE = False

try:
    from pypdf import PdfReader, PdfWriter
    PYPDF_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter
        PYPDF_AVAILABLE = True
    except ImportError:
        PYPDF_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

try:
    from cryptography.fernet import Fernet, InvalidToken
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False


# ============================================================
# PATHS & CONFIG
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

COMPANY_NAME = "OmniCart"
COMPANY_LEGAL = "PATEL KARKHANA PVT.LTD."
COMPANY_EMAIL = "omnicart@gmail.com"
COMPANY_PHONE = "9101970867"

SECRET_KEY = os.environ.get('SECRET_KEY', 'omnicart-secret-key-2026-change-me')

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')

UPI_ID = os.environ.get('UPI_ID', 'omnicart@upi')
UPI_PAYEE_NAME = COMPANY_NAME

PRESIDENT_MOBILE = "9101970867"
PRESIDENT_NAME = "Company President"

FREE_PREVIEW_PAGES = 3

FERNET_KEY = os.environ.get('FERNET_KEY', '')
if not FERNET_KEY and FERNET_AVAILABLE:
    FERNET_KEY = Fernet.generate_key().decode()
    os.environ['FERNET_KEY'] = FERNET_KEY
    print("[OmniCart] Auto-generated FERNET_KEY. Save this in .env:")
    print(f"  FERNET_KEY={FERNET_KEY}")
# ============================================================
# FIREBASE INITIALIZATION (NEW)
# ============================================================
FIREBASE_ADMIN_JSON = os.environ.get('FIREBASE_ADMIN_JSON',
    os.path.join(BASE_DIR, 'firebase-admin.json'))

firebase_app = None

def init_firebase():
    """Firebase Admin SDK initialize karo."""
    global firebase_app
    
    if firebase_app is not None:
        return firebase_app
    
    if not FIREBASE_ADMIN_AVAILABLE:
        print("[Firebase] firebase-admin not installed.")
        return None
    
    if not os.path.exists(FIREBASE_ADMIN_JSON):
        print(f"[Firebase] Service account key nahi mili: {FIREBASE_ADMIN_JSON}")
        return None
    
    try:
        cred = credentials.Certificate(FIREBASE_ADMIN_JSON)
        firebase_app = firebase_admin.initialize_app(cred)
        print("[Firebase] Admin SDK initialized successfully.")
        return firebase_app
    except Exception as e:
        print(f"[Firebase init error] {e}")
        return None


# App start pe initialize karo
init_firebase()


# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)

# Save original render_template
from flask import render_template as _flask_rt

def render_template(template_name, **context):
    """All routes render base.html (SPA-style)."""
    return _flask_rt('base.html', **context)
app.config['FERNET_KEY'] = FERNET_KEY

# Firebase config for frontend (public keys)
app.config['FIREBASE_API_KEY'] = os.environ.get('FIREBASE_API_KEY', '')
app.config['FIREBASE_AUTH_DOMAIN'] = os.environ.get('FIREBASE_AUTH_DOMAIN', '')
app.config['FIREBASE_PROJECT_ID'] = os.environ.get('FIREBASE_PROJECT_ID', '')
app.config['FIREBASE_APP_ID'] = os.environ.get('FIREBASE_APP_ID', '')
app.config['FIREBASE_MESSAGING_SENDER_ID'] = os.environ.get('FIREBASE_MESSAGING_SENDER_ID', '')

app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "omnicart.db")}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
app.config['FREE_PREVIEW_PAGES'] = FREE_PREVIEW_PAGES
app.config['FERNET_KEY'] = FERNET_KEY

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'user_login'
login_manager.login_message = 'Pehle login karein.'
login_manager.login_message_category = 'warning'

razorpay_client = None
if RAZORPAY_AVAILABLE and RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    try:
        razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    except Exception as e:
        print(f"[Razorpay init error] {e}")
        razorpay_client = None


# ============================================================
# ENCRYPTION HELPERS
# ============================================================
_fernet = None

def _get_fernet():
    global _fernet
    if _fernet is None and FERNET_AVAILABLE and FERNET_KEY:
        try:
            key = FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY
            _fernet = Fernet(key)
        except Exception as e:
            print(f"[Fernet error] {e}")
            _fernet = None
    return _fernet


def encrypt_text(plain):
    if not plain:
        return plain
    f = _get_fernet()
    if not f:
        return plain
    try:
        return f.encrypt(plain.encode()).decode()
    except Exception:
        return plain


def decrypt_text(token):
    if not token:
        return token
    f = _get_fernet()
    if not f:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except Exception:
        return token


# ============================================================
# VALIDATION
# ============================================================
EMAIL_RE = re.compile(r'^[\w\.\-\+]+@[\w\-]+\.[\w\.\-]+$')
MOBILE_RE = re.compile(r'^[6-9]\d{9}$')
PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#^()_\-+=])'
    r'[A-Za-z\d@$!%*?&#^()_\-+=]{8,}$'
)


def valid_email(e):
    return bool(e and EMAIL_RE.match(e))


def valid_mobile(m):
    return bool(m and MOBILE_RE.match(m))


def valid_password(pw):
    return bool(pw and PASSWORD_RE.match(pw))


def password_errors(pw):
    errs = []
    if not pw:
        return ['Password khali nahi ho sakta.']
    if len(pw) < 8:
        errs.append('Kam se kam 8 characters chahiye.')
    if not re.search(r'[A-Z]', pw):
        errs.append('1 capital letter chahiye.')
    if not re.search(r'[a-z]', pw):
        errs.append('1 small letter chahiye.')
    if not re.search(r'\d', pw):
        errs.append('1 number chahiye.')
    if not re.search(r'[@$!%*?&#^()_\-+=]', pw):
        errs.append('1 special character chahiye.')
    return errs


# ============================================================
# GENERATORS
# ============================================================
def generate_otp(length=6):
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def generate_ceo_code():
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    suffix = ''.join(secrets.choice(alphabet) for _ in range(8))
    return f"OMNICART-{suffix}"


# ============================================================
# SMS / OTP HELPERS (NEW)
# ============================================================
import requests as _requests

def send_otp_sms(mobile, otp, purpose='user'):
    """
    SMS bhejne ka function. 
    
    PRODUCTION me Fast2SMS / MSG91 / Twilio integrate karo.
    Abhi dev me console pe print kar raha hai.
    """
    message = f"OmniCart OTP: {otp}. 10 min me valid. Kisi ke sath share na karein."
    
    # --- Option 1: Fast2SMS (India, sasta) ---
    fast2sms_key = os.environ.get('FAST2SMS_API_KEY', '')
    if fast2sms_key:
        try:
            resp = _requests.post(
                'https://www.fast2sms.com/dev/bulkV2',
                headers={'authorization': fast2sms_key},
                data={
                    'route': 'q',
                    'message': message,
                    'language': 'english',
                    'flash': 0,
                    'numbers': mobile
                },
                timeout=10
            )
            if resp.status_code == 200:
                print(f"[SMS] OTP sent to {mobile} via Fast2SMS")
                return True
            else:
                print(f"[SMS ERROR] Fast2SMS: {resp.text}")
        except Exception as e:
            print(f"[SMS ERROR] Fast2SMS exception: {e}")
    
    # --- Option 2: MSG91 ---
    msg91_key = os.environ.get('MSG91_AUTH_KEY', '')
    if msg91_key:
        try:
            resp = _requests.post(
                'https://api.msg91.com/api/v5/flow/',
                headers={'authkey': msg91_key, 'Content-Type': 'application/json'},
                json={
                    'flow_id': os.environ.get('MSG91_FLOW_ID', ''),
                    'sender': 'OMNCRT',
                    'mobiles': f'91{mobile}',
                    'VAR1': otp
                },
                timeout=10
            )
            if resp.status_code == 200:
                print(f"[SMS] OTP sent to {mobile} via MSG91")
                return True
        except Exception as e:
            print(f"[SMS ERROR] MSG91: {e}")
    
    # --- Fallback: Console print (DEV ONLY) ---
    print("=" * 60)
    print(f"  📱 OTP for {mobile} ({purpose}): {otp}")
    print(f"  Message: {message}")
    print("=" * 60)
    return True




    # DEV fallback
    if not smtp_user or not smtp_pass:
        print("=" * 60)
        print(f"  📧 [DEV] Email OTP for {to_email}: {otp}")
        print("=" * 60)
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'{COMPANY_NAME} - Email Verification OTP'
        msg['From'] = from_addr
        msg['To'] = to_email

        html = f"""
        <div style="font-family:Arial;max-width:500px;margin:auto;
                    padding:24px;border:2px solid #f97316;
                    border-radius:14px;background:#ffffff">
          <h2 style="color:#0b2b5c">🛒 {COMPANY_NAME} Verification</h2>
          <p>Namaste <b>{name}</b>,</p>
          <p>Aapka Email verification OTP:</p>
          <div style="font-size:32px;font-weight:900;color:#ea580c;
                      letter-spacing:10px;text-align:center;
                      padding:20px;background:#fff7ed;border-radius:10px">
            {otp}
          </div>
          <p style="color:#64748b;font-size:13px">
            Ye OTP <b>5 minute</b> me expire ho jayega.
          </p>
        </div>
        """

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        print(f"[EMAIL] OTP sent to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


def send_otp_email(to_email, otp, name='User'):
    """Email pe OTP bhejta hai."""
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    from_addr = os.environ.get('SMTP_FROM', smtp_user)

    # DEV fallback
    if not smtp_user or not smtp_pass:
        print("=" * 60)
        print(f"  📧 [DEV] Email OTP for {to_email}: {otp}")
        print(f"  To: {name}")
        print("=" * 60)
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'{COMPANY_NAME} - Email Verification OTP'
        msg['From'] = from_addr
        msg['To'] = to_email

        html = f"""
        <div style="font-family:Arial;max-width:500px;margin:auto;
                    padding:24px;border:2px solid #f97316;
                    border-radius:14px;background:#ffffff">
          <h2 style="color:#0b2b5c">🛒 {COMPANY_NAME} Verification</h2>
          <p>Namaste <b>{name}</b>,</p>
          <p>Aapka Email verification OTP:</p>
          <div style="font-size:32px;font-weight:900;color:#ea580c;
                      letter-spacing:10px;text-align:center;
                      padding:20px;background:#fff7ed;border-radius:10px">
            {otp}
          </div>
          <p style="color:#64748b;font-size:13px">
            Ye OTP <b>5 minute</b> me expire ho jayega.
          </p>
        </div>
        """

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        print(f"[EMAIL] OTP sent to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        print("=" * 60)
        print(f"  📧 [FALLBACK] Email OTP for {to_email}: {otp}")
        print("=" * 60)
        return False
    """
    OTP generate karke DB me save karta hai.
    Return: (otp_plain, otp_record) ya (None, None) agar fail ho.
    """
    # Purane OTPs delete karo is mobile ke liye
    PasswordResetOTP.query.filter_by(mobile=mobile, purpose=purpose, used=False)\
        .delete()
    
    # Naya OTP generate karo — 5 minute validity
    otp = generate_otp(6)
    otp_record = PasswordResetOTP(
        mobile=mobile,
        otp_hash=bcrypt.generate_password_hash(otp).decode(),
        purpose=purpose,
        ip_address=request.remote_addr if request else '',
        expires_at=datetime.utcnow() + timedelta(minutes=5)  # ← 5 min
    )
    db.session.add(otp_record)
    db.session.commit()
    
    # SMS bhejo
    send_otp_sms(mobile, otp, purpose)
    
    return otp, otp_record


# ============================================================
# PDF HELPERS
# ============================================================
def count_pdf_pages(file_path):
    if not PYPDF_AVAILABLE or not os.path.exists(file_path):
        return 0
    try:
        return len(PdfReader(file_path).pages)
    except Exception as e:
        print(f"[PDF count error] {e}")
        return 0


def truncate_pdf(file_path, max_pages=FREE_PREVIEW_PAGES):
    if not PYPDF_AVAILABLE:
        return None
    try:
        reader = PdfReader(file_path)
        writer = PdfWriter()
        for i in range(min(max_pages, len(reader.pages))):
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"[PDF truncate error] {e}")
        return None


def save_pdf_safely(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None, None
    orig = file_storage.filename
    if not orig.lower().endswith('.pdf'):
        return None, None, None
    safe = f"{uuid.uuid4().hex}_{secrets.token_hex(4)}.pdf"
    full = os.path.join(app.config['UPLOAD_FOLDER'], safe)
    file_storage.save(full)
    return safe, orig, full


def generate_upi_qr_base64(upi_id, payee_name, amount, note=''):
    if not QRCODE_AVAILABLE:
        return ''
    try:
        upi_url = (f"upi://pay?pa={upi_id}&pn={payee_name}"
                   f"&am={amount:.2f}&cu=INR&tn={note[:50]}")
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"[QR error] {e}")
        return ''


# ============================================================
# DATABASE MODELS
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), nullable=False, unique=True, index=True)
    mobile = db.Column(db.String(15), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), default='user', index=True)

    is_active = db.Column(db.Boolean, default=True)
    is_banned = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    mobile_verified = db.Column(db.Boolean, default=False)
    must_change_password = db.Column(db.Boolean, default=False)

    otp_hash = db.Column(db.String(255))
    otp_expires_at = db.Column(db.DateTime)
    otp_purpose = db.Column(db.String(40))

    theme = db.Column(db.String(20), default='light')
    language = db.Column(db.String(10), default='en')
    privacy_level = db.Column(db.String(20), default='normal')
    notifications_enabled = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow)

    purchases = db.relationship('Purchase', backref='user', lazy='dynamic',
                                  foreign_keys='Purchase.user_id')
    feedbacks = db.relationship('Feedback', backref='user', lazy='dynamic',
                                  foreign_keys='Feedback.user_id')

    def set_password(self, raw):
        self.password_hash = bcrypt.generate_password_hash(raw).decode()

    def check_password(self, raw):
        try:
            return bcrypt.check_password_hash(self.password_hash, raw)
        except Exception:
            return False

    @property
    def is_company_admin(self):
        return self.role == 'admin'

    @property
    def is_ceo(self):
        return self.role == 'ceo'

    @property
    def is_president(self):
        return self.role == 'president'

    @property
    def is_staff(self):
        return self.role in ('admin', 'ceo', 'president')


class Section(db.Model):
    __tablename__ = 'sections'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    group = db.Column(db.String(60), default='General', index=True)
    icon = db.Column(db.String(10), default='📄')
    description = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pdfs = db.relationship('PDFNote', backref='section', lazy='dynamic',
                            cascade='all, delete-orphan')


class PDFNote(db.Model):
    __tablename__ = 'pdf_notes'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'),
                            nullable=False, index=True)
    subcategory = db.Column(db.String(40), default='notes')
    price = db.Column(db.Float, nullable=False, default=49.0)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    total_pages = db.Column(db.Integer, default=0)
    icon = db.Column(db.String(10), default='📄')
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_featured = db.Column(db.Boolean, default=False)

    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    purchases = db.relationship('Purchase', backref='pdf', lazy='dynamic',
                                  cascade='all, delete-orphan')

    @property
    def is_free(self):
        return self.price <= 0


class Purchase(db.Model):
    __tablename__ = 'purchases'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                         nullable=False, index=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_notes.id'),
                        nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default='pending', index=True)

    method = db.Column(db.String(30))
    razorpay_order_id = db.Column(db.String(120), index=True)
    razorpay_payment_id = db.Column(db.String(120))
    razorpay_signature = db.Column(db.String(255))
    upi_reference = db.Column(db.String(120))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    completed_at = db.Column(db.DateTime)
    ip_address = db.Column(db.String(45))

    __table_args__ = (
        Index('ix_purchase_user_pdf_status', 'user_id', 'pdf_id', 'status'),
    )


class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                         nullable=True, index=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(160))
    mobile = db.Column(db.String(15))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='new', index=True)
    admin_reply = db.Column(db.Text)
    replied_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    replied_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    detail = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    severity = db.Column(db.String(20), default='info', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class CEOInviteCode(db.Model):
    __tablename__ = 'ceo_invite_codes'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    used_at = db.Column(db.DateTime)

    @property
    def is_valid(self):
        if self.used:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


class SiteSetting(db.Model):
    __tablename__ = 'site_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow)


# ============================================================
# PASSWORD RESET OTP TABLE (NEW)
# ============================================================
class PasswordResetOTP(db.Model):
    __tablename__ = 'password_reset_otps'
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(15), nullable=False, index=True)
    otp_hash = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(30), default='user', index=True)  # 'user' ya 'staff'
    attempts = db.Column(db.Integer, default=0)
    ip_address = db.Column(db.String(45))
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def is_valid(self):
        if self.used:
            return False
        if self.attempts >= 5:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True
    
    @property
    def is_valid(self):
        if self.used:
            return False
        if self.attempts >= 10:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True


class PaymentMethod(db.Model):
    __tablename__ = 'payment_methods'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    method_type = db.Column(db.String(30), default='upi')
    upi_id = db.Column(db.String(120))
    account_name = db.Column(db.String(120))
    account_number = db.Column(db.String(60))
    ifsc_code = db.Column(db.String(20))
    bank_name = db.Column(db.String(80))
    instructions = db.Column(db.Text)
    icon = db.Column(db.String(10), default='💳')
    is_active = db.Column(db.Boolean, default=True, index=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# USER LOADER
# ============================================================
@login_manager.user_loader
def load_user(uid):
    try:
        return User.query.get(int(uid))
    except Exception:
        return None


# ============================================================
# ACTIVITY LOGGING
# ============================================================
def log_activity(action, detail='', severity='info', user_id=None):
    try:
        uid = user_id
        if uid is None and current_user and current_user.is_authenticated:
            uid = current_user.id
        log = ActivityLog(
            user_id=uid,
            action=action,
            detail=detail[:1000] if detail else '',
            ip_address=request.remote_addr if request else '',
            user_agent=(request.user_agent.string[:255]
                        if request and request.user_agent else ''),
            severity=severity
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"[log_activity error] {e}")
        try:
            db.session.rollback()
        except Exception:
            pass


# ============================================================
# ACCESS DECORATORS
# ============================================================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Pehle login karein.', 'warning')
            return redirect(url_for('admin_login'))
        if current_user.role not in ('admin', 'ceo', 'president'):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def ceo_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('ceo_login'))
        if current_user.role != 'ceo':
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def president_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('president_login'))
        if current_user.role != 'president':
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ============================================================
# RATE LIMITING
# ============================================================
_attempt_store = {}


def record_attempt(identifier):
    now = datetime.utcnow().timestamp()
    count, first = _attempt_store.get(identifier, (0, now))
    _attempt_store[identifier] = (count + 1, first)


def is_locked_out(identifier):
    if identifier not in _attempt_store:
        return False
    count, first = _attempt_store[identifier]
    if count < 5:
        return False
    elapsed_min = (datetime.utcnow().timestamp() - first) / 60
    if elapsed_min > 15:
        _attempt_store.pop(identifier, None)
        return False
    return True


def clear_attempts(identifier):
    _attempt_store.pop(identifier, None)


# ============================================================
# TEMPLATE FILTERS
# ============================================================
@app.template_filter('inr')
def inr_filter(v):
    try:
        return f"₹{int(float(v))}"
    except Exception:
        return "₹0"


@app.template_filter('humandate')
def humandate_filter(dt):
    if not dt:
        return '—'
    try:
        return dt.strftime('%d %b %Y, %I:%M %p')
    except Exception:
        return '—'


@app.context_processor
def inject_globals():
    return dict(
        COMPANY_NAME=COMPANY_NAME,
        COMPANY_LEGAL=COMPANY_LEGAL,
        COMPANY_EMAIL=COMPANY_EMAIL,
        COMPANY_PHONE=COMPANY_PHONE,
        FREE_PREVIEW_PAGES=FREE_PREVIEW_PAGES,
        current_year=datetime.utcnow().year,
    )


# ============================================================
# INIT DEFAULTS
# ============================================================
DEFAULT_SECTIONS = [
    ('class_4',  'Class 4',  'School',  '📗', 1),
    ('class_5',  'Class 5',  'School',  '📗', 2),
    ('class_6',  'Class 6',  'School',  '📘', 3),
    ('class_7',  'Class 7',  'School',  '📘', 4),
    ('class_8',  'Class 8',  'School',  '📙', 5),
    ('class_9',  'Class 9',  'School',  '📙', 6),
    ('class_10', 'Class 10', 'School',  '📕', 7),
    ('class_11', 'Class 11', 'School',  '📕', 8),
    ('class_12', 'Class 12', 'School',  '📕', 9),
    ('ssc_gd',   'SSC GD',   'SSC',     '🎯', 10),
    ('ssc_mts',  'SSC MTS',  'SSC',     '🎯', 11),
    ('ssc_chsl', 'SSC CHSL', 'SSC',     '🎯', 12),
    ('ssc_cgl',  'SSC CGL',  'SSC',     '🎯', 13),
    ('assam_police_constable', 'Assam Police Constable', 'Assam', '🚔', 14),
    ('assam_police_si',        'Assam Police SI',        'Assam', '🚔', 15),
    ('assam_other',            'Assam Other Exams',      'Assam', '🏛️', 16),
    ('upsc',      'UPSC',            'UPSC',    '🏆', 17),
    ('assam_pcs', 'Assam PCS (APSC)','UPSC',    '🏆', 18),
    ('banking',   'Banking',         'Banking', '🏦', 19),
]


def init_defaults():
    with app.app_context():
        db.create_all()

        for slug, name, group, icon, order in DEFAULT_SECTIONS:
            if not Section.query.filter_by(slug=slug).first():
                db.session.add(Section(slug=slug, name=name, group=group,
                                        icon=icon, display_order=order))
        db.session.commit()

        pres = User.query.filter_by(mobile=PRESIDENT_MOBILE,
                                     role='president').first()
        if not pres:
            pres = User(
                full_name=PRESIDENT_NAME,
                email='president@omnicart.local',
                mobile=PRESIDENT_MOBILE,
                role='president',
                email_verified=True,
                mobile_verified=True,
                must_change_password=True,
            )
            pres.set_password('__TEMP__' + PRESIDENT_MOBILE)
            db.session.add(pres)
            db.session.commit()
            print("=" * 60)
            print("  PRESIDENT ACCOUNT CREATED")
            print(f"  Mobile  : {PRESIDENT_MOBILE}")
            print(f"  Password: __TEMP__{PRESIDENT_MOBILE}")
            print("=" * 60)


# ============================================================
# OWNERSHIP CHECK
# ============================================================
def user_owns_pdf(user, pdf_id):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_staff', False):
        return True
    return Purchase.query.filter_by(
        user_id=user.id, pdf_id=pdf_id, status='completed'
    ).first() is not None
# ============================================================
# USER ROUTES
# ============================================================

@app.route('/')
def user_home():
    featured = PDFNote.query.filter_by(is_active=True)\
        .order_by(func.random()).limit(12).all()
    sections = Section.query.filter_by(is_active=True)\
        .order_by(Section.display_order).all()
    total = PDFNote.query.filter_by(is_active=True).count()

    section_data = []
    for s in sections:
        count = PDFNote.query.filter_by(section_id=s.id, is_active=True).count()
        section_data.append({'section': s, 'count': count})

    return render_template('user/home.html', featured=featured,
                            sections=section_data, total=total,
                            page_title="Home")


@app.route('/search')
def user_search():
    q = request.args.get('q', '').strip()
    results = []
    if q:
        like = f"%{q}%"
        results = PDFNote.query.filter(
            PDFNote.is_active == True,
            or_(PDFNote.title.ilike(like),
                PDFNote.description.ilike(like))
        ).limit(100).all()

    return render_template('user/search.html', q=q, results=results,
                            page_title=f'Search: {q}')


@app.route('/category/<slug>')
def user_category(slug):
    section = Section.query.filter_by(slug=slug, is_active=True).first()
    if not section:
        abort(404)

    sub = request.args.get('sub', '')
    query = PDFNote.query.filter_by(section_id=section.id, is_active=True)
    if sub:
        query = query.filter_by(subcategory=sub)
    pdfs = query.order_by(PDFNote.created_at.desc()).all()

    return render_template('user/category.html', section=section,
                            pdfs=pdfs, current_sub=sub,
                            page_title=section.name)


@app.route('/pdf/<int:pdf_id>')
def user_pdf_view(pdf_id):
    pdf = PDFNote.query.get_or_404(pdf_id)

    if not pdf.is_active:
        if not (current_user.is_authenticated and current_user.is_staff):
            abort(404)

    owns = user_owns_pdf(current_user, pdf_id)
    section_name = pdf.section.name if pdf.section else ''

    if current_user.is_authenticated:
        log_activity('pdf_view', f'PDF #{pdf.id} viewed')

    return render_template('user/pdf_view.html', pdf=pdf, owns=owns,
                            section_name=section_name,
                            page_title=pdf.title)


@app.route('/pdf/stream/<int:pdf_id>')
def user_pdf_stream(pdf_id):
    pdf = PDFNote.query.get_or_404(pdf_id)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf.filename)

    if not os.path.exists(file_path):
        abort(404)

    if user_owns_pdf(current_user, pdf_id):
        return send_file(file_path, mimetype='application/pdf')

    buf = truncate_pdf(file_path, max_pages=FREE_PREVIEW_PAGES)
    if buf:
        return send_file(buf, mimetype='application/pdf')

    return send_file(file_path, mimetype='application/pdf')


@app.route('/pdf/download/<int:pdf_id>')
@login_required
def user_pdf_download(pdf_id):
    pdf = PDFNote.query.get_or_404(pdf_id)

    if not user_owns_pdf(current_user, pdf_id):
        flash('Pehle purchase karein.', 'warning')
        return redirect(url_for('user_pdf_view', pdf_id=pdf_id))

    fp = os.path.join(app.config['UPLOAD_FOLDER'], pdf.filename)
    if not os.path.exists(fp):
        abort(404)

    log_activity('pdf_download', f'PDF #{pdf.id} downloaded')

    return send_file(fp, mimetype='application/pdf', as_attachment=True,
                     download_name=pdf.original_filename or 'notes.pdf')


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/signup', methods=['GET', 'POST'])
def user_signup():
    if current_user.is_authenticated:
        return redirect(url_for('user_home'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        errs = []
        if not all([full_name, email, mobile, password, confirm]):
            errs.append('Sabhi fields bharein.')
        if email and not valid_email(email):
            errs.append('Sahi email daalein.')
        if mobile and not valid_mobile(mobile):
            errs.append('Sahi 10-digit mobile daalein (6-9 se shuru).')
        if password:
            for e in password_errors(password):
                errs.append(e)
        if password != confirm:
            errs.append('Passwords match nahi kar rahe.')
        if email and User.query.filter_by(email=email).first():
            errs.append('Yeh email already registered hai.')
        if mobile and User.query.filter_by(mobile=mobile).first():
            errs.append('Yeh mobile already registered hai.')

        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('user_signup'))

        u = User(full_name=full_name, email=email, mobile=mobile, role='user')
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

        log_activity('user_signup', f'New user: {email}', user_id=u.id)
        flash('Account ban gaya! Login karein.', 'success')
        return redirect(url_for('user_login'))

    return render_template('user/signup.html', page_title="Sign Up")
@app.route('/api/signup/send-email-otp', methods=['POST'])
def api_signup_send_email_otp():
    """Email OTP bhejo — AJAX."""
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()

    if not valid_email(email):
        return jsonify({'error': 'Sahi email daalein.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Yeh email already registered hai.'}), 400

    # Rate limit
    recent = SignupOTP.query.filter(
        SignupOTP.email == email,
        SignupOTP.created_at >= datetime.utcnow() - timedelta(minutes=15)
    ).count()
    if recent >= 5:
        return jsonify({'error': 'Bahut zyada requests. 15 min baad try karein.'}), 429

    # OTP generate
    otp = generate_otp(6)

    record = SignupOTP.query.filter_by(email=email, used=False).first()
    if not record:
        record = SignupOTP(
            email=email,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            ip_address=request.remote_addr or ''
        )
        db.session.add(record)

    record.email_otp_hash = bcrypt.generate_password_hash(otp).decode()
    record.expires_at = datetime.utcnow() + timedelta(minutes=5)
    record.attempts = 0
    db.session.commit()

    send_otp_email(email, otp, 'User')

    return jsonify({
        'status': 'ok',
        'message': f'OTP bhej diya {email} pe. 5 min me valid.'
    })


@app.route('/api/signup/verify-email-otp', methods=['POST'])
def api_signup_verify_email_otp():
    """Email OTP verify karo — AJAX."""
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    otp = data.get('otp', '').strip()

    if not valid_email(email) or not otp:
        return jsonify({'error': 'Email aur OTP required.'}), 400

    record = SignupOTP.query.filter_by(email=email, used=False)\
        .order_by(SignupOTP.created_at.desc()).first()

    if not record or not record.is_valid:
        return jsonify({'error': 'OTP expire. Dobara bhejein.'}), 400

    if not bcrypt.check_password_hash(record.email_otp_hash, otp):
        record.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Galat OTP.'}), 400

    return jsonify({'status': 'ok', 'message': 'Email verified ✅'})


@app.route('/login', methods=['GET', 'POST'])
def user_login():
    if current_user.is_authenticated:
        return redirect(url_for('user_home'))

    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')

        if is_locked_out(mobile):
            flash('Bahut zyada attempts. 15 min baad try karein.', 'danger')
            return redirect(url_for('user_login'))

        u = User.query.filter_by(mobile=mobile).first()

        if u and u.check_password(password):
            if u.is_banned:
                flash('Aapka account banned hai.', 'danger')
                return redirect(url_for('user_login'))

            clear_attempts(mobile)
            u.last_login = datetime.utcnow()
            db.session.commit()
            login_user(u, remember=True)

            log_activity('login', f'User {u.role} logged in', user_id=u.id)

            if u.role == 'president':
                if u.must_change_password:
                    return redirect(url_for('president_change_password'))
                return redirect(url_for('staff_dashboard'))
            if u.role in ('ceo', 'admin'):
                return redirect(url_for('staff_dashboard'))
            return redirect(url_for('user_home'))

        record_attempt(mobile)
        flash('Galat mobile ya password.', 'danger')

    return render_template('user/login.html', page_title="Login")


@app.route('/logout')
@login_required
def user_logout():
    log_activity('logout', 'User logged out')
    logout_user()
    flash('Logout ho gaye.', 'success')
    return redirect(url_for('user_home'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def user_forgot_password():
    """Step 1: Mobile number lo, OTP bhejo."""
    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()

        if not valid_mobile(mobile):
            flash('Sahi 10-digit mobile daalein.', 'danger')
            return redirect(url_for('user_forgot_password'))

        # Rate limit: 3 OTP per 15 min per mobile
        recent_count = PasswordResetOTP.query.filter(
            PasswordResetOTP.mobile == mobile,
            PasswordResetOTP.purpose == 'user',
            PasswordResetOTP.created_at >= datetime.utcnow() - timedelta(minutes=15)
        ).count()

        if recent_count >= 3:
            flash('Bahut zyada OTP requests. 15 min baad try karein.', 'warning')
            return redirect(url_for('user_forgot_password'))

        u = User.query.filter_by(mobile=mobile, role='user').first()

        # Security: Agar user exist nahi karta to bhi generic message
        if u:
            create_otp_for_reset(mobile, purpose='user')
            log_activity('otp_sent', f'Password reset OTP sent to {mobile}',
                         severity='warning')

        # Generic message (user enumeration rok)
        flash('Agar account exist karta hai to OTP bhej diya gaya. 10 min me valid hai.',
              'info')

        # Session me mobile store karo next step ke liye
        session['reset_mobile'] = mobile
        session['reset_purpose'] = 'user'
        return redirect(url_for('user_verify_otp'))

    return render_template('base.html', page_title="Forgot Password")


@app.route('/verify-otp', methods=['GET', 'POST'])
def user_verify_otp():
    """Step 2: OTP verify karo, naya password set karo."""
    mobile = session.get('reset_mobile')
    purpose = session.get('reset_purpose', 'user')

    if not mobile:
        flash('Pehle mobile number daalein.', 'warning')
        return redirect(url_for('user_forgot_password'))

    if request.method == 'POST':
        otp = request.form.get('otp', '').strip()
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        # Validate inputs
        if not otp or len(otp) != 6 or not otp.isdigit():
            flash('6-digit OTP daalein.', 'danger')
            return redirect(url_for('user_verify_otp'))

        # Latest active OTP find karo
        otp_record = PasswordResetOTP.query.filter_by(
            mobile=mobile, purpose=purpose, used=False
        ).order_by(PasswordResetOTP.created_at.desc()).first()

        if not otp_record:
            flash('Koi active OTP nahi mila. Naya request karein.', 'danger')
            return redirect(url_for('user_forgot_password'))

        if not otp_record.is_valid:
            if otp_record.attempts >= 5:
                flash('Bahut zyada galat attempts. Naya OTP request karein.', 'danger')
            else:
                flash('OTP expire ho gaya. Naya request karein.', 'danger')
            return redirect(url_for('user_forgot_password'))

        # OTP verify
        if not bcrypt.check_password_hash(otp_record.otp_hash, otp):
            otp_record.attempts += 1
            db.session.commit()

            remaining = 5 - otp_record.attempts
            log_activity('otp_fail',
                         f'Wrong OTP attempt for {mobile}. {remaining} left',
                         severity='warning')
            flash(f'Galat OTP. {remaining} attempts bache hain.', 'danger')
            return redirect(url_for('user_verify_otp'))

        # OTP sahi hai — ab password validate karo
        errs = password_errors(new_pw)
        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('user_verify_otp'))

        if new_pw != confirm:
            flash('Passwords match nahi kar rahe.', 'danger')
            return redirect(url_for('user_verify_otp'))

        # User find karo
        u = User.query.filter_by(mobile=mobile, role='user').first()
        if not u:
            flash('Account nahi mila.', 'danger')
            return redirect(url_for('user_forgot_password'))

        # Password reset
        u.set_password(new_pw)
        otp_record.used = True
        db.session.commit()

        # Session clear
        session.pop('reset_mobile', None)
        session.pop('reset_purpose', None)

        log_activity('password_reset_success',
                     f'User {u.id} ({mobile}) reset password via OTP',
                     severity='warning')

        flash('✅ Password reset ho gaya! Ab login karein.', 'success')
        return redirect(url_for('user_login'))

    return render_template('base.html', page_title="Verify OTP")


# ============================================================
# ACCOUNT
# ============================================================
@app.route('/account')
@login_required
def user_account():
    purchases_count = Purchase.query.filter_by(
        user_id=current_user.id, status='completed'
    ).count()

    return render_template('user/account.html',
                            purchases_count=purchases_count,
                            page_title="My Account")


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def user_change_password():
    if request.method == 'POST':
        old_pw = request.form.get('old_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        if not current_user.check_password(old_pw):
            flash('Purana password galat hai.', 'danger')
            return redirect(url_for('user_change_password'))

        errs = password_errors(new_pw)
        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('user_change_password'))
        if new_pw != confirm:
            flash('Passwords match nahi kar rahe.', 'danger')
            return redirect(url_for('user_change_password'))

        current_user.set_password(new_pw)
        current_user.must_change_password = False
        db.session.commit()

        log_activity('password_change', 'User changed password')
        flash('Password change ho gaya.', 'success')
        return redirect(url_for('user_account'))

    return render_template('user/change_password.html', page_title="Change Password")


@app.route('/my-purchases')
@login_required
def user_my_purchases():
    purchases = Purchase.query.filter_by(
        user_id=current_user.id, status='completed'
    ).order_by(Purchase.completed_at.desc()).all()

    purchased_pdfs = [p.pdf for p in purchases if p.pdf]

    return render_template('user/my_purchases.html', purchases=purchases,
                            pdfs=purchased_pdfs,
                            page_title="My Purchases")


@app.route('/my-pending-orders')
@login_required
def user_pending_orders():
    purchases = Purchase.query.filter(
        Purchase.user_id == current_user.id,
        Purchase.status.in_(['pending', 'awaiting_verification'])
    ).order_by(Purchase.created_at.desc()).all()

    return render_template('user/pending_orders.html', purchases=purchases,
                            page_title="Pending Orders")


# ============================================================
# SETTINGS
# ============================================================
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    if request.method == 'POST':
        privacy = request.form.get('privacy_level', 'normal')
        notif = request.form.get('notifications_enabled') == 'on'

        if privacy not in ('normal', 'high', 'maximum'):
            privacy = 'normal'

        current_user.privacy_level = privacy
        current_user.notifications_enabled = notif
        db.session.commit()

        log_activity('settings_update', 'Privacy settings updated')
        flash('Privacy settings save ho gayi.', 'success')
        return redirect(url_for('user_settings'))

    return render_template('user/settings.html', page_title="Settings")


@app.route('/api/settings/theme', methods=['POST'])
@login_required
def api_save_theme():
    data = request.get_json() or {}
    theme = data.get('theme', 'light')
    if theme not in ('light', 'dark', 'ocean', 'forest', 'sunset', 'royal'):
        return jsonify({'error': 'Invalid theme'}), 400
    current_user.theme = theme
    db.session.commit()
    return jsonify({'status': 'ok', 'theme': theme})


@app.route('/api/settings/language', methods=['POST'])
@login_required
def api_save_language():
    data = request.get_json() or {}
    lang = data.get('language', 'en')
    allowed = ('en', 'hi', 'as', 'te', 'pa', 'or')
    if lang not in allowed:
        return jsonify({'error': 'Invalid language'}), 400
    current_user.language = lang
    db.session.commit()
    return jsonify({'status': 'ok', 'language': lang})


# ============================================================
# INFO PAGES
# ============================================================
@app.route('/contact')
def user_contact():
    return render_template('user/contact.html', page_title="Contact Us",
                            company_phone=COMPANY_PHONE,
                            company_email=COMPANY_EMAIL,
                            company_legal=COMPANY_LEGAL)


@app.route('/feedback', methods=['GET', 'POST'])
def user_feedback():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        mobile = request.form.get('mobile', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not message:
            flash('Message khali nahi ho sakta.', 'danger')
            return redirect(url_for('user_feedback'))

        if not name:
            if current_user.is_authenticated:
                name = current_user.full_name
            else:
                flash('Apna naam likhein.', 'danger')
                return redirect(url_for('user_feedback'))

        fb = Feedback(
            user_id=current_user.id if current_user.is_authenticated else None,
            name=name,
            email=email or (current_user.email if current_user.is_authenticated else None),
            mobile=mobile or (current_user.mobile if current_user.is_authenticated else None),
            subject=subject or 'General Feedback',
            message=message,
        )
        db.session.add(fb)
        db.session.commit()

        log_activity('feedback_submit', f'Feedback #{fb.id}')
        flash('Feedback submit ho gaya! Hum jald reply karenge.', 'success')
        return redirect(url_for('user_feedback'))

    return render_template('user/feedback.html', page_title="Feedback")


@app.route('/terms')
def user_terms():
    return render_template('user/terms.html', page_title="Terms & Conditions",
                            company_legal=COMPANY_LEGAL,
                            company_email=COMPANY_EMAIL,
                            company_phone=COMPANY_PHONE,
                            free_pages=FREE_PREVIEW_PAGES)


@app.route('/about')
def user_about():
    return render_template('user/about.html', page_title="About Us",
                            company_legal=COMPANY_LEGAL,
                            free_pages=FREE_PREVIEW_PAGES)


# ============================================================
# ADMIN LOGIN
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and current_user.role in ('admin', 'ceo', 'president'):
        return redirect(url_for('staff_dashboard'))
    

    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')

        if is_locked_out('admin_' + mobile):
            flash('Bahut zyada attempts. 15 min baad try karein.', 'danger')
            return redirect(url_for('admin_login'))

        u = User.query.filter_by(mobile=mobile).first()

        if u and u.check_password(password):
            if u.role not in ('admin', 'ceo', 'president'):
                log_activity('admin_login_denied',
                             f'Non-admin tried admin login: {mobile}',
                             severity='warning')
                flash('Aap admin nahi hain.', 'danger')
                return redirect(url_for('admin_login'))

            if u.is_banned:
                flash('Aapka account banned hai.', 'danger')
                return redirect(url_for('admin_login'))

            clear_attempts('admin_' + mobile)
            u.last_login = datetime.utcnow()
            db.session.commit()
            login_user(u, remember=True)

            log_activity('admin_login', f'{u.role} logged into admin panel', user_id=u.id)
            if u.role == 'president' and u.must_change_password:
                return redirect(url_for('president_change_password'))

            return redirect(url_for('staff_dashboard'))

        record_attempt('admin_' + mobile)
        flash('Galat mobile ya password.', 'danger')

    return render_template('admin/login.html', page_title="Admin Login")
@app.route('/staff/forgot-password', methods=['GET', 'POST'])
def staff_forgot_password():
    """Step 1 (Staff): Mobile number lo, OTP bhejo."""
    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()

        if not valid_mobile(mobile):
            flash('Valid 10-digit mobile daalein.', 'danger')
            return redirect(url_for('staff_forgot_password'))

        # Rate limit
        recent_count = PasswordResetOTP.query.filter(
            PasswordResetOTP.mobile == mobile,
            PasswordResetOTP.purpose == 'staff',
            PasswordResetOTP.created_at >= datetime.utcnow() - timedelta(minutes=15)
        ).count()

        if recent_count >= 3:
            flash('Bahut zyada OTP requests. 15 min baad try karein.', 'warning')
            return redirect(url_for('staff_forgot_password'))

        u = User.query.filter_by(mobile=mobile).first()

        # Sirf staff members allowed
        if u and u.role in ('admin', 'ceo', 'president'):
            create_otp_for_reset(mobile, purpose='staff')
            log_activity('staff_otp_sent',
                         f'Staff password reset OTP sent to {mobile}',
                         severity='critical')

        # Generic message
        flash('Agar staff account exist karta hai to OTP bhej diya gaya.',
              'info')

        session['reset_mobile'] = mobile
        session['reset_purpose'] = 'staff'
        return redirect(url_for('staff_verify_otp'))

    return render_template('base.html', page_title="Staff Password Reset")


@app.route('/staff/verify-otp', methods=['GET', 'POST'])
def staff_verify_otp():
    """Step 2 (Staff): OTP verify karo, naya password set karo."""
    mobile = session.get('reset_mobile')
    purpose = session.get('reset_purpose')

    if not mobile or purpose != 'staff':
        flash('Pehle mobile number daalein.', 'warning')
        return redirect(url_for('staff_forgot_password'))

    if request.method == 'POST':
        otp = request.form.get('otp', '').strip()
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        if not otp or len(otp) != 6 or not otp.isdigit():
            flash('6-digit OTP daalein.', 'danger')
            return redirect(url_for('staff_verify_otp'))

        otp_record = PasswordResetOTP.query.filter_by(
            mobile=mobile, purpose='staff', used=False
        ).order_by(PasswordResetOTP.created_at.desc()).first()

        if not otp_record or not otp_record.is_valid:
            flash('OTP invalid ya expire. Naya request karein.', 'danger')
            return redirect(url_for('staff_forgot_password'))

        if not bcrypt.check_password_hash(otp_record.otp_hash, otp):
            otp_record.attempts += 1
            db.session.commit()
            remaining = 5 - otp_record.attempts
            log_activity('staff_otp_fail',
                         f'Wrong staff OTP for {mobile}. {remaining} left',
                         severity='critical')
            flash(f'Galat OTP. {remaining} attempts bache hain.', 'danger')
            return redirect(url_for('staff_verify_otp'))

        errs = password_errors(new_pw)
        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('staff_verify_otp'))

        if new_pw != confirm:
            flash('Passwords match nahi kar rahe.', 'danger')
            return redirect(url_for('staff_verify_otp'))

        u = User.query.filter_by(mobile=mobile).first()
        if not u or u.role not in ('admin', 'ceo', 'president'):
            flash('Staff account nahi mila.', 'danger')
            return redirect(url_for('staff_forgot_password'))

        u.set_password(new_pw)
        otp_record.used = True
        db.session.commit()

        session.pop('reset_mobile', None)
        session.pop('reset_purpose', None)

        log_activity('staff_password_reset',
                     f'Staff #{u.id} ({u.role}) reset password via OTP',
                     severity='critical')

        flash('✅ Password reset ho gaya! Ab login karein.', 'success')
        return redirect(url_for('admin_login'))

    return render_template('base.html', page_title="Staff OTP Verify")

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    return redirect(url_for('staff_dashboard'))


# ============================================================
# ADMIN LEGACY ROUTES (redirects)
# ============================================================
@app.route('/admin/upload', methods=['GET', 'POST'])
@login_required
def admin_upload():
    return redirect(url_for('staff_upload'))


@app.route('/admin/pdfs')
@login_required
def admin_pdfs():
    return redirect(url_for('staff_products'))


@app.route('/admin/pdf/<int:pdf_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_pdf_edit(pdf_id):
    return redirect(url_for('staff_pdf_edit', pdf_id=pdf_id))


@app.route('/admin/pdf/<int:pdf_id>/toggle', methods=['POST'])
@login_required
def admin_pdf_toggle(pdf_id):
    return redirect(url_for('staff_pdf_toggle', pdf_id=pdf_id), code=307)


@app.route('/admin/pdf/<int:pdf_id>/delete', methods=['POST'])
@login_required
def admin_pdf_delete(pdf_id):
    return redirect(url_for('staff_pdf_delete', pdf_id=pdf_id), code=307)


@app.route('/admin/sections')
@login_required
def admin_sections():
    return redirect(url_for('staff_categories'))


@app.route('/admin/section/create', methods=['GET', 'POST'])
@login_required
def admin_section_create():
    return redirect(url_for('staff_section_create'))


@app.route('/admin/section/<int:section_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_section_edit(section_id):
    return redirect(url_for('staff_section_edit', section_id=section_id))


@app.route('/admin/section/<int:section_id>/delete', methods=['POST'])
@login_required
def admin_section_delete(section_id):
    return redirect(url_for('staff_section_delete', section_id=section_id), code=307)


@app.route('/admin/orders')
@login_required
def admin_orders():
    return redirect(url_for('staff_orders'))


@app.route('/admin/order/<int:order_id>')
@login_required
def admin_order_detail(order_id):
    return redirect(url_for('staff_order_detail', order_id=order_id))


@app.route('/admin/order/<int:order_id>/verify', methods=['POST'])
@login_required
def admin_order_verify(order_id):
    return redirect(url_for('staff_order_verify', order_id=order_id), code=307)


@app.route('/admin/order/<int:order_id>/fail', methods=['POST'])
@login_required
def admin_order_fail(order_id):
    return redirect(url_for('staff_order_fail', order_id=order_id), code=307)


@app.route('/admin/order/<int:order_id>/refund', methods=['POST'])
@login_required
def admin_order_refund(order_id):
    return redirect(url_for('staff_order_refund', order_id=order_id), code=307)


@app.route('/admin/users')
@login_required
def admin_users():
    return redirect(url_for('staff_customers'))


@app.route('/admin/user/<int:user_id>')
@login_required
def admin_user_detail(user_id):
    return redirect(url_for('staff_user_detail', user_id=user_id))


@app.route('/admin/user/<int:user_id>/ban', methods=['POST'])
@login_required
def admin_user_ban(user_id):
    return redirect(url_for('staff_user_ban', user_id=user_id), code=307)


@app.route('/admin/user/<int:user_id>/unban', methods=['POST'])
@login_required
def admin_user_unban(user_id):
    return redirect(url_for('staff_user_unban', user_id=user_id), code=307)


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_user_delete(user_id):
    flash('User delete sirf President kar sakte hain.', 'warning')
    return redirect(url_for('staff_customers'))


@app.route('/admin/feedback')
@login_required
def admin_feedback():
    return redirect(url_for('staff_feedback'))


@app.route('/admin/feedback/<int:fb_id>')
@login_required
def admin_feedback_detail(fb_id):
    return redirect(url_for('staff_feedback_detail', fb_id=fb_id))


@app.route('/admin/feedback/<int:fb_id>/reply', methods=['POST'])
@login_required
def admin_feedback_reply(fb_id):
    return redirect(url_for('staff_feedback_reply', fb_id=fb_id), code=307)


@app.route('/admin/feedback/<int:fb_id>/delete', methods=['POST'])
@login_required
def admin_feedback_delete(fb_id):
    return redirect(url_for('staff_feedback_delete', fb_id=fb_id), code=307)


@app.route('/admin/activity')
@login_required
def admin_activity():
    return redirect(url_for('staff_activity'))


@app.route('/admin/activity/clear', methods=['POST'])
@login_required
def admin_activity_clear():
    return redirect(url_for('staff_activity_clear'), code=307)


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    return redirect(url_for('staff_settings'))


# ============================================================
# CEO ROUTES
# ============================================================
@app.route('/ceo/signup', methods=['GET', 'POST'])
def ceo_signup():
    if current_user.is_authenticated:
        return redirect(url_for('user_home'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        invite_code = request.form.get('invite_code', '').strip().upper()

        errs = []
        if not all([full_name, email, mobile, password, confirm, invite_code]):
            errs.append('Sabhi fields bharein.')
        if email and not valid_email(email):
            errs.append('Sahi email daalein.')
        if mobile and not valid_mobile(mobile):
            errs.append('Sahi 10-digit mobile daalein (6-9 se shuru).')
        if password:
            for e in password_errors(password):
                errs.append(e)
        if password != confirm:
            errs.append('Passwords match nahi kar rahe.')

        invite_obj = None
        if invite_code:
            invite_obj = CEOInviteCode.query.filter_by(code=invite_code).first()
            if not invite_obj:
                errs.append('Invalid CEO invite code.')
            elif not invite_obj.is_valid:
                if invite_obj.used:
                    errs.append('Yeh invite code already use ho chuka hai.')
                else:
                    errs.append('Yeh invite code expire ho gaya hai.')

        if email and User.query.filter_by(email=email).first():
            errs.append('Yeh email already registered hai.')
        if mobile and User.query.filter_by(mobile=mobile).first():
            errs.append('Yeh mobile already registered hai.')

        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('ceo_signup'))

        u = User(
            full_name=full_name,
            email=email,
            mobile=mobile,
            role='ceo',
            email_verified=True,
            mobile_verified=True,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.flush()

        invite_obj.used = True
        invite_obj.used_by = u.id
        invite_obj.used_at = datetime.utcnow()

        db.session.commit()

        log_activity('ceo_signup',
                     f'CEO account created: {email} (via code {invite_code})',
                     severity='warning', user_id=u.id)

        flash('CEO account ban gaya! Ab login karein.', 'success')
        return redirect(url_for('ceo_login'))

    return render_template('ceo/signup.html', page_title="CEO Signup")


@app.route('/ceo/login', methods=['GET', 'POST'])
def ceo_login():
    if current_user.is_authenticated and current_user.role == 'ceo':
        return redirect(url_for('staff_dashboard'))

    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')

        if is_locked_out('ceo_' + mobile):
            flash('Bahut zyada attempts. 15 min baad try karein.', 'danger')
            return redirect(url_for('ceo_login'))

        u = User.query.filter_by(mobile=mobile, role='ceo').first()

        if u and u.check_password(password):
            if u.is_banned:
                flash('Aapka account banned hai.', 'danger')
                return redirect(url_for('ceo_login'))

            clear_attempts('ceo_' + mobile)
            u.last_login = datetime.utcnow()
            db.session.commit()
            login_user(u, remember=True)

            log_activity('ceo_login', 'CEO logged in', user_id=u.id)
            return redirect(url_for('staff_dashboard'))

        record_attempt('ceo_' + mobile)
        flash('Galat mobile ya password.', 'danger')

    return render_template('ceo/login.html', page_title="CEO Login")


@app.route('/ceo/dashboard')
@login_required
@ceo_required
def ceo_dashboard():
    return redirect(url_for('staff_dashboard'))


@app.route('/ceo/admins')
@login_required
@ceo_required
def ceo_admins():
    return redirect(url_for('staff_team'))


@app.route('/ceo/admin/create', methods=['GET', 'POST'])
@login_required
@ceo_required
def ceo_admin_create():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        errs = []
        if not all([full_name, email, mobile, password, confirm]):
            errs.append('Sabhi fields bharein.')
        if email and not valid_email(email):
            errs.append('Sahi email daalein.')
        if mobile and not valid_mobile(mobile):
            errs.append('Sahi 10-digit mobile daalein.')
        if password:
            for e in password_errors(password):
                errs.append(e)
        if password != confirm:
            errs.append('Passwords match nahi kar rahe.')
        if email and User.query.filter_by(email=email).first():
            errs.append('Yeh email already registered hai.')
        if mobile and User.query.filter_by(mobile=mobile).first():
            errs.append('Yeh mobile already registered hai.')

        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('ceo_admin_create'))

        u = User(
            full_name=full_name,
            email=email,
            mobile=mobile,
            role='admin',
            email_verified=True,
            mobile_verified=True,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

        log_activity('admin_create',
                     f'CEO created admin: {email}',
                     severity='warning', user_id=u.id)

        flash(f'Admin "{full_name}" ban gaya.', 'success')
        return redirect(url_for('staff_team'))

    return render_template('ceo/admin_create.html', page_title="Create Admin")


@app.route('/ceo/admin/<int:admin_id>/promote', methods=['POST'])
@login_required
@ceo_required
def ceo_admin_promote(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.role != 'admin':
        flash('Sirf admin ko promote kar sakte hain.', 'danger')
        return redirect(url_for('staff_team'))

    admin.role = 'ceo'
    db.session.commit()

    log_activity('admin_promote',
                 f'CEO promoted admin #{admin.id} to CEO',
                 severity='critical')
    flash(f'{admin.full_name} ab CEO hai.', 'success')
    return redirect(url_for('staff_team'))


@app.route('/ceo/admin/<int:admin_id>/demote', methods=['POST'])
@login_required
@ceo_required
def ceo_admin_demote(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.role != 'admin':
        flash('Sirf admin ko demote kar sakte hain.', 'danger')
        return redirect(url_for('staff_team'))

    if admin.id == current_user.id:
        flash('Khud ko demote nahi kar sakte.', 'danger')
        return redirect(url_for('staff_team'))

    admin.role = 'user'
    db.session.commit()

    log_activity('admin_demote',
                 f'CEO demoted admin #{admin.id} to user',
                 severity='critical')
    flash(f'{admin.full_name} ab user hai.', 'success')
    return redirect(url_for('staff_team'))


@app.route('/ceo/admin/<int:admin_id>/reset-password', methods=['POST'])
@login_required
@ceo_required
def ceo_admin_reset_password(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.role not in ('admin', 'user'):
        flash('Sirf admin/user ka password reset kar sakte hain.', 'danger')
        return redirect(url_for('staff_team'))

    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    errs = password_errors(new_pw)
    if errs:
        for e in errs:
            flash(e, 'danger')
        return redirect(url_for('staff_team'))
    if new_pw != confirm:
        flash('Passwords match nahi kar rahe.', 'danger')
        return redirect(url_for('staff_team'))

    admin.set_password(new_pw)
    admin.must_change_password = True
    db.session.commit()

    log_activity('admin_pw_reset',
                 f'CEO reset password for #{admin.id}',
                 severity='warning')
    flash(f'{admin.full_name} ka password reset ho gaya.', 'success')
    return redirect(url_for('staff_team'))


@app.route('/ceo/activity')
@login_required
@ceo_required
def ceo_activity():
    return redirect(url_for('staff_activity'))


@app.route('/ceo/lockdown', methods=['GET', 'POST'])
@login_required
@ceo_required
def ceo_lockdown():
    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'enable':
            _set_setting('maintenance_mode', 'true', current_user.id)
            log_activity('lockdown_enable', 'CEO enabled maintenance mode',
                         severity='critical')
            flash('Maintenance mode ON.', 'warning')
        elif action == 'disable':
            _set_setting('maintenance_mode', 'false', current_user.id)
            log_activity('lockdown_disable', 'CEO disabled maintenance mode',
                         severity='warning')
            flash('Maintenance mode OFF.', 'success')
        return redirect(url_for('ceo_lockdown'))

    current_mode = _get_setting('maintenance_mode', 'false')
    return render_template('ceo/lockdown.html',
                            maintenance_mode=(current_mode == 'true'),
                            page_title="Emergency Lockdown")


@app.route('/ceo/override/admin/<int:admin_id>', methods=['POST'])
@login_required
@ceo_required
def ceo_override_admin(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        flash('Khud pe override nahi.', 'danger')
        return redirect(url_for('staff_team'))

    action = request.form.get('action', '')

    if action == 'ban':
        admin.is_banned = True
        admin.is_active = False
        log_activity('admin_ban_override',
                     f'CEO banned admin #{admin.id}',
                     severity='critical')
        flash(f'{admin.full_name} ban ho gaya.', 'warning')
    elif action == 'unban':
        admin.is_banned = False
        admin.is_active = True
        log_activity('admin_unban_override',
                     f'CEO unbanned admin #{admin.id}',
                     severity='warning')
        flash(f'{admin.full_name} unban ho gaya.', 'success')

    db.session.commit()
    return redirect(url_for('staff_team'))


# ============================================================
# PRESIDENT ROUTES
# ============================================================
@app.route('/president/login', methods=['GET', 'POST'])
def president_login():
    if current_user.is_authenticated and current_user.role == 'president':
        return redirect(url_for('president_dashboard'))

    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')

        if is_locked_out('president_' + mobile):
            flash('Bahut zyada attempts. 15 min baad try karein.', 'danger')
            return redirect(url_for('president_login'))

        if mobile != PRESIDENT_MOBILE:
            log_activity('president_login_denied',
                         f'Attempted president login with wrong mobile: {mobile}',
                         severity='critical')
            flash('Invalid credentials.', 'danger')
            return redirect(url_for('president_login'))

        u = User.query.filter_by(mobile=PRESIDENT_MOBILE, role='president').first()
        if not u:
            flash('President account exist nahi karta. App restart karein.', 'danger')
            return redirect(url_for('president_login'))

        if u.check_password(password):
            clear_attempts('president_' + mobile)
            u.last_login = datetime.utcnow()
            db.session.commit()
            login_user(u, remember=True)

            log_activity('president_login', 'President logged in',
                         severity='warning', user_id=u.id)

            if u.must_change_password:
                return redirect(url_for('president_change_password'))
            return redirect(url_for('president_dashboard'))

        record_attempt('president_' + mobile)
        log_activity('president_login_fail', 'Wrong president password',
                     severity='critical')
        flash('Galat password.', 'danger')

    return render_template('president/login.html', page_title="President Login")


@app.route('/president/change-password', methods=['GET', 'POST'])
@login_required
def president_change_password():
    if current_user.role != 'president':
        return redirect(url_for('user_home'))

    if request.method == 'POST':
        old_pw = request.form.get('old_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        if not current_user.check_password(old_pw):
            flash('Purana password galat hai.', 'danger')
            return redirect(url_for('president_change_password'))

        errs = password_errors(new_pw)
        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('president_change_password'))

        if new_pw != confirm:
            flash('Passwords match nahi kar rahe.', 'danger')
            return redirect(url_for('president_change_password'))

        if new_pw == old_pw:
            flash('Naya password purane se alag hona chahiye.', 'danger')
            return redirect(url_for('president_change_password'))

        current_user.set_password(new_pw)
        current_user.must_change_password = False
        db.session.commit()

        log_activity('president_password_set',
                     'President set own password (first login)',
                     severity='critical')
        flash('Password set ho gaya!', 'success')
        return redirect(url_for('president_dashboard'))

    return render_template('president/change_password.html',
                            must_change=current_user.must_change_password,
                            page_title="Set President Password")


@app.route('/president/dashboard')
@login_required
@president_required
def president_dashboard():
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    total_users = User.query.filter_by(role='user').count()
    total_admins = User.query.filter_by(role='admin').count()
    total_ceos = User.query.filter_by(role='ceo').count()
    total_pdfs = PDFNote.query.count()
    total_sections = Section.query.count()
    total_purchases = Purchase.query.filter_by(status='completed').count()

    total_revenue = db.session.query(func.sum(Purchase.amount))\
        .filter(Purchase.status == 'completed').scalar() or 0

    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(15).all()
    critical_logs = ActivityLog.query.filter_by(severity='critical')\
        .order_by(ActivityLog.created_at.desc()).limit(10).all()

    all_admins = User.query.filter_by(role='admin').all()
    all_ceos = User.query.filter_by(role='ceo').all()

    active_codes = CEOInviteCode.query.filter_by(used=False)\
        .order_by(CEOInviteCode.created_at.desc()).all()

    pending_upi = Purchase.query.filter_by(status='awaiting_verification').count()
    unread_feedback = Feedback.query.filter_by(status='new').count()

    stats = {
        'total_users': total_users, 'total_admins': total_admins,
        'total_ceos': total_ceos, 'total_pdfs': total_pdfs,
        'total_sections': total_sections, 'total_purchases': total_purchases,
        'total_revenue': total_revenue, 'pending_upi': pending_upi,
        'unread_feedback': unread_feedback, 'active_codes': len(active_codes),
    }

    return render_template('president/dashboard.html', stats=stats,
                            recent_logs=recent_logs, critical_logs=critical_logs,
                            all_admins=all_admins, all_ceos=all_ceos,
                            active_codes=active_codes,
                            page_title="President Dashboard")


@app.route('/president/ceo-codes')
@login_required
@president_required
def president_ceo_codes():
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    active_codes = CEOInviteCode.query.filter_by(used=False)\
        .order_by(CEOInviteCode.created_at.desc()).all()
    used_codes = CEOInviteCode.query.filter_by(used=True)\
        .order_by(CEOInviteCode.used_at.desc()).limit(30).all()

    return render_template('president/ceo_codes.html',
                            active_codes=active_codes, used_codes=used_codes,
                            page_title="CEO Invite Codes")


@app.route('/president/ceo-code/generate', methods=['POST'])
@login_required
@president_required
def president_generate_ceo_code():
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    try:
        days = int(request.form.get('expiry_days', '30'))
    except ValueError:
        days = 30
    days = max(1, min(365, days))

    for _ in range(10):
        code = generate_ceo_code()
        if not CEOInviteCode.query.filter_by(code=code).first():
            break
    else:
        flash('Code generate nahi ho paya. Dobara try karein.', 'danger')
        return redirect(url_for('president_ceo_codes'))

    invite = CEOInviteCode(
        code=code,
        created_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(days=days)
    )
    db.session.add(invite)
    db.session.commit()

    log_activity('ceo_code_generate',
                 f'President generated CEO code: {code} (valid {days} days)',
                 severity='warning')
    flash(f'CEO Code: {code} (Valid {days} days)', 'success')
    return redirect(url_for('president_ceo_codes'))


@app.route('/president/ceo-code/<int:code_id>/revoke', methods=['POST'])
@login_required
@president_required
def president_revoke_ceo_code(code_id):
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    invite = CEOInviteCode.query.get_or_404(code_id)
    if invite.used:
        flash('Yeh code already use ho chuka hai.', 'warning')
        return redirect(url_for('president_ceo_codes'))

    code_str = invite.code
    db.session.delete(invite)
    db.session.commit()

    log_activity('ceo_code_revoke',
                 f'President revoked CEO code: {code_str}',
                 severity='warning')
    flash('Code revoke ho gaya.', 'success')
    return redirect(url_for('president_ceo_codes'))


@app.route('/president/control')
@login_required
@president_required
def president_control():
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    staff = User.query.filter(User.role.in_(['admin', 'ceo', 'president']))\
        .order_by(User.role.desc(), User.created_at.desc()).all()

    return render_template('president/control.html', staff=staff,
                            page_title="Full Control")


@app.route('/president/user/<int:user_id>/force-role', methods=['POST'])
@login_required
@president_required
def president_force_role(user_id):
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    user = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role', '').strip().lower()

    if new_role not in ('user', 'admin', 'ceo'):
        flash('Invalid role.', 'danger')
        return redirect(url_for('president_control'))

    if user.role == 'president':
        flash('President role change nahi kar sakte.', 'danger')
        return redirect(url_for('president_control'))

    old_role = user.role
    user.role = new_role
    db.session.commit()

    log_activity('president_force_role',
                 f'President changed role of #{user.id}: {old_role} -> {new_role}',
                 severity='critical')
    flash(f'{user.full_name} ka role {old_role} -> {new_role} ho gaya.', 'success')
    return redirect(url_for('president_control'))


@app.route('/president/user/<int:user_id>/force-delete', methods=['POST'])
@login_required
@president_required
def president_force_delete(user_id):
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Khud ko delete nahi kar sakte.', 'danger')
        return redirect(url_for('president_control'))

    if user.role == 'president':
        flash('Doosre president ko delete nahi kar sakte.', 'danger')
        return redirect(url_for('president_control'))

    log_activity('president_force_delete',
                 f'President deleted #{user.id} (role: {user.role})',
                 severity='critical')

    Purchase.query.filter_by(user_id=user_id).delete()
    Feedback.query.filter_by(user_id=user_id).delete()

    db.session.delete(user)
    db.session.commit()

    flash(f'{user.full_name} permanently delete ho gaya.', 'success')
    return redirect(url_for('president_control'))


@app.route('/president/settings', methods=['GET', 'POST'])
@login_required
@president_required
def president_settings():
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    if request.method == 'POST':
        keys = ['site_name', 'site_tagline', 'support_email', 'support_mobile',
                'upi_id', 'razorpay_enabled', 'maintenance_mode']
        for k in keys:
            val = request.form.get(k, '')
            _set_setting(k, val, current_user.id)

        log_activity('president_settings_update',
                     'President updated site settings',
                     severity='warning')
        flash('Settings saved.', 'success')
        return redirect(url_for('president_settings'))

    settings_map = {}
    for s in SiteSetting.query.all():
        settings_map[s.key] = s.value

    return render_template('president/settings.html', settings=settings_map,
                            page_title="Site Settings")


@app.route('/president/activity')
@login_required
@president_required
def president_activity():
    if current_user.must_change_password:
        return redirect(url_for('president_change_password'))

    severity_filter = request.args.get('severity', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50

    query = ActivityLog.query
    if severity_filter:
        query = query.filter_by(severity=severity_filter)

    pagination = query.order_by(ActivityLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    severity_counts = {
        'all': ActivityLog.query.count(),
        'info': ActivityLog.query.filter_by(severity='info').count(),
        'warning': ActivityLog.query.filter_by(severity='warning').count(),
        'critical': ActivityLog.query.filter_by(severity='critical').count(),
    }

    return render_template('president/activity.html', logs=pagination.items,
                            pagination=pagination,
                            current_severity=severity_filter,
                            severity_counts=severity_counts,
                            page_title="President Activity Log")


# ============================================================
# SETTINGS HELPERS
# ============================================================
def _get_setting(key, default=None):
    s = SiteSetting.query.filter_by(key=key).first()
    return s.value if s else default


def _set_setting(key, value, user_id=None):
    s = SiteSetting.query.filter_by(key=key).first()
    if s:
        s.value = value
        s.updated_by = user_id
    else:
        s = SiteSetting(key=key, value=value, updated_by=user_id)
        db.session.add(s)
    db.session.commit()
    return s


# ============================================================
# PAYMENT CHECKOUT
# ============================================================
@app.route('/payment/checkout/<int:pdf_id>')
@login_required
def payment_checkout(pdf_id):
    pdf = PDFNote.query.get_or_404(pdf_id)

    if not pdf.is_active:
        flash('Yeh PDF available nahi hai.', 'warning')
        return redirect(url_for('user_home'))

    if user_owns_pdf(current_user, pdf_id):
        flash('Aap already is PDF ke owner hain.', 'info')
        return redirect(url_for('user_pdf_view', pdf_id=pdf_id))

    if pdf.is_free:
        pur = Purchase(
            user_id=current_user.id,
            pdf_id=pdf_id,
            amount=0.0,
            status='completed',
            method='free',
            completed_at=datetime.utcnow(),
            ip_address=request.remote_addr
        )
        db.session.add(pur)
        db.session.commit()

        log_activity('free_pdf_claim', f'Free PDF #{pdf_id} claimed')
        flash('Free PDF unlock ho gaya!', 'success')
        return redirect(url_for('user_pdf_view', pdf_id=pdf_id))

    razorpay_ready = razorpay_client is not None

    qr_data_uri = generate_upi_qr_base64(
        upi_id=UPI_ID,
        payee_name=UPI_PAYEE_NAME,
        amount=pdf.price,
        note=f"OmniCart PDF #{pdf.id}"
    )

    existing = Purchase.query.filter_by(
        user_id=current_user.id,
        pdf_id=pdf_id,
        status='pending'
    ).order_by(Purchase.created_at.desc()).first()
   
 
    

    payment_methods = PaymentMethod.query.filter_by(is_active=True)\
        .order_by(PaymentMethod.display_order, PaymentMethod.id).all()


@app.route('/payment/method-details/<int:method_id>')
@login_required
def payment_method_details(method_id):
    m = PaymentMethod.query.get_or_404(method_id)
    if not m.is_active:
        return jsonify({'error': 'Method inactive'}), 400

    return jsonify({
        'id': m.id,
        'name': m.name,
        'method_type': m.method_type,
        'upi_id': m.upi_id or '',
        'account_name': m.account_name or '',
        'account_number': m.account_number or '',
        'ifsc_code': m.ifsc_code or '',
        'bank_name': m.bank_name or '',
        'instructions': m.instructions or '',
        'icon': m.icon or '💳'
    })


# ============================================================
# RAZORPAY
# ============================================================
@app.route('/payment/create-order/<int:pdf_id>', methods=['POST'])
@login_required
def payment_create_order(pdf_id):
    pdf = PDFNote.query.get_or_404(pdf_id)

    if user_owns_pdf(current_user, pdf_id):
        return jsonify({'error': 'Already purchased'}), 400
    if not razorpay_client:
        return jsonify({'error': 'Razorpay not configured.'}), 500
    if pdf.is_free or pdf.price <= 0:
        return jsonify({'error': 'This PDF is free'}), 400

    amount_paise = int(round(pdf.price * 100))

    try:
        order = razorpay_client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f'pdf{pdf_id}_u{current_user.id}_{int(datetime.utcnow().timestamp())}',
            'notes': {
                'pdf_id': str(pdf_id),
                'user_id': str(current_user.id),
                'user_mobile': current_user.mobile
            }
        })
    except Exception as e:
        log_activity('payment_order_fail',
                     f'Razorpay order creation failed: {e}',
                     severity='warning')
        return jsonify({'error': f'Order creation failed: {str(e)}'}), 500

    pur = Purchase(
        user_id=current_user.id,
        pdf_id=pdf_id,
        amount=pdf.price,
        status='pending',
        method='razorpay',
        razorpay_order_id=order['id'],
        ip_address=request.remote_addr
    )
    db.session.add(pur)
    db.session.commit()

    log_activity('payment_order_created',
                 f'Razorpay order {order["id"]} created for PDF #{pdf_id}')

    return jsonify({
        'order_id': order['id'],
        'amount': amount_paise,
        'currency': 'INR',
        'key_id': RAZORPAY_KEY_ID,
        'name': COMPANY_NAME,
        'description': pdf.title[:60],
        'pdf_id': pdf_id,
        'prefill': {
            'name': current_user.full_name,
            'email': current_user.email,
            'contact': current_user.mobile
        }
    })


@app.route('/payment/verify', methods=['POST'])
@login_required
def payment_verify():
    data = request.get_json() or {}
    order_id = data.get('razorpay_order_id')
    payment_id = data.get('razorpay_payment_id')
    signature = data.get('razorpay_signature')

    if not all([order_id, payment_id, signature]):
        return jsonify({'status': 'error', 'msg': 'Missing fields'}), 400

    pur = Purchase.query.filter_by(
        razorpay_order_id=order_id,
        user_id=current_user.id
    ).first()

    if not pur:
        return jsonify({'status': 'error', 'msg': 'Order not found'}), 404

    if pur.status == 'completed':
        return jsonify({
            'status': 'ok',
            'redirect': url_for('user_pdf_view', pdf_id=pur.pdf_id)
        })

    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
    except Exception as e:
        pur.status = 'failed'
        db.session.commit()
        log_activity('payment_verify_fail',
                     f'Order {order_id} signature verification failed: {e}',
                     severity='warning')
        return jsonify({'status': 'error', 'msg': 'Verification failed'}), 400

    pur.razorpay_payment_id = payment_id
    pur.razorpay_signature = signature
    pur.status = 'completed'
    pur.completed_at = datetime.utcnow()
    db.session.commit()

    log_activity('payment_success',
                 f'Razorpay payment success: order {order_id}, amount {pur.amount}')

    return jsonify({
        'status': 'ok',
        'redirect': url_for('user_pdf_view', pdf_id=pur.pdf_id)
    })


@app.route('/payment/webhook/razorpay', methods=['POST'])
def payment_webhook_razorpay():
    webhook_secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
    if not webhook_secret:
        return jsonify({'status': 'ignored', 'msg': 'Webhook secret not set'}), 200

    received_sig = request.headers.get('X-Razorpay-Signature', '')
    payload = request.get_data(as_text=True)

    try:
        expected_sig = hmac.new(
            webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, received_sig):
            log_activity('webhook_invalid_signature',
                         'Razorpay webhook signature mismatch',
                         severity='critical')
            return jsonify({'status': 'error'}), 400
    except Exception as e:
        print(f"[webhook verify error] {e}")
        return jsonify({'status': 'error'}), 400

    try:
        event = request.get_json() or {}
    except Exception:
        return jsonify({'status': 'error'}), 400

    event_type = event.get('event', '')
    payload_data = event.get('payload', {})

    if event_type == 'payment.captured':
        payment = payload_data.get('payment', {}).get('entity', {})
        order_id = payment.get('order_id')
        payment_id = payment.get('id')

        if order_id:
            pur = Purchase.query.filter_by(razorpay_order_id=order_id).first()
            if pur and pur.status != 'completed':
                pur.status = 'completed'
                pur.razorpay_payment_id = payment_id
                pur.completed_at = datetime.utcnow()
                db.session.commit()

                log_activity('webhook_payment_captured',
                             f'Webhook: order {order_id} marked completed')

    elif event_type == 'payment.failed':
        payment = payload_data.get('payment', {}).get('entity', {})
        order_id = payment.get('order_id')

        if order_id:
            pur = Purchase.query.filter_by(razorpay_order_id=order_id).first()
            if pur and pur.status == 'pending':
                pur.status = 'failed'
                db.session.commit()

                log_activity('webhook_payment_failed',
                             f'Webhook: order {order_id} marked failed',
                             severity='warning')

    return jsonify({'status': 'ok'}), 200


@app.route('/payment/upi-claim/<int:pdf_id>', methods=['POST'])
@login_required
def payment_upi_claim(pdf_id):
    pdf = PDFNote.query.get_or_404(pdf_id)

    if user_owns_pdf(current_user, pdf_id):
        return jsonify({'status': 'error', 'error': 'Already owned'}), 400

    if pdf.is_free or pdf.price <= 0:
        return jsonify({'status': 'error', 'error': 'This PDF is free'}), 400

    existing = Purchase.query.filter_by(
        user_id=current_user.id,
        pdf_id=pdf_id,
        status='awaiting_verification'
    ).first()

    if existing:
        return jsonify({
            'status': 'ok',
            'msg': 'Claim already pending admin verification',
            'purchase_id': existing.id
        })

    data = request.get_json() or {}
    reference = data.get('upi_reference', '').strip()[:80]
    method_name = data.get('method_name', '').strip()[:60]

    pur = Purchase(
        user_id=current_user.id,
        pdf_id=pdf_id,
        amount=pdf.price,
        status='awaiting_verification',
        method='upi_manual',
        upi_reference=reference or 'user_claimed',
        ip_address=request.remote_addr
    )
    db.session.add(pur)
    db.session.commit()

    log_activity('upi_claim_created',
                 f'UPI claim #{pur.id} for PDF #{pdf_id} ({pdf.price}) via {method_name}',
                 severity='warning')

    return jsonify({
        'status': 'ok',
        'msg': 'Claim submit ho gaya. Admin verify karega (24 hrs).',
        'purchase_id': pur.id
    })


@app.route('/payment/upi-qr/<int:pdf_id>')
@login_required
def payment_upi_qr(pdf_id):
    pdf = PDFNote.query.get_or_404(pdf_id)

    if pdf.is_free or pdf.price <= 0:
        return jsonify({'error': 'Free PDF'}), 400

    qr = generate_upi_qr_base64(
        upi_id=UPI_ID,
        payee_name=UPI_PAYEE_NAME,
        amount=pdf.price,
        note=f"OmniCart PDF #{pdf.id}"
    )

    upi_url = (f"upi://pay?pa={UPI_ID}&pn={UPI_PAYEE_NAME}"
               f"&am={pdf.price:.2f}&cu=INR"
               f"&tn=OmniCart%20PDF%20{pdf.id}")

    return jsonify({
        'qr_data_uri': qr,
        'upi_url': upi_url,
        'phonepe_url': upi_url.replace('upi://', 'phonepe://'),
        'paytm_url': upi_url.replace('upi://', 'paytmmp://'),
        'gpay_url': upi_url.replace('upi://', 'tez://upi/'),
        'amount': pdf.price,
        'upi_id': UPI_ID,
        'payee': UPI_PAYEE_NAME,
        'note': f'OmniCart PDF #{pdf.id}'
    })


@app.route('/payment/status/<int:purchase_id>')
@login_required
def payment_status(purchase_id):
    pur = Purchase.query.filter_by(
        id=purchase_id,
        user_id=current_user.id
    ).first()

    if not pur:
        return jsonify({'error': 'Not found'}), 404

    return jsonify({
        'status': pur.status,
        'purchase_id': pur.id,
        'pdf_id': pur.pdf_id,
        'amount': pur.amount,
        'method': pur.method or '',
        'completed': pur.status == 'completed'
    })


# ============================================================
# MAINTENANCE MODE
# ============================================================
@app.before_request
def check_maintenance_mode():
    skip_paths = ['/static', '/admin', '/ceo', '/president', '/login',
                  '/signup', '/logout', '/payment/webhook']

    path = request.path or ''
    for sp in skip_paths:
        if path.startswith(sp):
            return None

    if current_user.is_authenticated and current_user.is_staff:
        return None

    try:
        maintenance = _get_setting('maintenance_mode', 'false')
        if maintenance == 'true':
            return render_template('maintenance.html',
                                    page_title="Maintenance"), 503
    except Exception:
        pass

    return None
# ============================================================
# STAFF PORTAL
# ============================================================
def render_staff(template_name='dashboard', **context):
    context['page_title'] = context.get('page_title', 'Staff Portal')
    context['staff_page'] = template_name
    return _flask_rt('internal.html', **context)


def _staff_required():
    if not current_user.is_authenticated:
        return False
    return current_user.role in ('admin', 'ceo', 'president')


@app.route('/staff/')
@app.route('/staff/dashboard')
@login_required
def staff_dashboard():
    if not _staff_required():
        flash('Staff access only.', 'danger')
        return redirect(url_for('admin_login'))

    total_users = User.query.filter_by(role='user').count()
    total_pdfs = PDFNote.query.count()
    active_pdfs = PDFNote.query.filter_by(is_active=True).count()
    total_sections = Section.query.count()

    completed = Purchase.query.filter_by(status='completed').count()
    pending = Purchase.query.filter(Purchase.status.in_(
        ['pending', 'awaiting_verification'])).count()
    revenue = db.session.query(func.sum(Purchase.amount))\
        .filter(Purchase.status == 'completed').scalar() or 0

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_users = User.query.filter(User.created_at >= today_start).count()
    today_purchases = Purchase.query.filter(
        Purchase.created_at >= today_start,
        Purchase.status == 'completed').count()
    today_revenue = db.session.query(func.sum(Purchase.amount))\
        .filter(Purchase.created_at >= today_start,
                Purchase.status == 'completed').scalar() or 0

    unread_fb = Feedback.query.filter_by(status='new').count()

    recent_orders = Purchase.query.filter_by(status='completed')\
        .order_by(Purchase.completed_at.desc()).limit(8).all()
    recent_users = User.query.filter_by(role='user')\
        .order_by(User.created_at.desc()).limit(6).all()
    pending_upi = Purchase.query.filter_by(status='awaiting_verification')\
        .order_by(Purchase.created_at.desc()).limit(6).all()

    stats = {
        'total_users': total_users, 'total_pdfs': total_pdfs,
        'active_pdfs': active_pdfs, 'total_sections': total_sections,
        'completed': completed, 'pending': pending, 'revenue': revenue,
        'today_users': today_users, 'today_purchases': today_purchases,
        'today_revenue': today_revenue, 'unread_fb': unread_fb,
    }

    return render_staff('dashboard', stats=stats, recent_orders=recent_orders,
                        recent_users=recent_users, pending_upi=pending_upi,
                        page_title='Dashboard')


@app.route('/staff/orders')
@login_required
def staff_orders():
    if not _staff_required():
        abort(403)

    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)

    query = Purchase.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    pagination = query.order_by(Purchase.created_at.desc())\
        .paginate(page=page, per_page=30, error_out=False)

    status_counts = {
        'all': Purchase.query.count(),
        'completed': Purchase.query.filter_by(status='completed').count(),
        'pending': Purchase.query.filter_by(status='pending').count(),
        'awaiting_verification': Purchase.query.filter_by(status='awaiting_verification').count(),
        'failed': Purchase.query.filter_by(status='failed').count(),
        'refunded': Purchase.query.filter_by(status='refunded').count(),
    }

    return render_staff('orders', orders=pagination.items, pagination=pagination,
                        current_status=status_filter,
                        status_counts=status_counts, page_title='Orders')


@app.route('/staff/products')
@login_required
def staff_products():
    if not _staff_required():
        abort(403)
    pdfs = PDFNote.query.order_by(PDFNote.created_at.desc()).all()
    return render_staff('products', pdfs=pdfs, page_title='Products')


@app.route('/staff/categories')
@login_required
def staff_categories():
    if not _staff_required():
        abort(403)
    sections = Section.query.order_by(Section.display_order).all()
    return render_staff('categories', sections=sections, page_title='Categories')


@app.route('/staff/payments')
@login_required
def staff_payments():
    if not _staff_required():
        abort(403)
    payments = Purchase.query.filter(Purchase.status.in_(
        ['completed', 'awaiting_verification', 'pending']))\
        .order_by(Purchase.created_at.desc()).limit(100).all()
    return render_staff('payments', payments=payments, page_title='Payments')


@app.route('/staff/customers')
@login_required
def staff_customers():
    if not _staff_required():
        abort(403)
    page = request.args.get('page', 1, type=int)
    pagination = User.query.filter_by(role='user')\
        .order_by(User.created_at.desc())\
        .paginate(page=page, per_page=30, error_out=False)
    return render_staff('customers', customers=pagination.items,
                        pagination=pagination, page_title='Customers')


@app.route('/staff/feedback')
@login_required
def staff_feedback():
    if not _staff_required():
        abort(403)
    fbs = Feedback.query.order_by(Feedback.created_at.desc()).limit(100).all()
    return render_staff('feedback', feedbacks=fbs, page_title='Feedback')


@app.route('/staff/team')
@login_required
def staff_team():
    if current_user.role not in ('ceo', 'president'):
        abort(403)
    team = User.query.filter(User.role.in_(['admin', 'ceo', 'president']))\
        .order_by(User.role, User.created_at.desc()).all()
    return render_staff('team', team=team, page_title='Team')


@app.route('/staff/analytics')
@login_required
def staff_analytics():
    if not _staff_required():
        abort(403)
    return render_staff('analytics', page_title='Analytics')


@app.route('/staff/activity')
@login_required
def staff_activity():
    if not _staff_required():
        abort(403)
    page = request.args.get('page', 1, type=int)
    pagination = ActivityLog.query.order_by(ActivityLog.created_at.desc())\
        .paginate(page=page, per_page=50, error_out=False)
    return render_staff('activity', logs=pagination.items,
                        pagination=pagination, page_title='Activity Log')


@app.route('/staff/search')
@login_required
def staff_search():
    if not _staff_required():
        abort(403)

    q = request.args.get('q', '').strip()
    orders = []
    customers = []
    pdfs = []

    if q:
        like = f"%{q}%"
        orders = Purchase.query.filter(
            or_(Purchase.id.cast(db.String).ilike(like),
                Purchase.upi_reference.ilike(like),
                Purchase.razorpay_order_id.ilike(like))
        ).limit(30).all()

        customers = User.query.filter(
            or_(User.full_name.ilike(like),
                User.email.ilike(like),
                User.mobile.ilike(like))
        ).filter_by(role='user').limit(30).all()

        pdfs = PDFNote.query.filter(
            or_(PDFNote.title.ilike(like),
                PDFNote.description.ilike(like))
        ).limit(30).all()

    return render_staff('search', q=q, orders=orders, customers=customers,
                        pdfs=pdfs, page_title=f'Search: {q}')


@app.route('/staff/settings')
@login_required
def staff_settings():
    if current_user.role != 'president':
        abort(403)
    settings_map = {s.key: s.value for s in SiteSetting.query.all()}
    return render_staff('settings', settings=settings_map, page_title='Settings')


# ============================================================
# STAFF — PAYMENT METHODS
# ============================================================
@app.route('/staff/payment-methods')
@login_required
def staff_payment_methods():
    if not _staff_required():
        abort(403)
    methods = PaymentMethod.query.order_by(
        PaymentMethod.display_order, PaymentMethod.id).all()
    return render_staff('payment_methods', methods=methods,
                        page_title='Payment Methods')


@app.route('/staff/payment-method/create', methods=['GET', 'POST'])
@login_required
def staff_payment_method_create():
    if not _staff_required():
        abort(403)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        method_type = request.form.get('method_type', 'upi')
        upi_id = request.form.get('upi_id', '').strip()
        account_name = request.form.get('account_name', '').strip()
        account_number = request.form.get('account_number', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        bank_name = request.form.get('bank_name', '').strip()
        instructions = request.form.get('instructions', '').strip()
        icon = request.form.get('icon', '💳').strip() or '💳'
        is_active = request.form.get('is_active') == 'on'
        try:
            display_order = int(request.form.get('display_order', '0'))
        except ValueError:
            display_order = 0

        if not name:
            flash('Name zaroori hai.', 'danger')
            return redirect(url_for('staff_payment_method_create'))

        if method_type == 'upi' and not upi_id:
            flash('UPI ID zaroori hai.', 'danger')
            return redirect(url_for('staff_payment_method_create'))

        if method_type == 'bank' and not account_number:
            flash('Account number zaroori hai.', 'danger')
            return redirect(url_for('staff_payment_method_create'))

        m = PaymentMethod(
            name=name, method_type=method_type, upi_id=upi_id,
            account_name=account_name, account_number=account_number,
            ifsc_code=ifsc_code, bank_name=bank_name,
            instructions=instructions, icon=icon,
            is_active=is_active, display_order=display_order
        )
        db.session.add(m)
        db.session.commit()

        log_activity('payment_method_create',
                     f'Payment method "{name}" created')
        flash(f'Payment method "{name}" ban gaya.', 'success')
        return redirect(url_for('staff_payment_methods'))

    return render_staff('payment_method_form', method=None,
                        page_title='Add Payment Method')


@app.route('/staff/payment-method/<int:method_id>/edit', methods=['GET', 'POST'])
@login_required
def staff_payment_method_edit(method_id):
    if not _staff_required():
        abort(403)
    m = PaymentMethod.query.get_or_404(method_id)

    if request.method == 'POST':
        m.name = request.form.get('name', '').strip() or m.name
        m.method_type = request.form.get('method_type', 'upi')
        m.upi_id = request.form.get('upi_id', '').strip()
        m.account_name = request.form.get('account_name', '').strip()
        m.account_number = request.form.get('account_number', '').strip()
        m.ifsc_code = request.form.get('ifsc_code', '').strip()
        m.bank_name = request.form.get('bank_name', '').strip()
        m.instructions = request.form.get('instructions', '').strip()
        m.icon = request.form.get('icon', '💳').strip() or '💳'
        m.is_active = request.form.get('is_active') == 'on'
        try:
            m.display_order = int(request.form.get('display_order', '0'))
        except ValueError:
            m.display_order = 0

        db.session.commit()
        log_activity('payment_method_edit', f'Payment method #{m.id} updated')
        flash('Update ho gaya.', 'success')
        return redirect(url_for('staff_payment_methods'))

    return render_staff('payment_method_form', method=m,
                        page_title=f'Edit: {m.name}')


@app.route('/staff/payment-method/<int:method_id>/toggle', methods=['POST'])
@login_required
def staff_payment_method_toggle(method_id):
    if not _staff_required():
        abort(403)
    m = PaymentMethod.query.get_or_404(method_id)
    m.is_active = not m.is_active
    db.session.commit()
    log_activity('payment_method_toggle',
                 f'Payment method #{m.id} -> {"active" if m.is_active else "inactive"}')
    flash(f'{"Active" if m.is_active else "Inactive"} ho gaya.', 'success')
    return redirect(url_for('staff_payment_methods'))


@app.route('/staff/payment-method/<int:method_id>/delete', methods=['POST'])
@login_required
def staff_payment_method_delete(method_id):
    if not _staff_required():
        abort(403)
    m = PaymentMethod.query.get_or_404(method_id)
    db.session.delete(m)
    db.session.commit()
    log_activity('payment_method_delete',
                 f'Payment method #{method_id} deleted', severity='warning')
    flash('Delete ho gaya.', 'success')
    return redirect(url_for('staff_payment_methods'))


# ============================================================
# STAFF — UPLOAD / EDIT PDF
# ============================================================
@app.route('/staff/upload', methods=['GET', 'POST'])
@login_required
def staff_upload():
    if not _staff_required():
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        section_id = request.form.get('section_id', '').strip()
        subcategory = request.form.get('subcategory', 'notes')
        price_str = request.form.get('price', '49')
        icon = request.form.get('icon', '📄').strip() or '📄'
        is_featured = request.form.get('is_featured') == 'on'
        file = request.files.get('pdf_file')

        errs = []
        if not title:
            errs.append('Title zaroori hai.')
        if not section_id:
            errs.append('Section select karein.')
        else:
            try:
                section_id = int(section_id)
                if not Section.query.get(section_id):
                    errs.append('Invalid section.')
            except ValueError:
                errs.append('Invalid section.')
        try:
            price = float(price_str)
            if price < 0:
                errs.append('Price negative nahi ho sakta.')
        except ValueError:
            errs.append('Invalid price.')
            price = 0

        if not file or not file.filename:
            errs.append('PDF file upload karein.')
        elif not file.filename.lower().endswith('.pdf'):
            errs.append('Sirf PDF file allowed hai.')

        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('staff_upload'))

        safe_name, orig_name, full_path = save_pdf_safely(file)
        if not safe_name:
            flash('File save nahi ho payi.', 'danger')
            return redirect(url_for('staff_upload'))

        pages = count_pdf_pages(full_path)
        note = PDFNote(
            title=title, description=description, section_id=section_id,
            subcategory=subcategory, price=price, filename=safe_name,
            original_filename=orig_name, total_pages=pages, icon=icon,
            is_featured=is_featured, uploaded_by=current_user.id
        )
        db.session.add(note)
        db.session.commit()

        log_activity('pdf_upload', f'PDF #{note.id} "{title}" uploaded ({pages} pages)')
        flash(f'PDF upload ho gaya! ({pages} pages)', 'success')
        return redirect(url_for('staff_products'))

    sections = Section.query.filter_by(is_active=True)\
        .order_by(Section.display_order).all()
    return render_staff('upload', sections=sections, page_title='Upload PDF')


@app.route('/staff/pdf/<int:pdf_id>/edit', methods=['GET', 'POST'])
@login_required
def staff_pdf_edit(pdf_id):
    if not _staff_required():
        abort(403)
    pdf = PDFNote.query.get_or_404(pdf_id)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        section_id = request.form.get('section_id', '').strip()
        subcategory = request.form.get('subcategory', 'notes')
        price_str = request.form.get('price', '49')
        icon = request.form.get('icon', '📄').strip() or '📄'
        is_featured = request.form.get('is_featured') == 'on'
        is_active = request.form.get('is_active') == 'on'

        errs = []
        if not title:
            errs.append('Title zaroori hai.')
        try:
            section_id = int(section_id)
            if not Section.query.get(section_id):
                errs.append('Invalid section.')
        except ValueError:
            errs.append('Section select karein.')

        try:
            price = float(price_str)
        except ValueError:
            errs.append('Invalid price.')
            price = pdf.price

        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('staff_pdf_edit', pdf_id=pdf_id))

        new_file = request.files.get('pdf_file')
        if new_file and new_file.filename:
            if not new_file.filename.lower().endswith('.pdf'):
                flash('Sirf PDF allowed.', 'danger')
                return redirect(url_for('staff_pdf_edit', pdf_id=pdf_id))
            try:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf.filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass
            safe_name, orig_name, full_path = save_pdf_safely(new_file)
            if safe_name:
                pdf.filename = safe_name
                pdf.original_filename = orig_name
                pdf.total_pages = count_pdf_pages(full_path)

        pdf.title = title
        pdf.description = description
        pdf.section_id = section_id
        pdf.subcategory = subcategory
        pdf.price = price
        pdf.icon = icon
        pdf.is_featured = is_featured
        pdf.is_active = is_active
        db.session.commit()

        log_activity('pdf_edit', f'PDF #{pdf.id} updated')
        flash('PDF update ho gaya.', 'success')
        return redirect(url_for('staff_products'))

    sections = Section.query.filter_by(is_active=True)\
        .order_by(Section.display_order).all()
    return render_staff('pdf_edit', pdf=pdf, sections=sections,
                        page_title=f'Edit: {pdf.title}')


@app.route('/staff/pdf/<int:pdf_id>/toggle', methods=['POST'])
@login_required
def staff_pdf_toggle(pdf_id):
    if not _staff_required():
        abort(403)
    pdf = PDFNote.query.get_or_404(pdf_id)
    pdf.is_active = not pdf.is_active
    db.session.commit()
    log_activity('pdf_toggle',
                 f'PDF #{pdf.id} -> {"active" if pdf.is_active else "inactive"}')
    flash(f'PDF {"active" if pdf.is_active else "inactive"}.', 'success')
    return redirect(url_for('staff_products'))


@app.route('/staff/pdf/<int:pdf_id>/delete', methods=['POST'])
@login_required
def staff_pdf_delete(pdf_id):
    if not _staff_required():
        abort(403)
    pdf = PDFNote.query.get_or_404(pdf_id)
    try:
        fp = os.path.join(app.config['UPLOAD_FOLDER'], pdf.filename)
        if os.path.exists(fp):
            os.remove(fp)
    except Exception:
        pass
    Purchase.query.filter_by(pdf_id=pdf_id).delete()
    db.session.delete(pdf)
    db.session.commit()
    log_activity('pdf_delete', f'PDF #{pdf_id} deleted', severity='warning')
    flash('PDF delete ho gaya.', 'success')
    return redirect(url_for('staff_products'))


# ============================================================
# STAFF — SECTION
# ============================================================
@app.route('/staff/section/create', methods=['GET', 'POST'])
@login_required
def staff_section_create():
    if not _staff_required():
        abort(403)

    if request.method == 'POST':
        slug = request.form.get('slug', '').strip().lower()
        name = request.form.get('name', '').strip()
        group = request.form.get('group', 'General').strip() or 'General'
        icon = request.form.get('icon', '📄').strip() or '📄'
        description = request.form.get('description', '').strip()
        display_order = request.form.get('display_order', '0')

        errs = []
        if not slug:
            errs.append('Slug zaroori hai.')
        elif not re.match(r'^[a-z0-9_]+$', slug):
            errs.append('Slug me sirf lowercase, numbers, _ allowed.')
        elif Section.query.filter_by(slug=slug).first():
            errs.append('Yeh slug already exists.')
        if not name:
            errs.append('Name zaroori hai.')

        try:
            display_order = int(display_order)
        except ValueError:
            display_order = 0

        if errs:
            for e in errs:
                flash(e, 'danger')
            return redirect(url_for('staff_section_create'))

        s = Section(slug=slug, name=name, group=group, icon=icon,
                    description=description, display_order=display_order,
                    is_active=True)
        db.session.add(s)
        db.session.commit()

        log_activity('section_create', f'Section "{name}" created')
        flash(f'Section "{name}" ban gaya.', 'success')
        return redirect(url_for('staff_categories'))

    return render_staff('section_create', page_title='Create Section')


@app.route('/staff/section/<int:section_id>/edit', methods=['GET', 'POST'])
@login_required
def staff_section_edit(section_id):
    if not _staff_required():
        abort(403)
    section = Section.query.get_or_404(section_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        group = request.form.get('group', 'General').strip() or 'General'
        icon = request.form.get('icon', '📄').strip() or '📄'
        description = request.form.get('description', '').strip()
        display_order = request.form.get('display_order', '0')
        is_active = request.form.get('is_active') == 'on'
        new_slug = request.form.get('slug', '').strip().lower()

        if new_slug and new_slug != section.slug:
            if not re.match(r'^[a-z0-9_]+$', new_slug):
                flash('Slug invalid.', 'danger')
                return redirect(url_for('staff_section_edit', section_id=section_id))
            if Section.query.filter(Section.slug == new_slug,
                                    Section.id != section_id).first():
                flash('Slug already exists.', 'danger')
                return redirect(url_for('staff_section_edit', section_id=section_id))
            section.slug = new_slug

        if not name:
            flash('Name zaroori hai.', 'danger')
            return redirect(url_for('staff_section_edit', section_id=section_id))

        try:
            display_order = int(display_order)
        except ValueError:
            display_order = section.display_order

        section.name = name
        section.group = group
        section.icon = icon
        section.description = description
        section.display_order = display_order
        section.is_active = is_active
        db.session.commit()

        log_activity('section_edit', f'Section #{section.id} updated')
        flash('Section update ho gaya.', 'success')
        return redirect(url_for('staff_categories'))

    groups = db.session.query(Section.group).distinct().all()
    groups = [g[0] for g in groups if g[0]]
    return render_staff('section_edit', section=section, groups=groups,
                        page_title=f'Edit: {section.name}')


@app.route('/staff/section/<int:section_id>/delete', methods=['POST'])
@login_required
def staff_section_delete(section_id):
    if not _staff_required():
        abort(403)
    section = Section.query.get_or_404(section_id)
    pdf_count = PDFNote.query.filter_by(section_id=section_id).count()
    if pdf_count > 0:
        force = request.form.get('force') == 'yes'
        if not force:
            flash(f'{pdf_count} PDFs hain. Force delete karein.', 'warning')
            return redirect(url_for('staff_categories'))
        for pdf in PDFNote.query.filter_by(section_id=section_id).all():
            try:
                fp = os.path.join(app.config['UPLOAD_FOLDER'], pdf.filename)
                if os.path.exists(fp):
                    os.remove(fp)
            except Exception:
                pass
            Purchase.query.filter_by(pdf_id=pdf.id).delete()
            db.session.delete(pdf)
    db.session.delete(section)
    db.session.commit()
    log_activity('section_delete', f'Section #{section_id} deleted',
                 severity='warning')
    flash('Section delete ho gaya.', 'success')
    return redirect(url_for('staff_categories'))


# ============================================================
# STAFF — ORDERS
# ============================================================
@app.route('/staff/order/<int:order_id>')
@login_required
def staff_order_detail(order_id):
    if not _staff_required():
        abort(403)
    order = Purchase.query.get_or_404(order_id)
    return render_staff('order_detail', order=order,
                        page_title=f'Order #{order.id}')


@app.route('/staff/order/<int:order_id>/verify', methods=['POST'])
@login_required
def staff_order_verify(order_id):
    if not _staff_required():
        abort(403)
    order = Purchase.query.get_or_404(order_id)
    if order.status not in ('pending', 'awaiting_verification'):
        flash('Sirf pending orders verify ho sakte hain.', 'warning')
        return redirect(url_for('staff_order_detail', order_id=order_id))
    order.status = 'completed'
    order.completed_at = datetime.utcnow()
    if not order.method:
        order.method = 'upi_manual'
    db.session.commit()
    log_activity('order_verify',
                 f'Order #{order.id} verified (user {order.user_id}, {order.amount})')
    flash(f'Order #{order.id} verified.', 'success')
    return redirect(url_for('staff_orders'))


@app.route('/staff/order/<int:order_id>/fail', methods=['POST'])
@login_required
def staff_order_fail(order_id):
    if not _staff_required():
        abort(403)
    order = Purchase.query.get_or_404(order_id)
    order.status = 'failed'
    db.session.commit()
    log_activity('order_fail', f'Order #{order.id} failed', severity='warning')
    flash(f'Order #{order.id} failed.', 'warning')
    return redirect(url_for('staff_order_detail', order_id=order_id))


@app.route('/staff/order/<int:order_id>/refund', methods=['POST'])
@login_required
def staff_order_refund(order_id):
    if not _staff_required():
        abort(403)
    order = Purchase.query.get_or_404(order_id)
    reason = request.form.get('reason', '').strip()
    order.status = 'refunded'
    db.session.commit()
    log_activity('order_refund',
                 f'Order #{order.id} refunded. Reason: {reason}',
                 severity='warning')
    flash(f'Order #{order.id} refunded.', 'success')
    return redirect(url_for('staff_order_detail', order_id=order_id))


# ============================================================
# STAFF — CUSTOMERS
# ============================================================
@app.route('/staff/customer/<int:user_id>')
@login_required
def staff_user_detail(user_id):
    if not _staff_required():
        abort(403)
    user = User.query.get_or_404(user_id)
    purchases = Purchase.query.filter_by(user_id=user_id)\
        .order_by(Purchase.created_at.desc()).limit(50).all()
    feedbacks = Feedback.query.filter_by(user_id=user_id)\
        .order_by(Feedback.created_at.desc()).limit(20).all()
    total_spent = db.session.query(func.sum(Purchase.amount))\
        .filter(Purchase.user_id == user_id,
                Purchase.status == 'completed').scalar() or 0
    return render_staff('user_detail', user=user, purchases=purchases,
                        feedbacks=feedbacks, total_spent=total_spent,
                        page_title=f'User: {user.full_name}')


@app.route('/staff/customer/<int:user_id>/ban', methods=['POST'])
@login_required
def staff_user_ban(user_id):
    if not _staff_required():
        abort(403)
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Khud ko ban nahi kar sakte.', 'danger')
        return redirect(url_for('staff_user_detail', user_id=user_id))
    rank = {'user': 0, 'admin': 1, 'ceo': 2, 'president': 3}
    if rank.get(user.role, 0) >= rank.get(current_user.role, 0):
        flash('Is role ko ban nahi kar sakte.', 'danger')
        return redirect(url_for('staff_user_detail', user_id=user_id))
    reason = request.form.get('reason', '').strip()
    user.is_banned = True
    user.is_active = False
    db.session.commit()
    log_activity('user_ban', f'User #{user.id} banned. Reason: {reason}',
                 severity='warning')
    flash('User banned.', 'success')
    return redirect(url_for('staff_user_detail', user_id=user_id))


@app.route('/staff/customer/<int:user_id>/unban', methods=['POST'])
@login_required
def staff_user_unban(user_id):
    if not _staff_required():
        abort(403)
    user = User.query.get_or_404(user_id)
    user.is_banned = False
    user.is_active = True
    db.session.commit()
    log_activity('user_unban', f'User #{user.id} unbanned')
    flash('User unban.', 'success')
    return redirect(url_for('staff_user_detail', user_id=user_id))


# ============================================================
# STAFF — FEEDBACK
# ============================================================
@app.route('/staff/feedback/<int:fb_id>')
@login_required
def staff_feedback_detail(fb_id):
    if not _staff_required():
        abort(403)
    fb = Feedback.query.get_or_404(fb_id)
    if fb.status == 'new':
        fb.status = 'read'
        db.session.commit()
    return render_staff('feedback_detail', fb=fb,
                        page_title=f'Feedback #{fb.id}')


@app.route('/staff/feedback/<int:fb_id>/reply', methods=['POST'])
@login_required
def staff_feedback_reply(fb_id):
    if not _staff_required():
        abort(403)
    fb = Feedback.query.get_or_404(fb_id)
    reply = request.form.get('reply', '').strip()
    if not reply:
        flash('Reply khali nahi ho sakta.', 'danger')
        return redirect(url_for('staff_feedback_detail', fb_id=fb_id))
    fb.admin_reply = reply
    fb.replied_by = current_user.id
    fb.replied_at = datetime.utcnow()
    fb.status = 'resolved'
    db.session.commit()
    log_activity('feedback_reply', f'Replied to feedback #{fb.id}')
    flash('Reply bhej diya.', 'success')
    return redirect(url_for('staff_feedback'))


@app.route('/staff/feedback/<int:fb_id>/delete', methods=['POST'])
@login_required
def staff_feedback_delete(fb_id):
    if not _staff_required():
        abort(403)
    fb = Feedback.query.get_or_404(fb_id)
    db.session.delete(fb)
    db.session.commit()
    log_activity('feedback_delete', f'Feedback #{fb_id} deleted')
    flash('Feedback delete.', 'success')
    return redirect(url_for('staff_feedback'))


# ============================================================
# STAFF — SETTINGS / ACTIVITY
# ============================================================
@app.route('/staff/settings/save', methods=['POST'])
@login_required
def staff_settings_save():
    if current_user.role != 'president':
        abort(403)
    keys = ['site_name', 'site_tagline', 'support_email', 'support_mobile',
            'upi_id', 'razorpay_enabled', 'maintenance_mode']
    for k in keys:
        val = request.form.get(k, '')
        _set_setting(k, val, current_user.id)
    log_activity('president_settings_update', 'Settings updated',
                 severity='warning')
    flash('Settings saved.', 'success')
    return redirect(url_for('staff_settings'))


@app.route('/staff/activity/clear', methods=['POST'])
@login_required
def staff_activity_clear():
    if current_user.role != 'president':
        abort(403)
    days = request.form.get('days', '90')
    try:
        days = int(days)
    except ValueError:
        days = 90
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = ActivityLog.query.filter(ActivityLog.created_at < cutoff).delete()
    db.session.commit()
    log_activity('activity_clear', f'{deleted} logs cleared',
                 severity='critical')
    flash(f'{deleted} logs delete ho gaye.', 'success')
    return redirect(url_for('staff_activity'))


# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(403)
def err_403(e):
    return render_template('errors/403.html', page_title="403 - Access Denied"), 403


@app.errorhandler(404)
def err_404(e):
    return render_template('errors/404.html', page_title="404 - Not Found"), 404


@app.errorhandler(500)
def err_500(e):
    try:
        db.session.rollback()
    except Exception:
        pass
    return render_template('errors/500.html', page_title="500 - Server Error"), 500


@app.errorhandler(413)
def err_413(e):
    flash('File bahut badi hai. Max 100 MB allowed.', 'danger')
    return redirect(request.referrer or url_for('staff_upload'))


@app.errorhandler(429)
def err_429(e):
    return render_template('errors/429.html', page_title="429 - Too Many Requests"), 429


# ============================================================
# CONTEXT PROCESSOR
# ============================================================
@app.context_processor
def inject_nav_context():
    try:
        nav_sections = Section.query.filter_by(is_active=True)\
            .order_by(Section.display_order).all()
    except Exception:
        nav_sections = []

    pending_count = 0
    unread_feedback = 0
    try:
        if current_user.is_authenticated and current_user.is_staff:
            pending_count = Purchase.query.filter(
                Purchase.status.in_(['pending', 'awaiting_verification'])
            ).count()
            unread_feedback = Feedback.query.filter_by(status='new').count()
    except Exception:
        pass

    return dict(
        nav_sections=nav_sections,
        pending_count=pending_count,
        unread_feedback=unread_feedback,
    )


# ============================================================
# CLI COMMANDS
# ============================================================
@app.cli.command('init-db')
def cli_init_db():
    init_defaults()
    print("Database initialized.")


@app.cli.command('create-admin')
def cli_create_admin():
    mobile = input("Admin mobile: ").strip()
    email = input("Admin email: ").strip()
    name = input("Admin name: ").strip()
    password = input("Admin password: ").strip()

    with app.app_context():
        if User.query.filter_by(mobile=mobile).first():
            print("Mobile already exists.")
            return

        u = User(
            full_name=name,
            email=email,
            mobile=mobile,
            role='admin',
            email_verified=True,
            mobile_verified=True,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

        print(f"Admin created: {mobile}")


# ============================================================
# APP INITIALIZATION
# ============================================================
init_defaults()


# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    print("=" * 64)
    print("  OMNICART - E-Commerce PDF Notes Platform")
    print("  Copyright (c) 2026 PATEL KARKHANA PVT.LTD.")
    print("=" * 64)
    print(f"  Local        : http://localhost:5000")
    print(f"  Admin Login  : /admin/login")
    print(f"  CEO Signup   : /ceo/signup")
    print(f"  President    : /president/login")
    print(f"  President M  : {PRESIDENT_MOBILE}")
    print("-" * 64)
    print(f"  Razorpay     : {'Ready' if razorpay_client else 'Not configured'}")
    print(f"  PDF Library  : {'Ready' if PYPDF_AVAILABLE else 'pip install pypdf'}")
    print(f"  QR Library   : {'Ready' if QRCODE_AVAILABLE else 'pip install qrcode[pil]'}")
    print(f"  Encryption   : {'Ready' if FERNET_AVAILABLE else 'pip install cryptography'}")
    print("=" * 64)

    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=(os.environ.get('FLASK_ENV') != 'production'),
        threaded=True
    )