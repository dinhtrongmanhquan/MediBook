from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import math, smtplib, os, uuid, threading, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import bcrypt
from apscheduler.schedulers.background import BackgroundScheduler

# ─── Paths & App Setup ──────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if "scheduler" in globals():
        scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

@app.get("/")
def get_index():
    return FileResponse(os.path.join(BASE, "index.html"))


# ─── In-memory session store ────────────────────────────────────────────────
sessions = {}   # { token: { user_id, role } }
reset_otps = {} # { email: { otp, role, expires } }

# ─── CSV loaders ────────────────────────────────────────────────────────────
csv_lock = threading.Lock()

def load_clinics():      return pd.read_csv(f"{DATA}/clinics.csv")
def load_doctors():      return pd.read_csv(f"{DATA}/doctors.csv")
def load_appointments(): return pd.read_csv(f"{DATA}/appointments.csv")
def load_users():        return pd.read_csv(f"{DATA}/users.csv")
def load_medical_records():      return pd.read_csv(f"{DATA}/medical_records.csv")
def load_services():             return pd.read_csv(f"{DATA}/services.csv")
def load_payments():             return pd.read_csv(f"{DATA}/payments.csv")
def load_messages():             return pd.read_csv(f"{DATA}/messages.csv")
def load_aftercare():            return pd.read_csv(f"{DATA}/aftercare.csv")

def save_users(df):
    with csv_lock:
        df.to_csv(f"{DATA}/users.csv", index=False)

def save_appointments(df):
    with csv_lock:
        df.to_csv(f"{DATA}/appointments.csv", index=False)

def save_medical_records(df):
    with csv_lock:
        df.to_csv(f"{DATA}/medical_records.csv", index=False)

def save_payments(df):
    with csv_lock:
        df.to_csv(f"{DATA}/payments.csv", index=False)

def save_messages(df):
    with csv_lock:
        df.to_csv(f"{DATA}/messages.csv", index=False)

def save_aftercare(df):
    with csv_lock:
        df.to_csv(f"{DATA}/aftercare.csv", index=False)

def save_doctors(df):
    with csv_lock:
        df.to_csv(f"{DATA}/doctors.csv", index=False)

# ─── Gmail Config ──────────────────────────────────────────────────────────
GMAIL_USER = "kingdorenom@gmail.com"
GMAIL_PASS = "cicf pqba zwum ofkk"   # App Password, không phải mật khẩu thường

# ─── Helpers ───────────────────────────────────────────────────────────────
def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_current_user(request: Request):
    """Lấy user hiện tại từ session token trong header"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token or token not in sessions:
        return None
    session = sessions[token]
    user_id = session["user_id"]
    users = load_users()
    user_rows = users[users["id"] == user_id]
    if user_rows.empty:
        return None
    return user_rows.iloc[0]

def get_session_role(request: Request):
    """Lấy role từ session"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token or token not in sessions:
        return None
    return sessions[token].get("role", "patient")

def require_role(request: Request, role: str):
    """Kiểm tra role, raise 403 nếu không đúng"""
    current_role = get_session_role(request)
    if current_role != role:
        raise HTTPException(status_code=403, detail=f"Cần quyền {role}!")

# ─── Email Functions ───────────────────────────────────────────────────────

def send_email(to_email: str, patient_name: str, doctor_name: str,
               clinic_name: str, date: str, time: str):
    """Gửi email xác nhận cho BỆNH NHÂN"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ Xác nhận lịch hẹn khám bệnh"
    msg["From"]    = GMAIL_USER
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:Arial;max-width:500px;margin:auto;background:#f9f9f9;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#0369a1,#0ea5e9);padding:24px;color:#fff;text-align:center">
        <h2 style="margin:0">🏥 Xác Nhận Lịch Khám</h2>
      </div>
      <div style="padding:24px">
        <p>Xin chào <b>{patient_name}</b>,</p>
        <p>Lịch hẹn của bạn đã được đặt thành công:</p>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:8px;color:#666">👨‍⚕️ Bác sĩ</td><td><b>{doctor_name}</b></td></tr>
          <tr><td style="padding:8px;color:#666">🏥 Phòng khám</td><td><b>{clinic_name}</b></td></tr>
          <tr><td style="padding:8px;color:#666">📅 Ngày</td><td><b>{date}</b></td></tr>
          <tr><td style="padding:8px;color:#666">⏰ Giờ</td><td><b>{time}</b></td></tr>
        </table>
        <p style="color:#666;font-size:13px;margin-top:20px">Vui lòng đến trước 10 phút. Mang theo CMND/CCCD.</p>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html"))
    if GMAIL_PASS in ["13112006AZ", "your_app_password"] or not GMAIL_PASS:
        print(f"[MÔ PHỎNG] Gửi email xác nhận thành công tới bệnh nhân: {to_email}")
        return True

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error (patient): {e}")
        return False


def send_otp_email(to_email: str, otp: str):
    """Gửi email chứa mã OTP khôi phục mật khẩu"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🔐 Mã Khôi Phục Mật Khẩu – MediBook"
    msg["From"]    = GMAIL_USER
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:Arial;max-width:500px;margin:auto;background:#f9f9f9;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#0369a1,#0ea5e9);padding:24px;color:#fff;text-align:center">
        <h2 style="margin:0">🔐 Khôi Phục Mật Khẩu</h2>
      </div>
      <div style="padding:24px">
        <p>Xin chào,</p>
        <p>Bạn vừa yêu cầu khôi phục mật khẩu trên hệ thống <b>MediBook</b>.</p>
        <p>Mã xác nhận (OTP) của bạn là:</p>
        <div style="text-align:center; margin:20px 0;">
          <span style="font-size:24px; font-weight:bold; background:#e0f2fe; color:#0369a1; padding:10px 20px; border-radius:8px; letter-spacing:4px;">
            {otp}
          </span>
        </div>
        <p style="color:#666;font-size:13px;margin-top:20px">Mã này có hiệu lực trong 5 phút. Vui lòng không chia sẻ mã này cho bất kỳ ai.</p>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html"))
    if GMAIL_PASS in ["13112006AZ", "your_app_password"] or not GMAIL_PASS:
        print(f"[MÔ PHỎNG] Gửi email OTP khôi phục mật khẩu thành công tới: {to_email}")
        return True

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error (otp): {e}")
        return False


def send_doctor_notification(doctor_email: str, doctor_name: str,
                             patient_name: str, clinic_name: str,
                             date: str, time: str, symptoms: str):
    """Gửi email thông báo cho BÁC SĨ khi có lịch hẹn mới"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📋 Lịch hẹn mới – {patient_name} ({date} {time})"
    msg["From"]    = GMAIL_USER
    msg["To"]      = doctor_email

    html = f"""
    <div style="font-family:Arial;max-width:520px;margin:auto;background:#f9f9f9;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#059669,#10b981);padding:24px;color:#fff;text-align:center">
        <h2 style="margin:0">📋 Lịch Hẹn Mới</h2>
        <p style="margin:6px 0 0;opacity:.85;font-size:14px">Bạn có bệnh nhân mới đặt lịch</p>
      </div>
      <div style="padding:24px">
        <p>Xin chào <b>BS. {doctor_name}</b>,</p>
        <p>Bạn vừa nhận được lịch hẹn mới:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
          <tr style="border-bottom:1px solid #e5e7eb">
            <td style="padding:10px;color:#6b7280;font-size:14px">👤 Bệnh nhân</td>
            <td style="padding:10px;font-weight:600;text-align:right">{patient_name}</td>
          </tr>
          <tr style="border-bottom:1px solid #e5e7eb">
            <td style="padding:10px;color:#6b7280;font-size:14px">🏥 Phòng khám</td>
            <td style="padding:10px;font-weight:600;text-align:right">{clinic_name}</td>
          </tr>
          <tr style="border-bottom:1px solid #e5e7eb">
            <td style="padding:10px;color:#6b7280;font-size:14px">📅 Ngày khám</td>
            <td style="padding:10px;font-weight:600;text-align:right">{date}</td>
          </tr>
          <tr style="border-bottom:1px solid #e5e7eb">
            <td style="padding:10px;color:#6b7280;font-size:14px">⏰ Giờ khám</td>
            <td style="padding:10px;font-weight:600;text-align:right">{time}</td>
          </tr>
          <tr>
            <td style="padding:10px;color:#6b7280;font-size:14px">🤒 Triệu chứng</td>
            <td style="padding:10px;font-weight:600;text-align:right">{symptoms or '—'}</td>
          </tr>
        </table>
        <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px;font-size:13px;color:#065f46">
          💡 Vui lòng chuẩn bị trước cho buổi khám.
        </div>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html"))
    if GMAIL_PASS in ["13112006AZ", "your_app_password"] or not GMAIL_PASS:
        print(f"[MÔ PHỎNG] Gửi email thông báo lịch hẹn mới tới bác sĩ: {doctor_email}")
        return True

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, doctor_email, msg.as_string())
        print(f"✅ Doctor notification sent to {doctor_email}")
        return True
    except Exception as e:
        print(f"Email error (doctor): {e}")
        return False


def send_appointment_reminder(to_email: str, patient_name: str,
                              doctor_name: str, clinic_name: str,
                              date: str, time: str):
    """Gửi email nhắc nhở cho BỆNH NHÂN khi đến ngày khám"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⏰ Nhắc nhở: Lịch khám hôm nay lúc {time}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:Arial;max-width:520px;margin:auto;background:#f9f9f9;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#d97706,#f59e0b);padding:24px;color:#fff;text-align:center">
        <h2 style="margin:0">⏰ Nhắc Nhở Lịch Khám</h2>
        <p style="margin:6px 0 0;opacity:.9;font-size:14px">Lịch khám của bạn là HÔM NAY!</p>
      </div>
      <div style="padding:24px">
        <p>Xin chào <b>{patient_name}</b>,</p>
        <p>Đây là lời nhắc nhở cho lịch khám <b>hôm nay</b> của bạn:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
          <tr style="border-bottom:1px solid #e5e7eb">
            <td style="padding:10px;color:#6b7280">👨‍⚕️ Bác sĩ</td>
            <td style="padding:10px;font-weight:600;text-align:right">{doctor_name}</td>
          </tr>
          <tr style="border-bottom:1px solid #e5e7eb">
            <td style="padding:10px;color:#6b7280">🏥 Phòng khám</td>
            <td style="padding:10px;font-weight:600;text-align:right">{clinic_name}</td>
          </tr>
          <tr style="border-bottom:1px solid #e5e7eb">
            <td style="padding:10px;color:#6b7280">📅 Ngày</td>
            <td style="padding:10px;font-weight:600;text-align:right">{date}</td>
          </tr>
          <tr>
            <td style="padding:10px;color:#6b7280">⏰ Giờ</td>
            <td style="padding:10px;font-weight:700;text-align:right;color:#d97706;font-size:18px">{time}</td>
          </tr>
        </table>
        <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px;font-size:13px;color:#92400e">
          📌 <b>Lưu ý quan trọng:</b><br>
          • Vui lòng đến trước <b>10 phút</b><br>
          • Mang theo CMND/CCCD<br>
          • Mang theo sổ khám bệnh (nếu có)
        </div>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html"))
    if GMAIL_PASS in ["13112006AZ", "your_app_password"] or not GMAIL_PASS:
        print(f"[MÔ PHỎNG] Gửi email nhắc nhở tới: {to_email}")
        return True

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to_email, msg.as_string())
        print(f"✅ Reminder sent to {to_email}")
        return True
    except Exception as e:
        print(f"Email error (reminder): {e}")
        return False


def send_doctor_approval_email(doctor_email: str, doctor_name: str):
    """Gửi email thông báo bác sĩ đã được duyệt"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ Hồ sơ của bạn đã được phê duyệt – MediBook"
    msg["From"]    = GMAIL_USER
    msg["To"]      = doctor_email

    html = f"""
    <div style="font-family:Arial;max-width:520px;margin:auto;background:#f9f9f9;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#059669,#10b981);padding:24px;color:#fff;text-align:center">
        <h2 style="margin:0">✅ Hồ Sơ Đã Được Duyệt</h2>
      </div>
      <div style="padding:24px">
        <p>Xin chào <b>BS. {doctor_name}</b>,</p>
        <p>Hồ sơ đăng ký của bạn trên <b>MediBook</b> đã được <b style="color:#059669">phê duyệt</b>!</p>
        <p>Bạn có thể đăng nhập vào hệ thống tại trang Bác sĩ để bắt đầu nhận lịch hẹn từ bệnh nhân.</p>
        <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px;font-size:13px;color:#065f46">
          🎉 Chào mừng bạn gia nhập đội ngũ MediBook!
        </div>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html"))
    if GMAIL_PASS in ["13112006AZ", "your_app_password"] or not GMAIL_PASS:
        print(f"[MÔ PHỎNG] Gửi email phê duyệt tới bác sĩ: {doctor_email}")
        return True

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, doctor_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error (approval): {e}")
        return False


def send_doctor_rejection_email(doctor_email: str, doctor_name: str, reason: str):
    """Gửi email thông báo bác sĩ bị từ chối"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "❌ Hồ sơ chưa được phê duyệt – MediBook"
    msg["From"]    = GMAIL_USER
    msg["To"]      = doctor_email

    html = f"""
    <div style="font-family:Arial;max-width:520px;margin:auto;background:#f9f9f9;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#dc2626,#ef4444);padding:24px;color:#fff;text-align:center">
        <h2 style="margin:0">❌ Hồ Sơ Chưa Được Duyệt</h2>
      </div>
      <div style="padding:24px">
        <p>Xin chào <b>BS. {doctor_name}</b>,</p>
        <p>Rất tiếc, hồ sơ đăng ký của bạn trên <b>MediBook</b> <b style="color:#dc2626">chưa được phê duyệt</b>.</p>
        <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px;margin:16px 0">
          <b>Lý do:</b><br>{reason or 'Không đáp ứng yêu cầu.'}
        </div>
        <p>Bạn có thể bổ sung hồ sơ và đăng ký lại.</p>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, doctor_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error (rejection): {e}")
        return False


# ─── Background Scheduler – Gửi nhắc nhở ──────────────────────────────────

def check_and_send_reminders():
    """Kiểm tra appointments hôm nay và gửi email nhắc nhở"""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"🔍 Checking reminders for {today}...")

    try:
        apps = load_appointments()
        doctors = load_doctors()
        clinics = load_clinics()

        # Lọc appointments hôm nay, confirmed, chưa gửi nhắc nhở
        today_apps = apps[
            (apps["appointment_date"] == today) &
            (apps["status"] == "confirmed") &
            (apps["reminder_sent"].fillna(0).astype(int) == 0)
        ]

        if today_apps.empty:
            print("   Không có lịch hẹn cần nhắc nhở.")
            return

        for _, app in today_apps.iterrows():
            doctor_row = doctors[doctors["id"] == app["doctor_id"]]
            clinic_row = clinics[clinics["id"] == app["clinic_id"]]

            if doctor_row.empty or clinic_row.empty:
                continue

            doctor = doctor_row.iloc[0]
            clinic = clinic_row.iloc[0]

            sent = send_appointment_reminder(
                to_email     = app["patient_email"],
                patient_name = app["patient_name"],
                doctor_name  = doctor["name"],
                clinic_name  = clinic["name"],
                date         = app["appointment_date"],
                time         = app["appointment_time"]
            )

            if sent:
                apps.loc[apps["id"] == app["id"], "reminder_sent"] = 1

        save_appointments(apps)
        print(f"✅ Đã kiểm tra và gửi nhắc nhở xong.")
    except Exception as e:
        print(f"❌ Scheduler error: {e}")

# Khởi tạo scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(check_and_send_reminders, 'cron', hour=7, minute=0)  # 7:00 sáng mỗi ngày
scheduler.add_job(check_and_send_reminders, 'cron', hour=6, minute=30) # 6:30 sáng backup
scheduler.start()

# ─── Models ────────────────────────────────────────────────────────────────
class BookingRequest(BaseModel):
    patient_name:  str
    patient_email: str
    patient_phone: str = ""
    patient_cccd:  str = ""
    doctor_id:     int
    clinic_id:     int
    date:          str   # YYYY-MM-DD
    time:          str   # HH:MM
    symptoms:      str
    attachment:    str = ""
    booking_for:   str = "self"  # self / family / other
    patient_dob:   str = ""
    patient_gender: str = ""
    patient_address: str = ""
    payment_method: str = "at_hospital"  # wallet / card / transfer / at_hospital

class RescheduleRequest(BaseModel):
    date: str
    time: str

class RegisterRequest(BaseModel):
    username: str
    fullname: str
    email:    str
    phone:    str
    password: str
    cccd:     str = ""
    gender:   str = ""
    dob:      str = ""

class LoginRequest(BaseModel):
    email:    str
    password: str
    login_role: str = ""

class ForgotPasswordRequest(BaseModel):
    email: str
    role: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str
    role: str

class UpdateProfileRequest(BaseModel):
    fullname: str
    email:    str
    phone:    str
    cccd:     str = ""
    gender:   str = ""
    dob:      str = ""

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str

class DoctorRegisterRequest(BaseModel):
    fullname:         str
    email:            str
    phone:            str
    password:         str
    cccd:             str
    specialty:        str
    license_number:   str
    experience_years: int
    certificate_info: str
    clinic_id:        int

class MedicalRecordRequest(BaseModel):
    patient_id:     int
    appointment_id: int
    diagnosis:      str
    prescription:   str
    notes:          str = ""

class PaymentRequest(BaseModel):
    appointment_id: int
    amount:         float
    method:         str   # cash / card / momo / vnpay

class MessageRequest(BaseModel):
    to_doctor_id:   int
    appointment_id: int
    content:        str

class DoctorMessageRequest(BaseModel):
    to_user_id:     int
    appointment_id: int
    content:        str

class AftercareRequest(BaseModel):
    appointment_id:  int
    patient_id:      int
    instructions:    str
    follow_up_date:  str = ""

class AppointmentStatusRequest(BaseModel):
    action: str
    reason: str = ""

class UserStatusRequest(BaseModel):
    action: str
    password: str = ""


# ══════════════════════════════════════════════════════════════════════════
#   AUTH API ROUTES (Bệnh nhân)
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/register")
def register(req: RegisterRequest):
    users = load_users()

    # Kiểm tra email trùng (theo role patient)
    if not users.empty and not users[(users["email"] == req.email) & (users["role"] == "patient")].empty:
        raise HTTPException(status_code=409, detail="Email đã được đăng ký cho tài khoản bệnh nhân!")

    # Validate username
    import re
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập Tên đăng nhập!")
    if not re.match(r"^[a-zA-Z0-9_]+$", req.username):
        raise HTTPException(status_code=400, detail="Tên đăng nhập không được có dấu, ký tự đặc biệt hoặc khoảng trắng!")
    if not users.empty and not users[(users["username"] == req.username) & (users["role"] == "patient")].empty:
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại cho tài khoản bệnh nhân!")

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu phải từ 6 ký tự!")
    if not req.fullname.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập họ tên!")
    if "@" not in req.email:
        raise HTTPException(status_code=400, detail="Email không hợp lệ!")

    # Hash password
    pw_hash = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Tạo user mới
    new_id = int(users["id"].max()) + 1 if not users.empty and not pd.isna(users["id"].max()) else 1

    new_row = pd.DataFrame([{
        "id":            new_id,
        "fullname":      req.fullname.strip(),
        "email":         req.email.strip().lower(),
        "username":      req.username.strip().lower(),
        "phone":         req.phone.strip(),
        "password_hash": pw_hash,
        "created_at":    datetime.now().isoformat(),
        "role":          "patient",
        "cccd":          req.cccd.strip(),
        "gender":        req.gender.strip(),
        "dob":           req.dob.strip()
    }])

    updated = pd.concat([users, new_row], ignore_index=True)
    save_users(updated)

    # Auto login
    token = str(uuid.uuid4())
    sessions[token] = {"user_id": new_id, "role": "patient"}

    return {
        "success": True,
        "token": token,
        "user": {
            "id": new_id,
            "fullname": req.fullname.strip(),
            "username": req.username.strip().lower(),
            "email": req.email.strip().lower(),
            "phone": req.phone.strip(),
            "role": "patient",
            "cccd": req.cccd.strip(),
            "gender": req.gender.strip(),
            "dob": req.dob.strip()
        }
    }


@app.post("/api/login")
def login(req: LoginRequest):
    users = load_users()

    if users.empty:
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng!")

    input_val = req.email.strip().lower()
    
    # Check email or username, and filter by requested role if provided
    role_condition = (users["role"] == req.login_role) if req.login_role else True
    if "username" in users.columns:
        user_rows = users[((users["email"] == input_val) | (users["username"] == input_val)) & role_condition]
    else:
        user_rows = users[(users["email"] == input_val) & role_condition]

    if user_rows.empty:
        return JSONResponse(status_code=401, content={"detail": "Tên đăng nhập/Email hoặc mật khẩu không đúng!"})

    user = user_rows.iloc[0]
    stored_hash = user["password_hash"]

    if not bcrypt.checkpw(req.password.encode("utf-8"), stored_hash.encode("utf-8")):
        return JSONResponse(status_code=401, content={"detail": "Tên đăng nhập/Email hoặc mật khẩu không đúng!"})

    role = str(user.get("role", "patient")) if pd.notna(user.get("role")) else "patient"

    # Tăng login_count
    user_idx = users.index[users["id"] == user["id"]]
    if len(user_idx) > 0:
        val = users.loc[user_idx[0], "login_count"]
        current_count = int(val) if pd.notna(val) and str(val).strip() != "" else 0
        users.loc[user_idx[0], "login_count"] = current_count + 1
        save_users(users)

    token = str(uuid.uuid4())
    sessions[token] = {"user_id": int(user["id"]), "role": role}

    return {
        "success": True,
        "token": token,
        "user": {
            "id": int(user["id"]),
            "fullname": user["fullname"],
            "email": user["email"],
            "phone": str(user["phone"]) if pd.notna(user["phone"]) else "",
            "role": role,
            "cccd": str(user["cccd"]) if pd.notna(user.get("cccd")) else "",
            "gender": str(user.get("gender", "")) if pd.notna(user.get("gender")) else "",
            "dob": str(user.get("dob", "")) if pd.notna(user.get("dob")) else ""
        }
    }


@app.post("/api/logout")
def logout(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    sessions.pop(token, None)
    return {"success": True}


@app.post("/api/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    if req.role == "admin":
        raise HTTPException(status_code=403, detail="Không hỗ trợ khôi phục mật khẩu cho Quản trị viên!")
    
    users = load_users() if req.role == "patient" else load_doctors()
    
    # Kiểm tra email tồn tại theo role
    if req.role == "patient":
        user_rows = users[(users["email"] == req.email.strip().lower()) & (users["role"] == "patient")]
    else:
        user_rows = users[users["email"] == req.email.strip().lower()]
        
    if user_rows.empty:
        raise HTTPException(status_code=404, detail="Email không tồn tại trong hệ thống!")
        
    otp = str(random.randint(100000, 999999))
    reset_otps[req.email.strip().lower()] = {
        "otp": otp,
        "role": req.role,
        "expires": datetime.now() + timedelta(minutes=5)
    }
    
    sent = send_otp_email(req.email.strip().lower(), otp)
    if not sent:
        raise HTTPException(status_code=500, detail="Lỗi gửi email. Vui lòng thử lại sau.")
        
    return {"success": True, "message": "Mã OTP đã được gửi đến email của bạn."}


@app.post("/api/reset-password")
def reset_password(req: ResetPasswordRequest):
    email = req.email.strip().lower()
    if email not in reset_otps:
        raise HTTPException(status_code=400, detail="Không tìm thấy yêu cầu khôi phục mật khẩu cho email này.")
        
    otp_data = reset_otps[email]
    
    if otp_data["role"] != req.role:
        raise HTTPException(status_code=400, detail="Vai trò không khớp.")
        
    if otp_data["otp"] != req.otp.strip():
        raise HTTPException(status_code=400, detail="Mã OTP không chính xác.")
        
    if datetime.now() > otp_data["expires"]:
        del reset_otps[email]
        raise HTTPException(status_code=400, detail="Mã OTP đã hết hạn. Vui lòng yêu cầu lại.")
        
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải từ 6 ký tự!")
        
    new_hash = bcrypt.hashpw(req.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    if req.role == "patient":
        users = load_users()
        users.loc[(users["email"] == email) & (users["role"] == "patient"), "password_hash"] = new_hash
        save_users(users)
    elif req.role == "doctor":
        doctors = load_doctors()
        doctors.loc[doctors["email"] == email, "password_hash"] = new_hash
        save_doctors(doctors)
        
    del reset_otps[email]
    
    return {"success": True, "message": "Mật khẩu đã được khôi phục thành công. Vui lòng đăng nhập lại."}


@app.get("/api/me")
def get_me(request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    role = str(user.get("role", "patient")) if pd.notna(user.get("role")) else "patient"

    return {
        "id": int(user["id"]),
        "fullname": user["fullname"],
        "username": str(user.get("username", "")) if pd.notna(user.get("username")) else "",
        "email": user["email"],
        "phone": str(user["phone"]) if pd.notna(user["phone"]) else "",
        "role": role,
        "cccd": str(user["cccd"]) if pd.notna(user.get("cccd")) else "",
        "gender": str(user.get("gender", "")) if pd.notna(user.get("gender")) else "",
        "dob": str(user.get("dob", "")) if pd.notna(user.get("dob")) else ""
    }


@app.put("/api/me/update")
def update_profile(req: UpdateProfileRequest, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    users = load_users()
    user_id = int(user["id"])

    # Kiểm tra email trùng trong cùng role (trừ chính mình)
    current_role = str(user.get("role", "patient")) if pd.notna(user.get("role")) else "patient"
    other_emails = users[(users["id"] != user_id) & (users["role"] == current_role)]["email"].values
    if req.email.strip().lower() in other_emails:
        raise HTTPException(status_code=409, detail="Email này đã được sử dụng bởi tài khoản khác!")

    users.loc[users["id"] == user_id, "fullname"] = req.fullname.strip()
    users.loc[users["id"] == user_id, "email"]    = req.email.strip().lower()
    users.loc[users["id"] == user_id, "phone"]    = req.phone.strip()
    users.loc[users["id"] == user_id, "cccd"]     = req.cccd.strip()
    users.loc[users["id"] == user_id, "gender"]   = req.gender.strip()
    users.loc[users["id"] == user_id, "dob"]      = req.dob.strip()

    save_users(users)

    return {
        "success": True,
        "user": {
            "id": user_id,
            "fullname": req.fullname.strip(),
            "email": req.email.strip().lower(),
            "phone": req.phone.strip(),
            "cccd": req.cccd.strip(),
            "gender": req.gender.strip(),
            "dob": req.dob.strip()
        }
    }


@app.put("/api/me/password")
def change_password(req: ChangePasswordRequest, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    # Kiểm tra mật khẩu cũ
    if not bcrypt.checkpw(req.current_password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng!")

    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải từ 6 ký tự!")

    users = load_users()
    new_hash = bcrypt.hashpw(req.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    users.loc[users["id"] == int(user["id"]), "password_hash"] = new_hash
    save_users(users)

    return {"success": True, "message": "Đổi mật khẩu thành công!"}


@app.get("/api/me/appointments")
def get_my_appointments(request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    apps = load_appointments()
    doctors = load_doctors()
    clinics = load_clinics()

    user_id = int(user["id"])
    my_apps = apps[apps["user_id"].fillna(-1).astype(int) == user_id].copy()

    if my_apps.empty:
        return []

    results = []
    for _, a in my_apps.iterrows():
        doc = doctors[doctors["id"] == a["doctor_id"]]
        cli = clinics[clinics["id"] == a["clinic_id"]]
        results.append({
            "id": int(a["id"]),
            "date": a["appointment_date"],
            "time": a["appointment_time"],
            "doctor_name": doc.iloc[0]["name"] if not doc.empty else "—",
            "doctor_id": int(a["doctor_id"]),
            "clinic_name": cli.iloc[0]["name"] if not cli.empty else "—",
            "clinic_id": int(a["clinic_id"]),
            "symptoms": a["symptoms"],
            "status": a["status"]
        })

    # Sắp xếp theo ngày mới nhất
    results.sort(key=lambda x: x["date"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════
#   SERVICES API (Danh mục dịch vụ)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/services")
def get_services(clinic_id: Optional[int] = None):
    services = load_services()
    if clinic_id is not None:
        services = services[services["clinic_id"] == clinic_id]
    results = []
    for _, s in services.iterrows():
        results.append({
            "id": int(s["id"]),
            "name": s["name"],
            "description": s["description"],
            "price": int(s["price"]),
            "category": s["category"],
            "clinic_id": int(s["clinic_id"])
        })
    return results


# ══════════════════════════════════════════════════════════════════════════
#   MEDICAL RECORDS API (Hồ sơ bệnh án)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/me/medical-records")
def get_my_medical_records(request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    records = load_medical_records()
    doctors = load_doctors()
    user_id = int(user["id"])

    my_records = records[records["patient_id"].fillna(-1).astype(int) == user_id]

    if my_records.empty:
        return []

    results = []
    for _, r in my_records.iterrows():
        doc = doctors[doctors["id"] == r["doctor_id"]]
        results.append({
            "id": int(r["id"]),
            "doctor_name": doc.iloc[0]["name"] if not doc.empty else "—",
            "appointment_id": int(r["appointment_id"]),
            "diagnosis": r["diagnosis"],
            "prescription": r["prescription"],
            "notes": str(r["notes"]) if pd.notna(r["notes"]) else "",
            "created_at": r["created_at"]
        })

    results.sort(key=lambda x: x["created_at"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════
#   PAYMENT API (Thanh toán viện phí – giả lập)
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/me/payment")
def create_payment(req: PaymentRequest, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    payments = load_payments()
    new_id = int(payments["id"].max()) + 1 if not payments.empty and not pd.isna(payments["id"].max()) else 1

    new_row = pd.DataFrame([{
        "id": new_id,
        "appointment_id": req.appointment_id,
        "patient_id": int(user["id"]),
        "amount": req.amount,
        "method": req.method,
        "status": "paid",
        "paid_at": datetime.now().isoformat()
    }])

    updated = pd.concat([payments, new_row], ignore_index=True)
    save_payments(updated)

    return {"success": True, "payment_id": new_id, "status": "paid"}


@app.get("/api/me/payments")
def get_my_payments(request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    payments = load_payments()
    user_id = int(user["id"])
    my_payments = payments[payments["patient_id"].fillna(-1).astype(int) == user_id]

    if my_payments.empty:
        return []

    results = []
    for _, p in my_payments.iterrows():
        results.append({
            "id": int(p["id"]),
            "appointment_id": int(p["appointment_id"]),
            "amount": float(p["amount"]),
            "method": p["method"],
            "status": p["status"],
            "paid_at": p["paid_at"]
        })

    results.sort(key=lambda x: x["paid_at"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════
#   MESSAGES API (Liên hệ bác sĩ)
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/messages/send")
def send_message(req: MessageRequest, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    messages = load_messages()
    new_id = int(messages["id"].max()) + 1 if not messages.empty and not pd.isna(messages["id"].max()) else 1

    new_row = pd.DataFrame([{
        "id": new_id,
        "from_user_id": int(user["id"]),
        "to_doctor_id": req.to_doctor_id,
        "appointment_id": req.appointment_id,
        "content": req.content,
        "sent_at": datetime.now().isoformat(),
        "is_read": 0,
        "sender_role": "patient"
    }])

    updated = pd.concat([messages, new_row], ignore_index=True)
    save_messages(updated)

    return {"success": True, "message_id": new_id}


@app.get("/api/messages/{appointment_id}")
def get_messages(appointment_id: int, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    messages = load_messages()
    thread = messages[messages["appointment_id"] == appointment_id]

    if thread.empty:
        return []

    results = []
    for _, m in thread.iterrows():
        results.append({
            "id": int(m["id"]),
            "from_user_id": int(m["from_user_id"]),
            "to_doctor_id": int(m["to_doctor_id"]),
            "content": m["content"],
            "sent_at": m["sent_at"],
            "is_read": bool(m["is_read"]),
            "sender_role": m["sender_role"]
        })

    results.sort(key=lambda x: x["sent_at"])
    return results


# ══════════════════════════════════════════════════════════════════════════
#   AFTERCARE API (Chăm sóc sau khám)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/me/aftercare")
def get_my_aftercare(request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    aftercare = load_aftercare()
    doctors = load_doctors()
    user_id = int(user["id"])

    my_ac = aftercare[aftercare["patient_id"].fillna(-1).astype(int) == user_id]

    if my_ac.empty:
        return []

    results = []
    for _, a in my_ac.iterrows():
        doc = doctors[doctors["id"] == a["doctor_id"]]
        results.append({
            "id": int(a["id"]),
            "appointment_id": int(a["appointment_id"]),
            "doctor_name": doc.iloc[0]["name"] if not doc.empty else "—",
            "instructions": a["instructions"],
            "follow_up_date": str(a["follow_up_date"]) if pd.notna(a["follow_up_date"]) else "",
            "status": a["status"],
            "created_at": a["created_at"]
        })

    results.sort(key=lambda x: x["created_at"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════
#   DOCTOR REGISTRATION & AUTH API
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/doctor/register")
def doctor_register(req: DoctorRegisterRequest):
    users = load_users()

    # Kiểm tra email trùng cho tài khoản bác sĩ
    if not users.empty and not users[(users["email"].str.strip().str.lower() == req.email.strip().lower()) & (users["role"] == "doctor")].empty:
        raise HTTPException(status_code=409, detail="Email đã được đăng ký cho tài khoản bác sĩ!")

    # Validate
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu phải từ 6 ký tự!")
    if not req.cccd.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập số CCCD/CMND!")
    if not req.license_number.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập số giấy phép hành nghề!")

    pw_hash = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Thêm bác sĩ vào doctors.csv
    doctors = load_doctors()
    new_doc_id = int(doctors["id"].max()) + 1 if not doctors.empty and not pd.isna(doctors["id"].max()) else 1

    # Tìm specialty_id từ tên
    specialty_map = {
        "Nội tổng quát": 1, "Tim mạch": 2, "Da liễu": 3,
        "Cơ xương khớp": 4, "Tiêu hóa": 5, "Tai Mũi Họng": 6,
        "Thần kinh": 7, "Nhi khoa": 8, "Sản phụ khoa": 9
    }
    spec_id = specialty_map.get(req.specialty.strip(), 99)

    new_doc = pd.DataFrame([{
        "id": new_doc_id,
        "name": f"BS. {req.fullname.strip()}",
        "specialty_id": spec_id,
        "specialty_name": req.specialty.strip(),
        "clinic_id": req.clinic_id,
        "experience_years": req.experience_years,
        "rating": 5.0,
        "symptoms": "",
        "email": req.email.strip().lower()
    }])

    updated_docs = pd.concat([doctors, new_doc], ignore_index=True)
    save_doctors(updated_docs)

    # Thêm vào users.csv
    max_user_id = int(users["id"].max()) + 1 if not users.empty and not pd.isna(users["id"].max()) else 1
    new_user = pd.DataFrame([{
        "id": max_user_id,
        "fullname": req.fullname.strip(),
        "email": req.email.strip().lower(),
        "phone": req.phone.strip(),
        "password_hash": pw_hash,
        "created_at": datetime.now().isoformat(),
        "role": "doctor",
        "cccd": req.cccd.strip(),
        "login_count": 0,
        "status": "active",
        "gender": "",
        "dob": ""
    }])
    save_users(pd.concat([users, new_user], ignore_index=True))

    try:
        send_doctor_approval_email(req.email.strip().lower(), req.fullname.strip())
    except Exception:
        pass

    return {"success": True, "message": "Đăng ký tài khoản bác sĩ thành công và đã được kích hoạt!"}


@app.post("/api/doctor/login")
def doctor_login(req: LoginRequest):
    users = load_users()
    user_rows = users[
        (users["email"] == req.email.strip().lower()) &
        (users["role"] == "doctor")
    ]
    
    if user_rows.empty:
        return JSONResponse(status_code=401, content={"detail": "Email hoặc mật khẩu không đúng!"})

    user = user_rows.iloc[0]
    
    if user["status"] != "active":
        return JSONResponse(status_code=403, content={"detail": "Tài khoản đã bị khóa!"})

    stored_hash = user["password_hash"]
    if not bcrypt.checkpw(req.password.encode("utf-8"), stored_hash.encode("utf-8")):
        return JSONResponse(status_code=401, content={"detail": "Email hoặc mật khẩu không đúng!"})

    # Find doctor in doctors.csv
    doctors = load_doctors()
    doc_match = doctors[doctors["email"] == req.email.strip().lower()]
    if doc_match.empty:
        return JSONResponse(status_code=404, content={"detail": "Không tìm thấy hồ sơ bác sĩ công khai!"})
        
    doctor_id = int(doc_match.iloc[0]["id"])
    doc_record = doc_match.iloc[0]

    # Tăng login_count
    user_idx = users.index[users["id"] == user["id"]]
    if len(user_idx) > 0:
        val = users.loc[user_idx[0], "login_count"]
        current_count = int(val) if pd.notna(val) and str(val).strip() != "" else 0
        users.loc[user_idx[0], "login_count"] = current_count + 1
        save_users(users)

    token = str(uuid.uuid4())
    sessions[token] = {"user_id": int(user["id"]), "doctor_id": doctor_id, "role": "doctor"}

    return {
        "success": True,
        "token": token,
        "doctor": {
            "id": doctor_id,
            "fullname": user["fullname"],
            "email": user["email"],
            "specialty": doc_record["specialty_name"],
            "clinic_id": int(doc_record["clinic_id"]) if pd.notna(doc_record.get("clinic_id")) else None
        }
    }


@app.get("/api/doctor/me")
def get_doctor_me(request: Request):
    role = get_session_role(request)
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Cần quyền bác sĩ!")

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = sessions.get(token, {})
    doctor_id = session.get("doctor_id")

    doctors = load_doctors()
    doc = doctors[doctors["id"] == doctor_id]

    if doc.empty:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin bác sĩ!")

    d = doc.iloc[0]
    clinics = load_clinics()
    clinic = clinics[clinics["id"] == d["clinic_id"]]

    return {
        "id": int(d["id"]),
        "name": d["name"],
        "specialty_name": d["specialty_name"],
        "experience_years": int(d["experience_years"]),
        "rating": float(d["rating"]),
        "clinic_name": clinic.iloc[0]["name"] if not clinic.empty else "—",
        "clinic_id": int(d["clinic_id"]),
        "email": str(d["email"]) if pd.notna(d.get("email")) else ""
    }


@app.get("/api/doctor/appointments")
def get_doctor_appointments(request: Request):
    role = get_session_role(request)
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Cần quyền bác sĩ!")

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = sessions.get(token, {})
    doctor_id = session.get("doctor_id")

    apps = load_appointments()
    clinics = load_clinics()

    doc_apps = apps[apps["doctor_id"] == doctor_id].copy()

    if doc_apps.empty:
        return []

    results = []
    for _, a in doc_apps.iterrows():
        cli = clinics[clinics["id"] == a["clinic_id"]]
        results.append({
            "id": int(a["id"]),
            "patient_name": a["patient_name"],
            "patient_email": a["patient_email"],
            "date": a["appointment_date"],
            "time": a["appointment_time"],
            "symptoms": a["symptoms"],
            "status": a["status"],
            "clinic_name": cli.iloc[0]["name"] if not cli.empty else "—",
            "user_id": int(a["user_id"]) if pd.notna(a["user_id"]) else None
        })

    results.sort(key=lambda x: x["date"], reverse=True)
    return results


@app.post("/api/doctor/medical-record")
def create_medical_record(req: MedicalRecordRequest, request: Request):
    role = get_session_role(request)
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Cần quyền bác sĩ!")

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = sessions.get(token, {})
    doctor_id = session.get("doctor_id")

    records = load_medical_records()
    new_id = int(records["id"].max()) + 1 if not records.empty and not pd.isna(records["id"].max()) else 1

    new_row = pd.DataFrame([{
        "id": new_id,
        "patient_id": req.patient_id,
        "doctor_id": doctor_id,
        "appointment_id": req.appointment_id,
        "diagnosis": req.diagnosis,
        "prescription": req.prescription,
        "notes": req.notes,
        "created_at": datetime.now().isoformat()
    }])

    updated = pd.concat([records, new_row], ignore_index=True)
    save_medical_records(updated)

    return {"success": True, "record_id": new_id}


@app.post("/api/doctor/aftercare")
def create_aftercare(req: AftercareRequest, request: Request):
    role = get_session_role(request)
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Cần quyền bác sĩ!")

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = sessions.get(token, {})
    doctor_id = session.get("doctor_id")

    aftercare = load_aftercare()
    new_id = int(aftercare["id"].max()) + 1 if not aftercare.empty and not pd.isna(aftercare["id"].max()) else 1

    new_row = pd.DataFrame([{
        "id": new_id,
        "appointment_id": req.appointment_id,
        "patient_id": req.patient_id,
        "doctor_id": doctor_id,
        "instructions": req.instructions,
        "follow_up_date": req.follow_up_date,
        "status": "active",
        "created_at": datetime.now().isoformat()
    }])

    updated = pd.concat([aftercare, new_row], ignore_index=True)
    save_aftercare(updated)

    return {"success": True, "aftercare_id": new_id}


@app.post("/api/doctor/message")
def doctor_send_message(req: DoctorMessageRequest, request: Request):
    """Bác sĩ gửi tin nhắn cho bệnh nhân"""
    role = get_session_role(request)
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Cần quyền bác sĩ!")

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = sessions.get(token, {})
    doctor_id = session.get("doctor_id")

    messages = load_messages()
    new_id = int(messages["id"].max()) + 1 if not messages.empty and not pd.isna(messages["id"].max()) else 1

    new_row = pd.DataFrame([{
        "id": new_id,
        "from_user_id": doctor_id,
        "to_doctor_id": doctor_id,
        "appointment_id": req.appointment_id,
        "content": req.content,
        "sent_at": datetime.now().isoformat(),
        "is_read": 0,
        "sender_role": "doctor"
    }])

    updated = pd.concat([messages, new_row], ignore_index=True)
    save_messages(updated)

    return {"success": True, "message_id": new_id}


@app.get("/api/doctor/messages/{appointment_id}")
def doctor_get_messages(appointment_id: int, request: Request):
    """Bác sĩ xem tin nhắn theo appointment"""
    role = get_session_role(request)
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Cần quyền bác sĩ!")

    messages = load_messages()
    thread = messages[messages["appointment_id"] == appointment_id]

    if thread.empty:
        return []

    results = []
    for _, m in thread.iterrows():
        results.append({
            "id": int(m["id"]),
            "from_user_id": int(m["from_user_id"]),
            "content": m["content"],
            "sent_at": m["sent_at"],
            "sender_role": m["sender_role"]
        })

    results.sort(key=lambda x: x["sent_at"])
    return results





# ─── Clinic & Doctor API Routes ───────────────────────────────────────────

@app.get("/api/clinics/nearby")
def get_nearby_clinics(lat: float, lng: float):
    df = load_clinics()
    df["distance"] = df.apply(lambda r: haversine(lat, lng, r["lat"], r["lng"]), axis=1)
    df = df.sort_values("distance")
    return df[["id","name","address","phone","distance"]].to_dict(orient="records")

@app.get("/api/clinics/map")
def get_clinics_map(lat: float = None, lng: float = None):
    """Trả về danh sách phòng khám với tọa độ để hiển thị trên bản đồ.
    Nếu truyền lat/lng thì tính thêm khoảng cách và sắp xếp theo gần nhất."""
    df = load_clinics()
    cols = ["id", "name", "address", "phone", "lat", "lng"]
    # Thêm các cột tuỳ chọn nếu tồn tại
    for col in ["specialty", "rating", "open_hours", "image"]:
        if col in df.columns:
            cols.append(col)
    result = df[cols].copy()
    if lat is not None and lng is not None:
        result["distance"] = result.apply(
            lambda r: haversine(lat, lng, r["lat"], r["lng"]), axis=1
        )
        result = result.sort_values("distance")
    return result.to_dict(orient="records")

@app.get("/api/clinics")
def get_all_clinics():
    df = load_clinics()
    cols = ["id", "name", "address", "phone"]
    if "specialty_ids" in df.columns:
        cols.append("specialty_ids")
    return df[cols].to_dict(orient="records")

@app.get("/api/specialties")
def get_specialties():
    # Hardcoded specialties as mapped in the script
    return [
        {"id": 1, "name": "Nội tổng quát"},
        {"id": 2, "name": "Tim mạch"},
        {"id": 3, "name": "Da liễu"},
        {"id": 4, "name": "Cơ xương khớp"},
        {"id": 5, "name": "Tiêu hóa"},
        {"id": 6, "name": "Tai Mũi Họng"},
        {"id": 7, "name": "Thần kinh"},
        {"id": 8, "name": "Nhi khoa"},
        {"id": 9, "name": "Sản phụ khoa"},
        {"id": 10, "name": "Nhãn khoa"},
        {"id": 11, "name": "Ung bướu"},
        {"id": 12, "name": "Nam khoa"},
        {"id": 13, "name": "Nha khoa"},
        {"id": 14, "name": "Thận - Tiết niệu"},
        {"id": 15, "name": "Hô hấp"},
        {"id": 16, "name": "Chấn thương chỉnh hình"},
        {"id": 17, "name": "Phục hồi chức năng"},
        {"id": 18, "name": "Y học cổ truyền"},
        {"id": 19, "name": "Nội tiết"},
        {"id": 20, "name": "Truyền nhiễm"},
        {"id": 21, "name": "Dị ứng - Miễn dịch"},
        {"id": 22, "name": "Dinh dưỡng"}
    ]

@app.get("/api/doctors")
def get_doctors(clinic_id: int = None, specialty_id: int = None, symptoms: str = ""):
    doctors = load_doctors()
    services = load_services()
    df = doctors.copy()
    if clinic_id:
        df = df[df["clinic_id"] == clinic_id]
    if specialty_id:
        df = df[df["specialty_id"] == specialty_id]
    if symptoms.strip():
        kws = [s.strip().lower() for s in symptoms.split(",")]
        def match(sym_str):
            sym_str = str(sym_str).lower()
            return any(k in sym_str for k in kws)
        df = df[df["symptoms"].apply(match)]

    results = []
    for _, d in df.iterrows():
        fee = 0
        if not services.empty:
            matched = services[
                (services["category"] == d["specialty_name"]) &
                (services["clinic_id"] == d["clinic_id"])
            ]
            if not matched.empty:
                fee = int(matched.iloc[0]["price"])
        results.append({
            "id": int(d["id"]),
            "name": d["name"],
            "specialty_name": d["specialty_name"],
            "experience_years": int(d["experience_years"]),
            "rating": float(d["rating"]),
            "symptoms": d["symptoms"],
            "clinic_id": int(d["clinic_id"]),
            "consultation_fee": fee
        })
    return results

@app.get("/api/specialties")
def get_specialties(clinic_id: int = None):
    doctors = load_doctors()
    if clinic_id:
        df = doctors[doctors["clinic_id"] == clinic_id]
    else:
        df = doctors
    df = df[["specialty_id","specialty_name"]].drop_duplicates()
    return df.to_dict(orient="records")

@app.get("/api/slots")
def get_slots(doctor_id: int, date: str):
    """Trả về các slot giờ còn trống trong ngày"""
    all_slots = ["08:00","08:30","09:00","09:30","10:00","10:30",
                 "11:00","11:30","13:30","14:00","14:30","15:00",
                 "15:30","16:00","16:30","17:00"]
    apps = load_appointments()
    booked = apps[(apps["doctor_id"] == doctor_id) &
                  (apps["appointment_date"] == date) &
                  (apps["status"] == "confirmed")]["appointment_time"].tolist()
    return {"all_slots": all_slots, "booked": booked, "available": [s for s in all_slots if s not in booked]}

@app.post("/api/book")
def book_appointment(req: BookingRequest, request: Request):
    apps = load_appointments()

    # Kiểm tra trùng lịch
    conflict = apps[
        (apps["doctor_id"] == req.doctor_id) &
        (apps["appointment_date"] == req.date) &
        (apps["appointment_time"] == req.time) &
        (apps["status"] == "confirmed")
    ]
    if not conflict.empty:
        # Gợi ý giờ thay thế
        slots_info = get_slots(req.doctor_id, req.date)
        available = slots_info["available"]
        available = [s for s in available if s != req.time]
        raise HTTPException(status_code=409, detail={
            "message": "Giờ này đã có người đặt!",
            "suggestions": available[:4]
        })

    # Tạo ID mới
    new_id = int(apps["id"].max()) + 1 if not apps.empty else 1

    # Lấy thông tin bác sĩ & phòng khám
    doctors  = load_doctors()
    clinics  = load_clinics()
    doctor   = doctors[doctors["id"] == req.doctor_id].iloc[0]
    clinic   = clinics[clinics["id"] == req.clinic_id].iloc[0]

    # Lấy user_id nếu đã đăng nhập
    current_user = get_current_user(request)
    user_id = int(current_user["id"]) if current_user is not None else None

    new_row = pd.DataFrame([{
        "id": new_id,
        "patient_name":  req.patient_name,
        "patient_email": req.patient_email,
        "patient_phone": req.patient_phone,
        "doctor_id":     req.doctor_id,
        "clinic_id":     req.clinic_id,
        "appointment_date": req.date,
        "appointment_time": req.time,
        "symptoms":      req.symptoms,
        "status":        "confirmed",
        "user_id":       user_id,
        "reminder_sent": 0,
        "patient_phone": req.patient_phone,
        "attachment":    req.attachment,
        "rejection_reason": "",
        "booking_for":   req.booking_for,
        "booking_code":  f"MB-{datetime.now().strftime('%Y%m%d')}-{new_id:04d}",
        "patient_dob":   req.patient_dob,
        "patient_gender": req.patient_gender,
        "patient_address": req.patient_address,
        "payment_method": req.payment_method,
        "payment_status": "pending" if req.payment_method != "at_hospital" else "pay_later"
    }])
    updated = pd.concat([apps, new_row], ignore_index=True)
    save_appointments(updated)

    # Gửi email cho BỆNH NHÂN
    email_sent = send_email(
        to_email     = req.patient_email,
        patient_name = req.patient_name,
        doctor_name  = doctor["name"],
        clinic_name  = clinic["name"],
        date         = req.date,
        time         = req.time
    )

    # Gửi email thông báo cho BÁC SĨ
    doctor_email = str(doctor.get("email", ""))
    doctor_email_sent = False
    if doctor_email and "@" in doctor_email:
        doctor_email_sent = send_doctor_notification(
            doctor_email = doctor_email,
            doctor_name  = doctor["name"],
            patient_name = req.patient_name,
            clinic_name  = clinic["name"],
            date         = req.date,
            time         = req.time,
            symptoms     = req.symptoms
        )

    return {
        "success": True,
        "booking_id": new_id,
        "booking_code": f"MB-{datetime.now().strftime('%Y%m%d')}-{new_id:04d}",
        "doctor":  doctor["name"],
        "clinic":  clinic["name"],
        "date":    req.date,
        "time":    req.time,
        "email_sent": email_sent,
        "doctor_notified": doctor_email_sent,
        "payment_method": req.payment_method
    }


@app.get("/api/appointments/lookup")
def lookup_appointment(code: str):
    apps = load_appointments()
    app = apps[apps["booking_code"] == code.strip()]
    if app.empty:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã lịch hẹn!")
    app_row = app.iloc[0]
    doctors = load_doctors()
    clinics = load_clinics()
    doc = doctors[doctors["id"] == app_row["doctor_id"]]
    cli = clinics[clinics["id"] == app_row["clinic_id"]]
    return {
        "id": int(app_row["id"]),
        "booking_code": str(app_row["booking_code"]),
        "status": str(app_row["status"]),
        "date": str(app_row["appointment_date"]),
        "time": str(app_row["appointment_time"]),
        "doctor_id": int(app_row["doctor_id"]),
        "doctor_name": doc.iloc[0]["name"] if not doc.empty else "—",
        "clinic_id": int(app_row["clinic_id"]),
        "clinic_name": cli.iloc[0]["name"] if not cli.empty else "—",
        "patient_name": str(app_row["patient_name"]),
        "patient_phone": str(app_row.get("patient_phone", "")),
        "patient_email": str(app_row["patient_email"]),
        "patient_cccd": str(app_row.get("patient_cccd", "")),
        "patient_dob": str(app_row.get("patient_dob", "")),
        "patient_gender": str(app_row.get("patient_gender", "")),
        "patient_address": str(app_row.get("patient_address", "")),
        "symptoms": str(app_row.get("symptoms", "")),
        "booking_for": str(app_row.get("booking_for", "self")),
        "payment_method": str(app_row.get("payment_method", "at_hospital")),
    }


@app.put("/api/appointments/lookup/{code}")
def update_appointment_guest(code: str, req: BookingRequest):
    apps = load_appointments()
    app_idx = apps.index[apps["booking_code"] == code.strip()]
    if len(app_idx) == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn!")
    
    app_id = int(apps.loc[app_idx[0], "id"])
    conflict = apps[
        (apps["doctor_id"] == req.doctor_id) &
        (apps["appointment_date"] == req.date) &
        (apps["appointment_time"] == req.time) &
        (apps["status"] == "confirmed") &
        (apps["id"] != app_id)
    ]
    if not conflict.empty:
        slots_info = get_slots(req.doctor_id, req.date)
        available = [s for s in slots_info["available"] if s != req.time]
        raise HTTPException(status_code=409, detail={
            "message": "Giờ này đã có người đặt!",
            "suggestions": available[:4]
        })
    
    apps.loc[app_idx[0], "patient_name"] = req.patient_name
    apps.loc[app_idx[0], "patient_email"] = req.patient_email
    apps.loc[app_idx[0], "patient_phone"] = req.patient_phone
    apps.loc[app_idx[0], "patient_cccd"] = req.patient_cccd
    apps.loc[app_idx[0], "doctor_id"] = req.doctor_id
    apps.loc[app_idx[0], "clinic_id"] = req.clinic_id
    apps.loc[app_idx[0], "appointment_date"] = req.date
    apps.loc[app_idx[0], "appointment_time"] = req.time
    apps.loc[app_idx[0], "symptoms"] = req.symptoms
    apps.loc[app_idx[0], "booking_for"] = req.booking_for
    apps.loc[app_idx[0], "patient_dob"] = req.patient_dob
    apps.loc[app_idx[0], "patient_gender"] = req.patient_gender
    apps.loc[app_idx[0], "patient_address"] = req.patient_address
    apps.loc[app_idx[0], "payment_method"] = req.payment_method
    
    save_appointments(apps)
    return {"success": True, "booking_code": code}


@app.post("/api/appointments/lookup/{code}/cancel")
def cancel_appointment_guest(code: str):
    apps = load_appointments()
    app_idx = apps.index[apps["booking_code"] == code.strip()]
    if len(app_idx) == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn!")
    apps.loc[app_idx[0], "status"] = "cancelled"
    save_appointments(apps)
    return {"success": True}


@app.put("/api/me/appointments/{app_id}")
def update_appointment_user(app_id: int, req: BookingRequest, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    apps = load_appointments()
    app_idx = apps.index[apps["id"] == app_id]
    if len(app_idx) == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")

    app_row = apps.loc[app_idx[0]]
    if app_row["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Không có quyền!")

    conflict = apps[
        (apps["doctor_id"] == req.doctor_id) &
        (apps["appointment_date"] == req.date) &
        (apps["appointment_time"] == req.time) &
        (apps["status"] == "confirmed") &
        (apps["id"] != app_id)
    ]
    if not conflict.empty:
        slots_info = get_slots(req.doctor_id, req.date)
        available = [s for s in slots_info["available"] if s != req.time]
        raise HTTPException(status_code=409, detail={
            "message": "Giờ này đã có người đặt!",
            "suggestions": available[:4]
        })

    apps.loc[app_idx[0], "patient_name"] = req.patient_name
    apps.loc[app_idx[0], "patient_email"] = req.patient_email
    apps.loc[app_idx[0], "patient_phone"] = req.patient_phone
    apps.loc[app_idx[0], "patient_cccd"] = req.patient_cccd
    apps.loc[app_idx[0], "doctor_id"] = req.doctor_id
    apps.loc[app_idx[0], "clinic_id"] = req.clinic_id
    apps.loc[app_idx[0], "appointment_date"] = req.date
    apps.loc[app_idx[0], "appointment_time"] = req.time
    apps.loc[app_idx[0], "symptoms"] = req.symptoms
    apps.loc[app_idx[0], "booking_for"] = req.booking_for
    apps.loc[app_idx[0], "patient_dob"] = req.patient_dob
    apps.loc[app_idx[0], "patient_gender"] = req.patient_gender
    apps.loc[app_idx[0], "patient_address"] = req.patient_address
    apps.loc[app_idx[0], "payment_method"] = req.payment_method

    save_appointments(apps)
    return {"success": True, "booking_code": str(app_row["booking_code"])}

@app.post("/api/me/appointments/{app_id}/reschedule")
def reschedule_appointment(app_id: int, req: RescheduleRequest, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")

    apps = load_appointments()
    app_idx = apps.index[apps["id"] == app_id]
    if len(app_idx) == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")

    app_row = apps.loc[app_idx[0]]
    if app_row["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Không có quyền!")

    if app_row["status"] not in ["confirmed"]:
        raise HTTPException(status_code=400, detail="Chỉ có thể đổi lịch hẹn đang xác nhận!")

    # Kiểm tra slot mới có trống không
    doctor_id = app_row["doctor_id"]
    conflict = apps[
        (apps["doctor_id"] == doctor_id) &
        (apps["appointment_date"] == req.date) &
        (apps["appointment_time"] == req.time) &
        (apps["status"] == "confirmed") &
        (apps["id"] != app_id)
    ]
    if not conflict.empty:
        raise HTTPException(status_code=409, detail="Giờ này đã có người đặt!")

    apps.loc[app_idx[0], "appointment_date"] = req.date
    apps.loc[app_idx[0], "appointment_time"] = req.time
    save_appointments(apps)

    return {"success": True, "new_date": req.date, "new_time": req.time}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    import os, uuid
    filename = f"{uuid.uuid4()}_{file.filename}"
    filepath = os.path.join(BASE, "static", "uploads", filename)
    with open(filepath, "wb") as f:
        f.write(await file.read())
    return {"success": True, "url": f"/static/uploads/{filename}"}

@app.post("/api/me/appointments/{app_id}/cancel")
def cancel_appointment(app_id: int, request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập!")
    
    apps = load_appointments()
    app_idx = apps.index[apps["id"] == app_id]
    if len(app_idx) == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
        
    app_row = apps.loc[app_idx[0]]
    if app_row["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Không có quyền!")
        
    apps.loc[app_idx[0], "status"] = "cancelled"
    save_appointments(apps)
    return {"success": True}

@app.post("/api/doctor/appointments/{app_id}/status")
def doctor_appointment_status(app_id: int, req: AppointmentStatusRequest, request: Request):
    role = get_session_role(request)
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Cần quyền bác sĩ!")

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = sessions.get(token, {})
    doctor_id = session.get("doctor_id")

    apps = load_appointments()
    app_idx = apps.index[apps["id"] == app_id]
    if len(app_idx) == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
        
    app_row = apps.loc[app_idx[0]]
    if app_row["doctor_id"] != doctor_id:
        raise HTTPException(status_code=403, detail="Không có quyền!")

    if req.action == "approve":
        apps.loc[app_idx[0], "status"] = "confirmed"
    elif req.action == "reject":
        apps.loc[app_idx[0], "status"] = "rejected"
        apps.loc[app_idx[0], "rejection_reason"] = req.reason
        
    save_appointments(apps)
    return {"success": True}



# ─── Serve Frontend ────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════
#   ADMIN API ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/admin/stats")
def get_admin_stats(request: Request):
    user = get_current_user(request)
    if user is None or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Chỉ dành cho Admin")
    
    users = load_users()
    doctors = load_doctors()
    appointments = load_appointments()
    payments = load_payments()
    
    total_doctors = len(doctors)
    total_patients = len(users[users["role"] == "patient"])
    total_appointments = len(appointments)
    
    total_revenue = 0
    if not payments.empty:
        total_revenue = payments["amount"].sum()
        
    return {
        "total_doctors": total_doctors,
        "total_patients": total_patients,
        "total_appointments": total_appointments,
        "total_revenue": int(total_revenue)
    }

@app.get("/api/admin/doctors")
def get_admin_doctors(request: Request):
    user = get_current_user(request)
    if user is None or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Chỉ dành cho Admin")
        
    doctors = load_doctors()
    users = load_users()
    
    res = []
    for _, doc in doctors.iterrows():
        # Tìm account tương ứng trong users.csv
        doc_email = str(doc["email"]).strip().lower()
        user_rows = users[(users["email"] == doc_email) & (users["role"] == "doctor")]
        status = "active"
        if not user_rows.empty:
            status = user_rows.iloc[0].get("status", "active")
            
        res.append({
            "id": int(doc["id"]),
            "code": f"BS{int(doc['id']):03d}",
            "name": str(doc["name"]),
            "specialty": str(doc["specialty"]),
            "phone": str(doc["phone"]),
            "status": status,
            "avatar": str(doc.get("avatar", "https://i.pravatar.cc/150?img=12"))
        })
    return res

@app.get("/api/admin/patients")
def get_admin_patients(request: Request):
    user = get_current_user(request)
    if user is None or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Chỉ dành cho Admin")
        
    users = load_users()
    patients = users[users["role"] == "patient"]
    
    res = []
    for _, p in patients.iterrows():
        res.append({
            "id": int(p["id"]),
            "code": f"BN{int(p['id']):03d}",
            "name": str(p["fullname"]),
            "dob": str(p.get("dob", "")),
            "gender": str(p.get("gender", "")),
            "phone": str(p.get("phone", "")),
            "email": str(p["email"])
        })
    return res

@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404)
    return FileResponse(os.path.join(BASE, "index.html"))

# ─── Startup / Shutdown & Scripts ──────────────────────────────────────────

def run_temp_reorder():
    import re
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    new_html = r'''        <div class="steps-indicator" id="stepsIndicator">
          <div class="steps-wrap">
            <div class="step-dot active" id="dot1">1</div>
            <div class="step-label">Bệnh nhân</div>
          </div>
          <div class="step-line" id="line1"></div>
          <div class="steps-wrap">
            <div class="step-dot" id="dot2">2</div>
            <div class="step-label">BS & Khoa</div>
          </div>
          <div class="step-line" id="line2"></div>
          <div class="steps-wrap">
            <div class="step-dot" id="dot3">3</div>
            <div class="step-label">Thời gian</div>
          </div>
          <div class="step-line" id="line3"></div>
          <div class="steps-wrap">
            <div class="step-dot" id="dot4">4</div>
            <div class="step-label">Xác nhận</div>
          </div>
          <div class="step-line" id="line4"></div>
          <div class="steps-wrap">
            <div class="step-dot" id="dot5">5</div>
            <div class="step-label">Thanh toán</div>
          </div>
          <div class="step-line" id="line5"></div>
          <div class="steps-wrap">
            <div class="step-dot" id="dot6">6</div>
            <div class="step-label">Hoàn tất</div>
          </div>
        </div>
      </div>

      <div class="container">
        <!-- Bước 1: Thông tin BN -->
        <div class="card" id="step1">
          <div class="badge badge-blue">👤 Bước 1</div>
          <div class="card-title">Thông Tin Bệnh Nhân</div>
          <div class="card-sub">Lựa chọn người cần khám và điền thông tin.</div>

          <div class="form-group" style="margin-top:20px;">
            <label>🎯 Bạn đặt lịch khám cho ai?</label>
            <div style="display:flex; gap:10px; margin-top:8px;">
              <label class="radio-card" style="flex:1;">
                <input type="radio" name="bookingFor" value="self" checked onchange="handleBookingForChange()">
                <div class="radio-card-content">
                  <div style="font-size:24px;">👤</div>
                  <div style="font-weight:600; margin-top:8px;">Bản thân</div>
                </div>
              </label>
              <label class="radio-card" style="flex:1;">
                <input type="radio" name="bookingFor" value="family" onchange="handleBookingForChange()">
                <div class="radio-card-content">
                  <div style="font-size:24px;">👨‍👩‍👧</div>
                  <div style="font-weight:600; margin-top:8px;">Gia đình</div>
                </div>
              </label>
              <label class="radio-card" style="flex:1;">
                <input type="radio" name="bookingFor" value="other" onchange="handleBookingForChange()">
                <div class="radio-card-content">
                  <div style="font-size:24px;">🤝</div>
                  <div style="font-weight:600; margin-top:8px;">Người khác</div>
                </div>
              </label>
            </div>
          </div>

          <div id="patientFormContainer">
            <div id="guestBookingNotice" class="alert alert-warn" style="display:none; margin-top:16px;">
              ⚠️ Bạn đang đặt lịch với tư cách <b>Khách</b>. Vui lòng điền đầy đủ thông tin. Đăng nhập để tiết kiệm thời gian.
            </div>

            <div class="form-row" style="margin-top:20px;">
              <div class="form-group" id="fgPatientName">
                <label>👤 Họ và tên bệnh nhân <span style="color:var(--danger)">*</span></label>
                <input type="text" id="patientName" placeholder="Nguyễn Văn A" oninput="clearFieldError(this)" />
              </div>
              <div class="form-group" id="fgPatientEmail">
                <label>📧 Email liên hệ <span style="color:var(--danger)">*</span></label>
                <input type="email" id="patientEmail" placeholder="email@gmail.com" oninput="clearFieldError(this)" />
              </div>
            </div>

            <div class="form-row">
              <div class="form-group" id="fgPatientPhone">
                <label>📱 Số điện thoại <span style="color:var(--danger)">*</span></label>
                <input type="tel" id="patientPhone" placeholder="0901234567" oninput="clearFieldError(this)" />
              </div>
              <div class="form-group" id="fgPatientCCCD">
                <label>🪪 Số CCCD</label>
                <input type="text" id="patientCCCD" placeholder="Số Căn cước công dân" oninput="clearFieldError(this)" />
              </div>
            </div>

            <div class="form-row">
              <div class="form-group">
                <label>📅 Ngày sinh</label>
                <input type="date" id="patientDOB" />
              </div>
              <div class="form-group">
                <label>⚧ Giới tính</label>
                <select id="patientGender">
                  <option value="">-- Chọn giới tính --</option>
                  <option value="Nam">Nam</option>
                  <option value="Nữ">Nữ</option>
                  <option value="Khác">Khác</option>
                </select>
              </div>
            </div>

            <div class="form-group">
              <label>📍 Địa chỉ</label>
              <input type="text" id="patientAddress" placeholder="Số nhà, đường, phường/xã, quận/huyện, tỉnh/thành phố" />
            </div>

            <div class="form-group" id="fgSymptoms">
              <label>🤒 Triệu chứng / Lý do khám</label>
              <textarea id="symptomsInput" rows="3" placeholder="Mô tả triệu chứng, biểu hiện bệnh..."></textarea>
            </div>

            <div class="form-group">
              <label>📎 File đính kèm (Kết quả khám cũ, đơn thuốc...)</label>
              <input type="file" id="patientAttachment" accept="image/*,.pdf" onchange="uploadAttachment(this)" />
              <input type="hidden" id="patientAttachmentUrl" />
              <div id="uploadStatus" style="font-size:12px; margin-top:4px; color:var(--primary)"></div>
            </div>
          </div>

          <div style="display:flex; gap:10px; margin-top:20px">
            <button class="btn btn-primary" onclick="goStep(2)" style="flex:1">Tiếp theo →</button>
          </div>
        </div>

        <!-- Bước 2: BS & Khoa -->
        <div class="card" id="step2" style="display:none">
          <div class="badge badge-blue">🏥 Bước 2</div>
          <div class="card-title">Chọn Chuyên Khoa & Bác Sĩ</div>
          <div class="card-sub">Lựa chọn bác sĩ phù hợp.</div>

          <div class="form-group" style="margin-bottom:20px; margin-top:20px;">
            <label>🏥 Phòng khám (tùy chọn)</label>
            <div style="display:flex; gap:10px;">
              <select id="bookingClinicSelect" onchange="handleClinicChange()" style="flex:1;">
                <option value="">-- Tất cả phòng khám --</option>
              </select>
              <button class="btn btn-primary" type="button" onclick="openMapModal()"
                style="padding: 12px 18px; font-size: 14px; white-space: nowrap;">🗺️ Chọn trên Bản đồ</button>
            </div>
          </div>

          <div id="doctorSelectionSection" style="display:none; margin-top:30px;">
            <label id="step2Title"
              style="font-weight:600; font-size:16px; margin-bottom:12px; display:block; color:#1e293b;">Danh sách Bác sĩ</label>
            <div id="doctorResult"></div>
          </div>

          <div id="step2Btns" style="display:none; gap:10px; margin-top:20px">
            <button class="btn btn-outline" onclick="goStep(1)" style="flex:1">← Quay lại</button>
            <button class="btn btn-primary" id="step2NextBtn" onclick="goStep(3)" style="flex:1">Tiếp theo →</button>
          </div>
        </div>

        <!-- Bước 3: Lịch Hẹn -->
        <div class="card" id="step3" style="display:none">
          <div class="badge badge-blue">📅 Bước 3</div>
          <div class="card-title">Chọn Ngày & Giờ Khám</div>

          <div id="slotSection" style="margin-top:20px;">
            <label>📅 Ngày khám</label>
            <input type="date" id="appointmentDate" style="margin-bottom:16px" onchange="loadSlots()" />
            <label>⏰ Chọn giờ khám</label>
            <div class="slot-grid" id="slotGrid"></div>
          </div>
          <div id="step3Btns" style="display:none; gap:10px; margin-top:20px">
            <button class="btn btn-outline" onclick="goStep(2)" style="flex:1">← Quay lại</button>
            <button class="btn btn-primary" onclick="goStep(4)" style="flex:2">Xác nhận lịch →</button>
          </div>
        </div>

        <!-- Bước 4: Xác nhận -->'''

    pattern = re.compile(r'        <div class="steps-indicator" id="stepsIndicator">.*?<!-- Bước 4: Xác nhận -->', re.DOTALL)
    content = pattern.sub(new_html, content)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated index.html")

if __name__ == "__main__":
    import sys
    import uvicorn
    if len(sys.argv) > 1:
        if sys.argv[1] == "reorder":
            run_temp_reorder()
            sys.exit(0)
            
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)