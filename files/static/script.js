/* ============================================================
   MediBook – Single Page App Script
   ============================================================ */

const state = {
  user: null,    // { id, fullname, email, role, ... }
  token: null,
  isGuest: false,

  // Booking state
  symptoms: '', clinic: null, doctor: null, date: '', time: '', currentStep: 1,

  // Shared modals state
  currentRecordAppId: null, currentRecordPatientId: null,
  currentMessageAppId: null, currentMessageUserId: null,
  currentDocId: null, paymentAppointmentId: null, paymentMethod: 'cash',

  // Map state
  map: null, mapMarkers: [], userMarker: null, userCircle: null, allClinics: [], selectedClinic: null,
  userLat: null, userLng: null,

};

const $ = id => document.getElementById(id);
const API = (url, options = {}) => {
  const opts = { ...options };
  if (!opts.headers) opts.headers = {};
  if (state.token) opts.headers['Authorization'] = `Bearer ${state.token}`;
  if (opts.body && !opts.headers['Content-Type']) {
    opts.headers['Content-Type'] = 'application/json';
  }
  return fetch(url, opts).then(r => r.json().then(data => ({ ok: r.ok, status: r.status, data })));
};

function showFormMessage(elId, message, type = 'error') {
  const el = $(elId);
  if (!el) return;
  el.className = `form-message show ${type}`;
  el.innerHTML = `${type === 'error' ? '❌' : '✅'} ${message}`;
  if (type === 'success') setTimeout(() => { el.className = 'form-message'; }, 5000);
}
function hideFormMessage(elId) {
  if ($(elId)) $(elId).className = 'form-message';
}

// ─── INIT & ROUTING ───
window.onload = async () => {
  const token = localStorage.getItem('medibook_token');
  if (token) {
    state.token = token;
    await verifyToken();
  } else {
    showGateway();
  }
};

async function verifyToken() {
  const res = await API('/api/me');
  if (res.ok) {
    state.user = res.data;
    routeUser();
  } else {
    handleLogout();
  }
}

function routeUser() {
  $('gatewayView').style.display = 'none';
  $('patientView').style.display = 'none';
  $('doctorView').style.display = 'none';
  if ($('adminView')) $('adminView').style.display = 'none';

  if (state.isGuest) {
    $('patientView').style.display = 'block';
    $('headerGuestPatient').style.display = 'flex';
    $('headerUserPatient').style.display = 'none';
    $('navRecords').style.display = 'none';
    $('navPayments').style.display = 'none';
    $('navAftercare').style.display = 'none';
    $('navAppointments').style.display = 'none';
    $('navLookup').style.display = 'inline-flex';
    showPatientSection('booking');
    populateBookingClinics();
    return;
  }

  const role = state.user.role;
  if (role === 'patient') {
    $('patientView').style.display = 'block';
    $('headerGuestPatient').style.display = 'none';
    $('headerUserPatient').style.display = 'flex';
    $('headerUserNamePatient').textContent = state.user.fullname;
    $('navRecords').style.display = 'inline-flex';
    $('navPayments').style.display = 'inline-flex';
    $('navAftercare').style.display = 'inline-flex';
    $('navAppointments').style.display = 'inline-flex';
    $('navLookup').style.display = 'none';
    showPatientSection('booking');
    populateBookingClinics();
  }
  else if (role === 'doctor') {
    $('doctorView').style.display = 'block';
    $('headerUserNameDoctor').textContent = `BS. ${state.user.fullname}`;

    // Check if doctor data requires another endpoint call
    API('/api/doctor/me').then(dRes => {
      if (dRes.ok) {
        $('docNameDisplay').textContent = dRes.data.name;
        $('docSpecDisplay').textContent = `${dRes.data.specialty_name} | ${dRes.data.clinic_name}`;
      }
    });
    showDoctorTab('appointments');
  }
  else if (role === 'admin') {
    $('adminView').style.display = 'block';
    initAdminLogic();
    setTimeout(() => {
        initAdminCharts();
    }, 100);
  }
}

async function populateBookingClinics() {
  const res = await API('/api/clinics');
  if (res.ok) {
    state.clinicsData = res.data; // save for later filtering
    const selectEl = $('bookingClinicSelect');
    const serviceFilterEl = $('serviceClinicFilter');
    const html = `<option value="">-- Chọn phòng khám --</option>` + res.data.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    if (selectEl) {
      selectEl.innerHTML = html;
      handleStep2ClinicChange();
    }
    if (serviceFilterEl) serviceFilterEl.innerHTML = html;
  }
}

// ─── GATEWAY LOGIC ───
function showGateway() {
  $('gatewayView').style.display = 'flex';
  $('patientView').style.display = 'none';
  $('doctorView').style.display = 'none';
  if ($('adminView')) $('adminView').style.display = 'none';
  switchGatewayTab('patient');
}

function switchGatewayTab(tab) {
  ['Patient', 'Doctor', 'Admin'].forEach(t => {
    if ($(`gtwTab${t}`)) $(`gtwTab${t}`).classList.remove('active');
    if ($(`gtwForm${t}`)) $(`gtwForm${t}`).classList.remove('active');
  });
  const cap = tab.charAt(0).toUpperCase() + tab.slice(1);
  if ($(`gtwTab${cap}`)) $(`gtwTab${cap}`).classList.add('active');
  if ($(`gtwForm${cap}`)) $(`gtwForm${cap}`).classList.add('active');
  hideFormMessage('gatewayMessage');
}

async function handleGatewayLogin(role) {
  let email, password, url;
  if (role === 'patient') {
    email = $('gwPatientEmail').value;
    password = $('gwPatientPassword').value;
    url = '/api/login';
  } else if (role === 'doctor') {
    email = $('gwDoctorEmail').value;
    password = $('gwDoctorPassword').value;
    url = '/api/doctor/login';
  } else if (role === 'admin') {
    email = $('gwAdminEmail').value;
    password = $('gwAdminPassword').value;
    url = '/api/login';
  }

  if (!email || !password) return showFormMessage('gatewayMessage', 'Nhập đủ email và mật khẩu!');

  const btnId = `btnGw${role.charAt(0).toUpperCase() + role.slice(1)}Login`;
  $(btnId).disabled = true;

  const res = await API(url, { method: 'POST', body: JSON.stringify({ email, password, login_role: role }) });
  $(btnId).disabled = false;

  if (res.ok) {
    state.token = res.data.token;
    state.isGuest = false;
    localStorage.setItem('medibook_token', state.token);
    verifyToken();
  } else {
    showFormMessage('gatewayMessage', res.data.detail || 'Đăng nhập thất bại');
  }
}

function continueAsGuest() {
  state.isGuest = true;
  state.token = null;
  state.user = null;
  localStorage.removeItem('medibook_token');
  routeUser();
}

function backToGateway() {
  state.isGuest = false;
  showGateway();
}

function handleLogout() {
  if (state.token) API('/api/logout', { method: 'POST' });
  state.token = null;
  state.user = null;
  state.isGuest = false;
  localStorage.removeItem('medibook_token');
  showGateway();
}

// ─── REGISTRATION MODAL ───
function openAuthModal(type) {
  $('regModal').classList.add('active');
  hideFormMessage('regMessage');
  $('regName').value = ''; $('regUsername').value = ''; $('regEmail').value = ''; $('regPhone').value = '';
  $('regCCCD').value = ''; $('regPassword').value = '';

  if (type === 'register_doctor') {
    $('regModalTitle').textContent = 'Đăng Ký Bác Sĩ';
    $('regDoctorFields').style.display = 'block';
    loadClinicsForReg();
  } else {
    $('regModalTitle').textContent = 'Đăng Ký Bệnh Nhân';
    $('regDoctorFields').style.display = 'none';
  }
  $('btnSubmitReg').onclick = () => handleRegistration(type);
}
function closeRegModal() { $('regModal').classList.remove('active'); }

// ─── FORGOT PASSWORD LOGIC ───
let forgotPasswordRole = 'patient';

function openForgotModal(role) {
  forgotPasswordRole = role;
  $('forgotPasswordModal').classList.add('active');
  hideFormMessage('forgotMessage');
  $('forgotStep1').style.display = 'block';
  $('forgotStep2').style.display = 'none';
  $('forgotEmail').value = '';
  $('forgotOtp').value = '';
  $('forgotNewPassword').value = '';
}

function closeForgotModal() {
  $('forgotPasswordModal').classList.remove('active');
}

async function handleRequestOtp() {
  const email = $('forgotEmail').value.trim();
  if (!email) return showFormMessage('forgotMessage', 'Vui lòng nhập email!');
  
  $('btnRequestOtp').disabled = true;
  $('btnRequestOtp').textContent = 'Đang gửi...';
  
  const res = await API('/api/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email, role: forgotPasswordRole })
  });
  
  $('btnRequestOtp').disabled = false;
  $('btnRequestOtp').textContent = 'Gửi mã xác nhận';
  
  if (res.ok) {
    showFormMessage('forgotMessage', res.data.message || 'Mã OTP đã được gửi!', 'success');
    $('forgotStep1').style.display = 'none';
    $('forgotStep2').style.display = 'block';
  } else {
    showFormMessage('forgotMessage', res.data.detail || 'Lỗi gửi yêu cầu!');
  }
}

async function handleResetPassword() {
  const email = $('forgotEmail').value.trim();
  const otp = $('forgotOtp').value.trim();
  const new_password = $('forgotNewPassword').value.trim();
  
  if (!otp || !new_password) return showFormMessage('forgotMessage', 'Vui lòng nhập OTP và mật khẩu mới!');
  
  $('btnResetPassword').disabled = true;
  $('btnResetPassword').textContent = 'Đang xử lý...';
  
  const res = await API('/api/reset-password', {
    method: 'POST',
    body: JSON.stringify({ email, otp, new_password, role: forgotPasswordRole })
  });
  
  $('btnResetPassword').disabled = false;
  $('btnResetPassword').textContent = 'Lưu mật khẩu mới';
  
  if (res.ok) {
    showFormMessage('forgotMessage', res.data.message || 'Đổi mật khẩu thành công!', 'success');
    setTimeout(() => {
      closeForgotModal();
    }, 2000);
  } else {
    showFormMessage('forgotMessage', res.data.detail || 'Lỗi khôi phục mật khẩu!');
  }
}

async function loadClinicsForReg() {
  const res = await API('/api/clinics');
  if (res.ok) {
    $('regClinic').innerHTML = res.data.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
  }
}

async function handleRegistration(type) {
  const isDoc = (type === 'register_doctor');
  const body = {
    fullname: $('regName').value, username: $('regUsername').value, email: $('regEmail').value,
    phone: $('regPhone').value, cccd: $('regCCCD').value, password: $('regPassword').value
  };

  if (!body.fullname || !body.email || !body.password) {
    return showFormMessage('regMessage', 'Điền đủ các trường bắt buộc!');
  }

  let url = '/api/register';
  if (isDoc) {
    url = '/api/doctor/register';
    Object.assign(body, {
      specialty: $('regSpecialty').value, experience_years: parseInt($('regExp').value) || 0,
      license_number: $('regLicense').value, certificate_info: $('regCert').value,
      clinic_id: parseInt($('regClinic').value)
    });
  }

  $('btnSubmitReg').disabled = true;
  const res = await API(url, { method: 'POST', body: JSON.stringify(body) });
  $('btnSubmitReg').disabled = false;

  if (res.ok) {
    showFormMessage('regMessage', isDoc ? 'Đăng ký bác sĩ thành công! Đang tự động đăng nhập...' : 'Đăng ký thành công! Đang tự động đăng nhập...', 'success');
    
    // Auto login
    const loginRes = await API(isDoc ? '/api/doctor/login' : '/api/login', {
      method: 'POST',
      body: JSON.stringify({ email: body.email, password: body.password })
    });
    
    if (loginRes.ok) {
      state.token = loginRes.data.token;
      state.user = loginRes.data.user;
      localStorage.setItem('medibook_token', state.token);
      setTimeout(() => {
        closeRegModal();
        routeUser();
      }, 1000);
    } else {
      setTimeout(() => {
        closeRegModal();
        switchGatewayTab(isDoc ? 'doctor' : 'patient');
      }, 1500);
    }
  } else {
    showFormMessage('regMessage', res.data.detail || 'Lỗi đăng ký!');
  }
}

// ─── PATIENT BOOKING LOGIC ───
function showPatientSection(section) {
  ['sectionBooking', 'sectionServices', 'sectionRecords', 'sectionPayments', 'sectionAftercare', 'sectionAppointments'].forEach(id => {
    if ($(id)) $(id).style.display = 'none';
  });
  const navLinks = document.querySelectorAll('#headerNavPatient .nav-link');
  navLinks.forEach(el => el.classList.remove('active'));

  if (section === 'booking') {
    $('sectionBooking').style.display = 'block';
    if ($('navBooking')) $('navBooking').classList.add('active');
  } else if (section === 'appointments') {
    $('sectionAppointments').style.display = 'block';
    if ($('navAppointments')) $('navAppointments').classList.add('active');
    loadMyAppointments();
  } else if (section === 'services') {
    $('sectionServices').style.display = 'block';
    if ($('navServices')) $('navServices').classList.add('active');
    loadServicesPage();
  } else if (section === 'records') {
    $('sectionRecords').style.display = 'block';
    if ($('navRecords')) $('navRecords').classList.add('active');
    loadPatientRecords();
  } else if (section === 'payments') {
    $('sectionPayments').style.display = 'block';
    if ($('navPayments')) $('navPayments').classList.add('active');
    loadPatientPayments();
  } else if (section === 'aftercare') {
    $('sectionAftercare').style.display = 'block';
    if ($('navAftercare')) $('navAftercare').classList.add('active');
    loadPatientAftercare();
  }
}

function updateSteps(step) {
  state.currentStep = step;
  [1, 2, 3, 4, 5].forEach(i => {
    const dot = $(`dot${i}`);
    if (!dot) return;
    dot.classList.remove('active', 'done');
    if (i < step) { dot.classList.add('done'); dot.textContent = '✓'; }
    else if (i === step) { dot.classList.add('active'); dot.textContent = i; }
    else { dot.textContent = i; }
    if (i < 5 && $(`line${i}`)) $(`line${i}`).classList.toggle('done', i < step);
  });
}

function handleBookingForChange() {
  const bf = document.querySelector('input[name="bookingFor"]:checked').value;
  state.bookingFor = bf;
  
  ['patientName', 'patientEmail', 'patientPhone', 'patientCCCD', 'patientDOB', 'patientGender', 'symptomsInput'].forEach(id => {
    const el = $(id);
    if (el) {
      el.value = '';
      el.classList.remove('input-success', 'input-error');
    }
  });
  if ($('patientAttachmentUrl')) $('patientAttachmentUrl').value = '';
  if ($('uploadStatus')) $('uploadStatus').textContent = '';

  if (!state.isGuest && state.user && state.bookingFor === 'self') {
    if ($('patientFormContainer')) $('patientFormContainer').style.display = 'none';
  } else {
    if ($('patientFormContainer')) $('patientFormContainer').style.display = 'block';
  }
  checkStep1Validation();
}

function validateStep1() {
  // Tạm thời comment logic để test
  return true;
  /*
  const isSelf = (!state.bookingFor || state.bookingFor === 'self');
  const isFormVisible = state.isGuest || !isSelf || !state.user;
  if (isFormVisible) {
    let pName = $('patientName') ? $('patientName').value.trim() : '';
    let pEmail = $('patientEmail') ? $('patientEmail').value.trim() : '';
    let pPhone = $('patientPhone') ? $('patientPhone').value.trim() : '';
    
    let hasError = false;
    if (!pName) { if($('patientName')) $('patientName').classList.add('input-error'); hasError = true; }
    if (!pEmail) { if($('patientEmail')) $('patientEmail').classList.add('input-error'); hasError = true; }
    if (!pPhone) { if($('patientPhone')) $('patientPhone').classList.add('input-error'); hasError = true; }
    
    if (hasError) {
      alert("Vui lòng điền đầy đủ thông tin bệnh nhân (Họ tên, Email, SĐT)!");
      return false;
    }
  }
  return true;
  */
}

function checkStep1Validation() {
  const btn = $('btnNextStep1');
  if (!btn) return;
  
  // Tạm thời comment logic để test
  btn.disabled = false;
  if ($('step1Warning')) $('step1Warning').style.display = 'none';
  return;
  /*
  const isSelf = (!state.bookingFor || state.bookingFor === 'self');
  const isFormVisible = state.isGuest || !isSelf || !state.user;
  
  let isValid = true;
  if (isFormVisible) {
    let pName = $('patientName') ? $('patientName').value.trim() : '';
    let pEmail = $('patientEmail') ? $('patientEmail').value.trim() : '';
    let pPhone = $('patientPhone') ? $('patientPhone').value.trim() : '';
    
    if (!pName || !pEmail || !pPhone) {
      isValid = false;
    }
  }
  
  if (isValid) {
    btn.disabled = false;
    if ($('step1Warning')) $('step1Warning').style.display = 'none';
  } else {
    btn.disabled = true;
    if ($('step1Warning')) $('step1Warning').style.display = 'block';
  }
  */
}

function goStep(n) {
  // Navigation direction
  const currentStep = 1; // we don't have a robust way to know current step without state, but we can infer from DOM or just always validate
  // We can just validate previous steps if n is greater than them.
  if (n === 2) {
    if (!validateStep1()) return;
  }
  if (n === 3) {
    // If going to step 3 from step 2, validate step 2
    if (!state.doctor || !state.doctor.id) {
      alert("Vui lòng chọn bác sĩ trước khi tiếp tục!");
      return;
    }
  }
  if (n === 4) {
    // If going to step 4 from step 3, validate step 3
    if (!state.time) {
      alert("Vui lòng chọn giờ khám trước khi tiếp tục!");
      return;
    }
  }
  if (n === 1) {
    if (!state.bookingFor) state.bookingFor = 'self';
    handleBookingForChange();

    if (state.isGuest) {
      if ($('guestBookingNotice')) $('guestBookingNotice').style.display = 'block';
      ['fgPatientName', 'fgPatientEmail', 'fgPatientPhone'].forEach(id => {
        if ($(id)) $(id).classList.add('guest-required-field');
      });
    } else {
      if ($('guestBookingNotice')) $('guestBookingNotice').style.display = 'none';
    }

    // Pre-fill dữ liệu user nếu có
    if (!state.isGuest && state.user && state.bookingFor === 'self') {
      if ($('patientName')) $('patientName').value = state.user.fullname || '';
      if ($('patientEmail')) $('patientEmail').value = state.user.email || '';
      if ($('patientPhone')) $('patientPhone').value = state.user.phone || '';
      if ($('patientCCCD')) $('patientCCCD').value = state.user.cccd || '';
    }
    checkStep1Validation();
  }

  $('step1').style.display = n === 1 ? 'block' : 'none';
  $('step2').style.display = n === 2 ? 'block' : 'none';
  $('step3').style.display = n === 3 ? 'block' : 'none';
  $('step4').style.display = n === 4 ? 'block' : 'none';
  $('stepSuccess').style.display = n === 5 ? 'block' : 'none';

  updateSteps(n);

  if (n === 4) {
    renderSummary();
    if ($('bookingAlert')) $('bookingAlert').innerHTML = '';
  }
}

function clearFieldError(el) {
  el.classList.remove('input-error');
  if (el.value.trim()) el.classList.add('input-success');
  else el.classList.remove('input-success');
  checkStep1Validation();
}

async function handleStep2ClinicChange() {
  const clinicId = $('bookingClinicSelect').value;
  const specGroup = $('step2SpecialtyGroup');
  const specSelect = $('bookingSpecialtySelect');
  $('doctorSelectionSection').style.display = 'none';

  if (!clinicId) {
    specGroup.style.display = 'none';
    specSelect.innerHTML = '<option value="">-- Chọn chuyên khoa --</option>';
    return;
  }

  // Find clinic data to get specialty_ids
  const clinic = state.clinicsData?.find(c => c.id == clinicId);
  if (!clinic || !clinic.specialty_ids) {
    specGroup.style.display = 'none';
    return;
  }

  // Load all specialties mapping from server
  if (!state.specialtiesMap) {
    const res = await API('/api/specialties');
    if (res.ok) {
      state.specialtiesMap = res.data;
    }
  }

  const allowedIds = clinic.specialty_ids.split(',').map(s => parseInt(s.trim()));
  const allowedSpecs = state.specialtiesMap.filter(s => allowedIds.includes(s.id));

  specSelect.innerHTML = '<option value="">-- Chọn chuyên khoa --</option>' + 
    allowedSpecs.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
  
  specGroup.style.display = 'block';
}

function handleStep2SpecialtyChange() {
  const clinicId = $('bookingClinicSelect').value;
  const specId = $('bookingSpecialtySelect').value;
  
  if (!clinicId || !specId) {
    $('doctorSelectionSection').style.display = 'none';
    return;
  }
  
  $('doctorSelectionSection').style.display = 'block';
  loadDoctorsHorizontal(clinicId, specId);
}

async function loadDoctorsHorizontal(clinicId, specId) {
  $('doctorResult').innerHTML = 'Đang tải...';
  const url = `/api/doctors?clinic_id=${clinicId}&specialty_id=${specId}`;

  const res = await API(url);
  if (res.ok) {
    if (!res.data.length) return $('doctorResult').innerHTML = 'Không tìm thấy Bác sĩ cho khoa này.';
    
    // RENDER HORIZONTAL SQUARES
    const html = res.data.map(d => {
      const avatarIcon = d.gender === 'Nữ' ? '👩‍⚕️' : '👨‍⚕️';
      return `
      <div class="doctor-square-card" id="docCard_${d.id}" onclick="selectDoctorHorizontal(${d.id},'${d.name}','${d.specialty_name}', ${d.clinic_id}, ${d.consultation_fee || 200000})">
        <div class="avatar">${avatarIcon}</div>
        <div class="doctor-name">${d.name}</div>
        <div class="doctor-spec">${d.specialty_name}</div>
        <div class="stars">⭐ ${d.rating}</div>
        <div style="font-size:10px; color:#94a3b8; margin-top:4px;">${d.experience_years} năm KN</div>
      </div>
      `;
    }).join('');
    
    $('doctorResult').innerHTML = `<div class="doctor-horizontal-list">${html}</div>`;
  }
}

function selectDoctorHorizontal(id, name, spec, clinic_id, fee) {
  state.doctor = { id, name, spec, fee };
  const clinicName = $('bookingClinicSelect').options[$('bookingClinicSelect').selectedIndex].text;
  state.clinic = { id: clinic_id, name: clinicName };

  document.querySelectorAll('.doctor-square-card').forEach(el => el.classList.remove('selected'));
  const card = $(`docCard_${id}`);
  if (card) card.classList.add('selected');

  if ($('step2Btns')) $('step2Btns').style.display = 'flex';

  const today = new Date().toISOString().split('T')[0];
  if ($('appointmentDate')) {
    $('appointmentDate').min = today;
    $('appointmentDate').value = today;
  }
  state.date = today;
  loadSlots();

  setTimeout(() => {
    goStep(3);
  }, 300); // slight delay for visual effect
}

function selectDoctor(id, name, spec, clinic_id, fee) {
  state.doctor = { id, name, spec, fee };
  state.clinic = { id: clinic_id, name: "Phòng khám" };

  // Highlight card
  document.querySelectorAll('.doctor-item').forEach(el => el.style.border = '1px solid #e2e8f0');
  const card = $(`docCard_${id}`);
  if (card) card.style.border = '2px solid var(--primary)';

  if ($('step2Btns')) $('step2Btns').style.display = 'flex';

  const today = new Date().toISOString().split('T')[0];
  if ($('appointmentDate')) {
    $('appointmentDate').min = today;
    $('appointmentDate').value = today;
  }
  state.date = today;
  loadSlots();

  // Tự động chuyển sang bước 3
  goStep(3);
}

async function loadSlots() {
  state.date = $('appointmentDate').value;
  if (!state.doctor || !state.date) return;
  $('slotGrid').innerHTML = 'Đang tải...';
  const res = await API(`/api/slots?doctor_id=${state.doctor.id}&date=${state.date}`);
  if (res.ok) {
    const { all_slots, booked } = res.data;
    $('slotGrid').innerHTML = all_slots.map(s => {
      const isBooked = booked.includes(s);
      return `<div class="slot ${isBooked ? 'booked' : ''}" onclick="${isBooked ? '' : `pickSlot('${s}',this)`}">${s}</div>`;
    }).join('');
    state.time = '';
  }
}

function pickSlot(t, el) {
  state.time = t;
  document.querySelectorAll('.slot').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
  if ($('step3Btns')) $('step3Btns').style.display = 'flex';
}

function renderSummary() {
  const isSelf = (!state.bookingFor || state.bookingFor === 'self');
  const bfText = state.bookingFor === 'family' ? 'Cho Gia đình' : (state.bookingFor === 'other' ? 'Cho Người khác' : 'Cho Bản thân');

  let pName = isSelf && !state.isGuest && state.user ? state.user.fullname : $('patientName').value;
  let pEmail = isSelf && !state.isGuest && state.user ? state.user.email : $('patientEmail').value;
  let pPhone = isSelf && !state.isGuest && state.user ? state.user.phone : $('patientPhone').value;

  $('bookingSummary').innerHTML = `
  <div class="alert alert-info">
    <div style="margin-bottom:8px;">🎯 Hình thức: <b>Đặt lịch ${bfText}</b></div>
    <div style="margin-bottom:8px;">👨‍⚕️ Bác sĩ: <b>${state.doctor.name}</b> (${state.doctor.spec})</div>
    <div style="margin-bottom:8px;">📅 Thời gian: <b>${state.time}</b> ngày <b>${state.date}</b></div>
    <hr style="margin:12px 0; border:none; border-top:1px dashed #cbd5e1;"/>
    <div style="margin-bottom:8px;">👤 Bệnh nhân: <b>${pName || '<i>Chưa nhập</i>'}</b></div>
    <div style="margin-bottom:8px;">📱 SĐT: <b>${pPhone || '<i>Chưa nhập</i>'}</b></div>
  </div>`;
}

async function uploadAttachment(input) {
  const file = input.files[0];
  if (!file) return;

  $('uploadStatus').textContent = 'Đang tải lên...';
  const formData = new FormData();
  formData.append('file', file);

  const token = localStorage.getItem('medibook_token') || '';
  const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      headers,
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      $('patientAttachmentUrl').value = data.url;
      $('uploadStatus').textContent = '✅ Đã tải lên file.';
    } else {
      $('uploadStatus').textContent = '❌ Lỗi tải lên.';
    }
  } catch (e) {
    $('uploadStatus').textContent = '❌ Lỗi tải lên.';
  }
}

async function submitBooking() {
  if (!state.time) return alert("Vui lòng chọn thời gian khám.");

  const paymentMethod = 'at_hospital';

  const isSelf = (!state.bookingFor || state.bookingFor === 'self');
  let pName = isSelf && !state.isGuest && state.user ? state.user.fullname : $('patientName').value;
  let pEmail = isSelf && !state.isGuest && state.user ? state.user.email : $('patientEmail').value;
  let pPhone = isSelf && !state.isGuest && state.user ? state.user.phone : $('patientPhone').value;
  let pCCCD = isSelf && !state.isGuest && state.user ? state.user.cccd : $('patientCCCD').value;

  if (!pName || !pEmail || !pPhone) {
    $('bookingAlert').innerHTML = '<div class="booking-validation-alert">⚠️ Thiếu thông tin bệnh nhân. Vui lòng tải lại trang và nhập đủ thông tin!</div>';
    return;
  }

  const payload = {
    patient_name: pName,
    patient_email: pEmail,
    patient_phone: pPhone,
    patient_cccd: pCCCD,
    doctor_id: state.doctor.id,
    clinic_id: state.clinic.id,
    date: state.date,
    time: state.time,
    symptoms: $('symptomsInput').value,
    attachment: $('patientAttachmentUrl').value,
    booking_for: state.bookingFor || 'self',
    patient_dob: $('patientDOB') ? $('patientDOB').value : '',
    patient_gender: $('patientGender') ? $('patientGender').value : '',
    patient_address: $('patientAddress') ? $('patientAddress').value : '',
    payment_method: paymentMethod
  };

  const btn = $('btnSubmitBooking');
  if (btn) btn.disabled = true;
  $('bookingAlert').innerHTML = '<div class="booking-validation-alert" style="background:#e0f2fe; color:#0284c7;">Đang xử lý...</div>';

  let res;
  if (state.editAppId) {
    if (state.editAppCode) {
      res = await API(`/api/appointments/lookup/${state.editAppCode}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      res = await API(`/api/me/appointments/${state.editAppId}`, { method: 'PUT', body: JSON.stringify(payload) });
    }
  } else {
    res = await API('/api/book', { method: 'POST', body: JSON.stringify(payload) });
  }
  
  if (btn) btn.disabled = false;

  if (res.ok) {
    goStep(5);
    $('successBookingCode').textContent = res.data.booking_code;
    $('successText').innerHTML = `
      Cảm ơn <b>${payload.patient_name}</b>.<br/>
      ${state.editAppId ? 'Lịch hẹn của bạn đã được cập nhật.' : 'Đã đặt lịch khám thành công.'}<br/>
      Thời gian: <b>${state.time}</b> ngày <b>${state.date}</b><br/>
      Bác sĩ: <b>${state.doctor.name}</b>
    `;
    if (!state.isGuest) {
      $('btnManageAppointments').style.display = 'inline-block';
    }
    state.editAppId = null;
    state.editAppCode = null;
    if (btn) btn.innerHTML = 'Xác Nhận Đặt Lịch 🚀';
  } else {
    $('paymentAlert').innerHTML = `<div class="booking-validation-alert">❌ Lỗi: ${res.data.detail?.message || res.data.detail}</div>`;
  }
}

function resetAll() {
  state.specialty = null; state.clinic = null; state.doctor = null; state.date = ''; state.time = '';
  $('symptomsInput').value = ''; $('patientAttachmentUrl').value = ''; $('uploadStatus').textContent = '';
  const selfRadio = document.querySelector('input[name="bookingFor"][value="self"]');
  if (selfRadio) selfRadio.checked = true;
  $('slotSection').style.display = 'block';
  goStep(1);
}

// ─── PATIENT PROFILE & OTHERS ───
function openProfileModal() {
  $('profileModal').classList.add('active');
  $('profileName').value = state.user.fullname || '';
  $('profileEmail').value = state.user.email || '';
  $('profilePhone').value = state.user.phone || '';
  $('profileCCCD').value = state.user.cccd || '';
  loadPatientHistory();
}
function closeProfileModal() { $('profileModal').classList.remove('active'); }

async function handleUpdateProfile() {
  const body = {
    fullname: $('profileName').value, email: $('profileEmail').value,
    phone: $('profilePhone').value, cccd: $('profileCCCD').value
  };
  const res = await API('/api/me/update', { method: 'PUT', body: JSON.stringify(body) });
  if (res.ok) {
    showFormMessage('profileMessage', 'Cập nhật thành công', 'success');
    state.user = { ...state.user, ...res.data.user };
  }
}

async function loadPatientHistory() {
  const res = await API('/api/me/appointments');
  if (res.ok) {
    $('appointmentHistory').innerHTML = res.data.map(a => `
      <div style="border:1px solid #ccc; padding:10px; margin-bottom:10px; border-radius:8px">
        <b>${a.date} ${a.time}</b> - BS. ${a.doctor_name}<br/>
        <button class="btn btn-sm btn-outline" onclick="openMessageModal(${a.doctor_id},${a.id},'${a.doctor_name}')">💬 Chat</button>
      </div>`).join('');
  }
}

async function loadServicesPage() {
  const res = await API('/api/services');
  if (res.ok) {
    $('servicesList').innerHTML = res.data.map(s => `<div class="service-item">
      <div><b>${s.name}</b><br/><small>${s.description}</small></div>
      <div style="color:var(--accent); font-weight:bold">${s.price}đ</div>
    </div>`).join('');
  }
}

async function loadPatientRecords() {
  const res = await API('/api/me/medical-records');
  if (res.ok) {
    $('recordsList').innerHTML = res.data.map(r => `<div class="record-item">
      <div class="record-item-header">📅 ${r.created_at.split('T')[0]} - BS. ${r.doctor_name}</div>
      <div class="record-item-body"><b>Chẩn đoán:</b> ${r.diagnosis}<br/><b>Đơn thuốc:</b> ${r.prescription}</div>
    </div>`).join('');
  }
}

async function loadPatientPayments() {
  const [appsRes, payRes] = await Promise.all([API('/api/me/appointments'), API('/api/me/payments')]);
  if (appsRes.ok && payRes.ok) {
    const paidIds = payRes.data.map(p => p.appointment_id);
    const unpaid = appsRes.data.filter(a => !paidIds.includes(a.id) && a.status === 'confirmed');

    $('unpaidList').innerHTML = unpaid.map(a => `<div style="border:1px solid #ccc; padding:10px; margin-bottom:10px; border-radius:8px">
      📅 ${a.date} - BS. ${a.doctor_name}
      <button class="btn btn-sm btn-success" onclick="openPaymentModal(${a.id})">Thanh toán</button>
    </div>`).join('');

    $('paymentHistory').innerHTML = payRes.data.map(p => `<div class="payment-item">
      <div><b>${p.amount}đ</b> - ${p.method}</div><div>${p.paid_at.split('T')[0]} - ✅</div>
    </div>`).join('');
  }
}

async function loadPatientAftercare() {
  const res = await API('/api/me/aftercare');
  if (res.ok) {
    $('aftercareList').innerHTML = res.data.map(a => `<div class="aftercare-item">
      <b>BS. ${a.doctor_name}</b><br/>${a.instructions}<br/>
      <small style="color:var(--warn)">Tái khám: ${a.follow_up_date || 'Không'}</small>
    </div>`).join('');
  }
}

function openPaymentModal(appId) {
  state.paymentAppointmentId = appId;
  $('paymentModal').classList.add('active');
  state.paymentMethod = 'cash';
}
function closePaymentModal() { $('paymentModal').classList.remove('active'); }

function selectPaymentMethod(m, el) {
  state.paymentMethod = m;
  document.querySelectorAll('.payment-method').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
}
async function loadMyAppointments() {
  const res = await API('/api/me/appointments');
  if (res.ok) {
    const list = res.data.length ? res.data.map(a => `
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
          <div>
            <div style="font-weight:600; font-size:16px; color:#1e293b;">Bác sĩ ${a.doctor_name}</div>
            <div style="color:#64748b; font-size:14px; margin-top:4px;">
              Mã LH: <b>${a.booking_code || 'N/A'}</b><br/>
              📅 ${a.date} &nbsp; ⏰ ${a.time}<br/>
              👤 Bệnh nhân: ${a.patient_name} <br/>
              Trạng thái: <span class="badge ${a.status === 'confirmed' ? 'badge-blue' : (a.status === 'completed' ? 'badge-success' : (a.status === 'cancelled' ? 'badge-danger' : 'badge-gray'))}">${a.status}</span>
            </div>
          </div>
          <div style="text-align:right;">
            ${a.status === 'confirmed' ? `
              <button class="btn btn-sm btn-outline" style="margin-bottom:8px; display:block; width:100%;" onclick="startEditAppointmentFromUser(${a.id})">Sửa thông tin</button>
              <button class="btn btn-sm btn-outline" style="margin-bottom:8px; display:block; width:100%;" onclick="openRescheduleModal(${a.id}, ${a.doctor_id})">Đổi Lịch</button>
              <button class="btn btn-sm btn-danger" style="display:block; width:100%;" onclick="cancelAppt(${a.id})">Hủy</button>
            ` : ''}
          </div>
        </div>
      </div>
    `).join('') : '<p>Chưa có lịch hẹn nào.</p>';
    $('appointmentsList').innerHTML = list;
  }
}

// Reschedule Logic
function openRescheduleModal(appId, docId) {
  state.rescheduleAppId = appId;
  state.rescheduleDocId = docId;
  $('rescheduleModal').classList.add('active');
  $('rescheduleDate').min = new Date().toISOString().split('T')[0];
  $('rescheduleDate').value = '';
  $('rescheduleSlotGrid').innerHTML = '';
  $('rescheduleAlert').innerHTML = '';
}

function closeRescheduleModal() {
  $('rescheduleModal').classList.remove('active');
  state.rescheduleAppId = null;
  state.rescheduleDocId = null;
}

async function loadRescheduleSlots() {
  const date = $('rescheduleDate').value;
  if (!date || !state.rescheduleDocId) return;
  $('rescheduleSlotGrid').innerHTML = 'Đang tải...';
  const res = await API(`/api/slots?doctor_id=${state.rescheduleDocId}&date=${date}`);
  if (res.ok) {
    const { all_slots, booked } = res.data;
    $('rescheduleSlotGrid').innerHTML = all_slots.map(s => {
      const isBooked = booked.includes(s);
      return `<div class="slot ${isBooked ? 'booked' : ''}" onclick="${isBooked ? '' : `pickRescheduleSlot('${s}',this)`}">${s}</div>`;
    }).join('');
    state.rescheduleTime = '';
  }
}

function pickRescheduleSlot(t, el) {
  state.rescheduleTime = t;
  document.querySelectorAll('#rescheduleSlotGrid .slot').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
}

async function confirmReschedule() {
  const date = $('rescheduleDate').value;
  const time = state.rescheduleTime;
  if (!date || !time) {
    $('rescheduleAlert').innerHTML = '<div class="booking-validation-alert">Vui lòng chọn ngày và giờ mới!</div>';
    return;
  }
  const res = await API(`/api/me/appointments/${state.rescheduleAppId}/reschedule`, {
    method: 'POST',
    body: JSON.stringify({ date, time })
  });
  if (res.ok) {
    alert("Đổi lịch thành công!");
    closeRescheduleModal();
    loadMyAppointments();
  } else {
    $('rescheduleAlert').innerHTML = `<div class="booking-validation-alert">❌ ${res.data.detail}</div>`;
  }
}
async function handlePayment() {
  const amt = $('paymentAmount').value;
  const res = await API('/api/me/payment', {
    method: 'POST', body: JSON.stringify({
      appointment_id: state.paymentAppointmentId, amount: parseFloat(amt), method: state.paymentMethod
    })
  });
  if (res.ok) {
    alert('Thanh toán thành công!');
    closePaymentModal();
    loadPatientPayments();
  }
}

// ─── DOCTOR LOGIC ───
function showDoctorTab(tab) {
  document.querySelectorAll('#doctorView .sidebar-link').forEach(el => el.classList.remove('active'));
  document.querySelector(`[onclick="showDoctorTab('${tab}')"]`).classList.add('active');
  $('tabDoctorAppointments').style.display = tab === 'appointments' ? 'block' : 'none';
  $('tabDoctorMessages').style.display = tab === 'messages' ? 'block' : 'none';
  if (tab === 'appointments') loadDoctorAppointments();
}

async function loadDoctorAppointments() {
  const res = await API('/api/doctor/appointments');
  if (res.ok) {
    $('doctorAppointmentsList').innerHTML = `<table class="data-table">
      <thead><tr><th>ID</th><th>Ngày giờ</th><th>Bệnh nhân</th><th>Thao tác</th></tr></thead>
      <tbody>${res.data.map(a => `<tr>
        <td>#${a.id}</td><td>${a.date} ${a.time}</td><td>${a.patient_name}</td>
        <td>
          <button class="btn btn-sm btn-outline" onclick="openRecordModal(${a.id},${a.user_id})">📝 Lập HS</button>
          <button class="btn btn-sm btn-outline" onclick="openMessageModal(null,${a.id},'${a.patient_name}',${a.user_id})">💬 Chat</button>
        </td>
      </tr>`).join('')}</tbody></table>`;
  }
}

function openRecordModal(appId, userId) {
  state.currentRecordAppId = appId; state.currentRecordPatientId = userId;
  $('recordModal').classList.add('active');
}
function closeRecordModal() { $('recordModal').classList.remove('active'); }

async function saveMedicalRecord() {
  const body = {
    patient_id: state.currentRecordPatientId, appointment_id: state.currentRecordAppId,
    diagnosis: $('recordDiagnosis').value, prescription: $('recordPrescription').value, notes: $('recordNotes').value
  };
  const res1 = await API('/api/doctor/medical-record', { method: 'POST', body: JSON.stringify(body) });
  if (res1.ok && $('recordAftercare').value) {
    await API('/api/doctor/aftercare', {
      method: 'POST', body: JSON.stringify({
        appointment_id: state.currentRecordAppId, patient_id: state.currentRecordPatientId,
        instructions: $('recordAftercare').value, follow_up_date: $('recordFollowUp').value
      })
    });
  }
  if (res1.ok) { alert('Đã lưu hồ sơ!'); closeRecordModal(); }
}



// ─── INTEGRATED MAP LOGIC (Redesigned) ───

function openMapModal() {
  $('mapModal').classList.add('active');
  if (!state.map) {
    initLeafletMap();
  } else {
    setTimeout(() => { state.map.invalidateSize(); }, 200);
  }
  // Show instruction
  const instr = $('mapInstruction');
  if (instr) instr.style.display = 'flex';
  // Try GPS auto-detect
  locateUserOnMap();
}

function closeMapModal() {
  $('mapModal').classList.remove('active');
}

function initLeafletMap() {
  state.map = L.map('leafletMap', {
    zoomControl: true,
    attributionControl: true
  }).setView([16.0, 106.5], 6); // Vietnam center

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(state.map);

  // ── Click on map to set position ──
  state.map.on('click', function (e) {
    const { lat, lng } = e.latlng;
    setUserPosition(lat, lng, 'manual');
  });
}

// Set user position (from GPS or manual click)
function setUserPosition(lat, lng, source) {
  state.userLat = lat;
  state.userLng = lng;

  state.map.setView([lat, lng], 16);

  // Remove old markers
  if (state.userMarker) state.map.removeLayer(state.userMarker);
  if (state.userCircle) state.map.removeLayer(state.userCircle);

  const isGPS = source === 'gps';

  const iconUser = L.divIcon({
    className: '',
    html: `<div style="
      background:${isGPS ? '#10b981' : '#f59e0b'};
      border-radius:50%;
      width:20px; height:20px;
      border:3px solid #fff;
      box-shadow:0 2px 12px ${isGPS ? 'rgba(16,185,129,.5)' : 'rgba(245,158,11,.5)'};
      ${isGPS ? 'animation: pulse-marker 2s infinite;' : ''}
    "></div>
    <style>
      @keyframes pulse-marker {
        0%,100% { box-shadow:0 2px 12px rgba(16,185,129,.5); }
        50% { box-shadow:0 2px 20px rgba(16,185,129,.8), 0 0 0 10px rgba(16,185,129,.1); }
      }
    </style>`,
    iconSize: [20, 20], iconAnchor: [10, 10]
  });

  state.userMarker = L.marker([lat, lng], { icon: iconUser, zIndexOffset: 1000 })
    .addTo(state.map)
    .bindPopup(`<b>${isGPS ? '📍 Vị trí của bạn' : '📌 Vị trí đã chọn'}</b>`)
    .openPopup();

  state.userCircle = L.circle([lat, lng], {
    radius: isGPS ? 500 : 1000,
    color: isGPS ? '#10b981' : '#f59e0b',
    fillColor: isGPS ? '#d1fae5' : '#fef3c7',
    fillOpacity: 0.15,
    weight: 1.5,
    dashArray: isGPS ? null : '6 4'
  }).addTo(state.map);

  // Update location bar
  updateLocationBar(lat, lng, source);

  // Hide instruction
  const instr = $('mapInstruction');
  if (instr) instr.style.display = 'none';

  // Load & sort clinics
  loadClinicsForMap(lat, lng);
}

function updateLocationBar(lat, lng, source) {
  const bar = $('mapLocationBar');
  const text = $('mapLocationText');
  if (!bar || !text) return;

  bar.className = 'map-location-bar';

  if (source === 'gps') {
    bar.classList.add('located');
    text.textContent = `📍 Vị trí của bạn: ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    // Try reverse geocoding
    reverseGeocode(lat, lng);
  } else {
    bar.classList.add('manual');
    text.textContent = `📌 Vị trí đã chọn: ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    reverseGeocode(lat, lng);
  }
}

async function reverseGeocode(lat, lng) {
  try {
    const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&accept-language=vi`);
    const data = await res.json();
    if (data.display_name) {
      const text = $('mapLocationText');
      const bar = $('mapLocationBar');
      const isGPS = bar.classList.contains('located');
      const shortName = data.display_name.split(',').slice(0, 3).join(', ');
      text.textContent = `${isGPS ? '📍' : '📌'} ${shortName}`;
    }
  } catch (e) { /* silently ignore */ }
}

function locateUserOnMap() {
  const bar = $('mapLocationBar');
  const text = $('mapLocationText');
  if (bar) bar.className = 'map-location-bar';
  if (text) text.textContent = 'Đang xác định vị trí...';

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      pos => {
        setUserPosition(pos.coords.latitude, pos.coords.longitude, 'gps');
      },
      () => {
        fetchIPLocation();
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  } else {
    fetchIPLocation();
  }
}

function fetchIPLocation() {
  fetch('https://ipinfo.io/json')
    .then(res => res.json())
    .then(data => {
      if (data.loc) {
        const coords = data.loc.split(',');
        setUserPosition(parseFloat(coords[0]), parseFloat(coords[1]), 'gps');
      } else {
        updateLocationBarError('Không thể xác định vị trí. Nhấn vào bản đồ để chọn.');
        loadClinicsForMap(null, null);
      }
    })
    .catch(() => {
      updateLocationBarError('Không thể xác định vị trí. Nhấn vào bản đồ để chọn.');
      loadClinicsForMap(null, null);
    });
}

function updateLocationBarError(msg) {
  const bar = $('mapLocationBar');
  const text = $('mapLocationText');
  if (bar) bar.className = 'map-location-bar';
  if (text) text.textContent = `⚠️ ${msg}`;
}

async function loadClinicsForMap(lat, lng) {
  let url = '/api/clinics/map';
  if (lat != null) url += `?lat=${lat}&lng=${lng}`;

  // Show loading skeleton
  const list = $('mapClinicList');
  if (list) {
    list.innerHTML = `
      <div class="map-loading-card"><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div></div>
      <div class="map-loading-card"><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div></div>
      <div class="map-loading-card"><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div></div>
    `;
  }

  try {
    const res = await fetch(url);
    const data = await res.json();
    state.allClinics = data;
  } catch (e) {
    // Fallback to local data from API
    state.allClinics = [];
    try {
      const fallback = await fetch('/api/clinics/map');
      state.allClinics = await fallback.json();
      // Calculate distances client-side if needed
      if (lat && lng) {
        state.allClinics.forEach(c => {
          const R = 6371;
          const dlat = (c.lat - lat) * Math.PI / 180;
          const dlng = (c.lng - lng) * Math.PI / 180;
          const a = Math.sin(dlat / 2) ** 2 + Math.cos(lat * Math.PI / 180) * Math.cos(c.lat * Math.PI / 180) * Math.sin(dlng / 2) ** 2;
          c.distance = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        });
        state.allClinics.sort((a, b) => a.distance - b.distance);
      }
    } catch (e2) { /* empty */ }
  }

  renderMapCards(state.allClinics);
  renderMapMarkers(state.allClinics);
  if (lat == null && lng == null) {
    fitMapToMarkers();
  }
}

function fitMapToMarkers() {
  const markers = [...state.mapMarkers];
  if (state.userMarker) markers.push(state.userMarker);
  if (markers.length === 0) return;

  const group = L.featureGroup(markers);
  state.map.fitBounds(group.getBounds().pad(0.15), {
    maxZoom: 14,
    animate: true,
    duration: 0.8
  });
}

function renderMapCards(clinics) {
  const list = $('mapClinicList');
  if (!list) return;

  if (!clinics.length) {
    list.innerHTML = `
      <div class="map-empty">
        <div class="map-empty-icon">🔍</div>
        <p>Không tìm thấy phòng khám</p>
        <small>Thử tìm kiếm khác hoặc nhấn vào bản đồ</small>
      </div>`;
    return;
  }

  list.innerHTML = clinics.map((c, i) => {
    const distText = c.distance != null ? `${c.distance.toFixed(1)} km` : null;
    const isNearest = i === 0 && c.distance != null;
    return `
    <div class="map-clinic-card ${isNearest ? 'nearest' : ''}" id="map-card-${c.id}" onclick="selectClinicFromMap(${c.id})">
      <div class="map-clinic-name">${c.name}</div>
      <div class="map-clinic-address">📍 ${c.address}</div>
      <div class="map-clinic-meta">
        ${distText ? `<span class="map-badge badge-distance">🗺 ${distText}</span>` : ''}
        ${isNearest ? `<span class="map-badge badge-nearest">⭐ Gần nhất</span>` : ''}
        ${c.phone ? `<span class="map-badge badge-phone">📞 ${c.phone}</span>` : ''}
      </div>
      <button class="map-select-btn" onclick="if(typeof event !== 'undefined') event.stopPropagation(); confirmMapClinic(${c.id})">
        ✅ Chọn phòng khám này
      </button>
    </div>`;
  }).join('');
}

function renderMapMarkers(clinics) {
  state.mapMarkers.forEach(m => state.map.removeLayer(m));
  state.mapMarkers = [];

  const iconClinic = L.divIcon({
    className: '',
    html: `<div style="background:#0ea5e9; color:#fff; border-radius:50% 50% 50% 0; width:36px; height:36px; display:flex; align-items:center; justify-content:center; font-size:17px; transform:rotate(-45deg); box-shadow:0 3px 10px rgba(14,165,233,.4); border:2.5px solid #fff;"><span style="transform:rotate(45deg)">🏥</span></div>`,
    iconSize: [36, 36], iconAnchor: [18, 36], popupAnchor: [0, -38]
  });

  const iconNearest = L.divIcon({
    className: '',
    html: `<div style="background:linear-gradient(135deg, #059669, #10b981); color:#fff; border-radius:50% 50% 50% 0; width:44px; height:44px; display:flex; align-items:center; justify-content:center; font-size:20px; transform:rotate(-45deg); box-shadow:0 4px 16px rgba(16,185,129,.5); border:3px solid #fff;"><span style="transform:rotate(45deg)">🏥</span></div>`,
    iconSize: [44, 44], iconAnchor: [22, 44], popupAnchor: [0, -46]
  });

  clinics.forEach((c, i) => {
    const isNearest = i === 0 && c.distance != null;
    const icon = isNearest ? iconNearest : iconClinic;
    const distInfo = c.distance != null ? `<p style="color:#0ea5e9;font-weight:600;">🗺 ${c.distance.toFixed(1)} km</p>` : '';

    const marker = L.marker([c.lat, c.lng], { icon })
      .addTo(state.map)
      .bindPopup(`<div class="map-popup">
        ${isNearest ? '<span class="popup-nearest-badge">⭐ Gần bạn nhất</span>' : ''}
        <h4>${c.name}</h4>
        <p>📍 ${c.address}</p>
        ${distInfo}
        ${c.phone ? `<p>📞 ${c.phone}</p>` : ''}
        <button class="popup-btn" onclick="confirmMapClinic(${c.id})">✅ Chọn phòng khám này</button>
      </div>`);

    marker.clinicId = c.id;
    marker.on('click', () => {
      highlightMapCard(c.id);
      showMapBanner(c);
    });
    state.mapMarkers.push(marker);
  });
}

function selectClinicFromMap(id) {
  const clinic = state.allClinics.find(c => c.id === id);
  if (!clinic) return;
  state.selectedClinic = clinic;

  highlightMapCard(id);

  state.map.setView([clinic.lat, clinic.lng], 15, { animate: true, duration: 0.6 });
  const marker = state.mapMarkers.find(m => m.clinicId === id);
  if (marker) setTimeout(() => marker.openPopup(), 300);

  showMapBanner(clinic);
}

function highlightMapCard(id) {
  document.querySelectorAll('.map-clinic-card').forEach(el => el.classList.remove('active'));
  const card = $(`map-card-${id}`);
  if (card) {
    card.classList.add('active');
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function showMapBanner(clinic) {
  state.selectedClinic = clinic;
  $('mapBannerName').textContent = clinic.name;
  $('mapBannerAddress').textContent = clinic.address;
  const banner = $('mapSelectedBanner');
  banner.style.display = 'flex';
  banner.classList.add('show');
}

function confirmMapClinic(id) {
  const clinic = state.allClinics.find(c => c.id === id);
  if (clinic) {
    state.selectedClinic = clinic;
    confirmMapSelection();
  }
}

function confirmMapSelection() {
  if (!state.selectedClinic) return;

  const selectEl = $('bookingClinicSelect');
  if (selectEl) {
    let exists = false;
    for (let i = 0; i < selectEl.options.length; i++) {
      if (parseInt(selectEl.options[i].value) === state.selectedClinic.id) {
        exists = true;
        selectEl.selectedIndex = i;
        break;
      }
    }
    if (!exists) {
      const opt = document.createElement('option');
      opt.value = state.selectedClinic.id;
      opt.textContent = state.selectedClinic.name;
      selectEl.appendChild(opt);
      selectEl.value = state.selectedClinic.id;
    }
    handleStep2ClinicChange();
  }

  state.clinic = { id: state.selectedClinic.id, name: state.selectedClinic.name };
  closeMapModal();
}

function filterMapCards() {
  const q = $('mapSearchInput').value.toLowerCase();
  const filtered = state.allClinics.filter(c =>
    c.name.toLowerCase().includes(q) || c.address.toLowerCase().includes(q)
  );
  renderMapCards(filtered);
}

// ─── CHAT MODAL (SHARED) ───
function openMessageModal(doctorId, appId, name, userId = null) {
  $('messageModal').classList.add('active');
  $('messageModalSub').textContent = `Chat với ${name}`;
  state.currentMessageAppId = appId;
  if (state.user.role === 'patient') state.currentMessageUserId = doctorId; // is actually to_doctor_id
  else state.currentMessageUserId = userId; // is actually to_user_id
  loadMessageThread();
}
function closeMessageModal() { $('messageModal').classList.remove('active'); }

async function loadMessageThread() {
  const isDoc = state.user.role === 'doctor';
  const url = isDoc ? `/api/doctor/messages/${state.currentMessageAppId}` : `/api/messages/${state.currentMessageAppId}`;
  const res = await API(url);
  if (res.ok) {
    $('messageThread').innerHTML = res.data.map(m => `
      <div class="message-bubble ${m.sender_role === state.user.role ? 'sent' : 'received'}">
        <div class="message-content">${m.content}</div>
      </div>
    `).join('');
  }
}

async function handleSendMessage() {
  const content = $('messageContent').value;
  const isDoc = state.user.role === 'doctor';
  const url = isDoc ? '/api/doctor/message' : '/api/messages/send';
  const body = isDoc
    ? { to_user_id: state.currentMessageUserId, appointment_id: state.currentMessageAppId, content }
    : { to_doctor_id: state.currentMessageUserId, appointment_id: state.currentMessageAppId, content };

  const res = await API(url, { method: 'POST', body: JSON.stringify(body) });
  if (res.ok) { $('messageContent').value = ''; loadMessageThread(); }
}


// Alias sendMessage() cho nut trong HTML
function sendMessage() { handleSendMessage(); }

// ─── GUEST LOOKUP APPOINTMENT ───
function openLookupModal() {
  $('lookupModal').classList.add('active');
  $('lookupCodeInput').value = '';
  $('lookupAlert').innerHTML = '';
  $('lookupResult').style.display = 'none';
  state.lookupData = null;
}
function closeLookupModal() {
  $('lookupModal').classList.remove('active');
}

async function lookupAppointment() {
  const code = $('lookupCodeInput').value.trim();
  if (!code) {
    $('lookupAlert').innerHTML = '<div class="booking-validation-alert">Vui lòng nhập mã lịch hẹn</div>';
    return;
  }
  $('lookupAlert').innerHTML = 'Đang tìm kiếm...';
  $('lookupResult').style.display = 'none';

  const res = await API(`/api/appointments/lookup?code=${code}`);
  if (res.ok) {
    $('lookupAlert').innerHTML = '';
    const a = res.data;
    state.lookupData = a;
    $('lookupDetails').innerHTML = `
      <p><b>Mã LH:</b> ${a.booking_code}</p>
      <p><b>Bệnh nhân:</b> ${a.patient_name}</p>
      <p><b>Thời gian:</b> ${a.date} - ${a.time}</p>
      <p><b>Bác sĩ:</b> ${a.doctor_name}</p>
      <p><b>Phòng khám:</b> ${a.clinic_name}</p>
      <p><b>Trạng thái:</b> <span class="badge ${a.status === 'confirmed' ? 'badge-blue' : (a.status === 'completed' ? 'badge-success' : (a.status === 'cancelled' ? 'badge-danger' : 'badge-gray'))}">${a.status}</span></p>
    `;
    $('lookupResult').style.display = 'block';
    
    if (a.status !== 'confirmed') {
      $('lookupActions').style.display = 'none';
    } else {
      $('lookupActions').style.display = 'flex';
    }
  } else {
    $('lookupAlert').innerHTML = `<div class="booking-validation-alert">❌ Lỗi: ${res.data.detail}</div>`;
  }
}

async function cancelGuestApptFromLookup() {
  if (!state.lookupData) return;
  if (!confirm('Bạn có chắc chắn muốn hủy lịch hẹn này?')) return;
  
  const code = state.lookupData.booking_code;
  const res = await API(`/api/appointments/lookup/${code}/cancel`, { method: 'POST' });
  if (res.ok) {
    alert("Hủy lịch thành công!");
    closeLookupModal();
  } else {
    alert("Lỗi: " + res.data.detail);
  }
}

function startEditAppointmentFromLookup() {
  if (!state.lookupData) return;
  const a = state.lookupData;
  state.editAppId = a.id;
  state.editAppCode = a.booking_code;
  
  applyEditAppointmentData(a);
  closeLookupModal();
}

async function startEditAppointmentFromUser(appId) {
  // Find appointment data
  const res = await API('/api/me/appointments');
  if (res.ok) {
    const a = res.data.find(x => x.id === appId);
    if (!a) return;
    state.editAppId = a.id;
    state.editAppCode = null;
    // We need more details like patient_name, phone, dob which might not be in the short list
    // Actually we can just fetch it again or use default user info if not available
    // We will do a full lookup using our lookup endpoint because we don't have all info
    const fullRes = await API(`/api/appointments/lookup?code=${a.booking_code}`);
    if (fullRes.ok) {
      applyEditAppointmentData(fullRes.data);
    }
  }
}

function applyEditAppointmentData(a) {
  state.bookingFor = a.booking_for || 'self';
  const selfRadio = document.querySelector(`input[name="bookingFor"][value="${state.bookingFor}"]`);
  if (selfRadio) selfRadio.checked = true;
  handleBookingForChange();

  $('patientName').value = a.patient_name || '';
  $('patientEmail').value = a.patient_email || '';
  $('patientPhone').value = a.patient_phone || '';
  $('patientCCCD').value = a.patient_cccd || '';
  $('symptomsInput').value = a.symptoms || '';
  
  // Set doctor, clinic, date, time
  state.doctor = { id: a.doctor_id, name: a.doctor_name };
  state.clinic = { id: a.clinic_id, name: a.clinic_name };
  state.date = a.date;
  state.time = a.time;
  
  const btn = $('btnSubmitBooking');
  if (btn) btn.innerHTML = 'Cập Nhật Lịch Hẹn ✏️';

  showPatientSection('booking');
  goStep(1);
}

// ============================================================
// ADMIN LOGIC
// ============================================================
function initAdminLogic() {
    const adminSidebarItems = document.querySelectorAll('.admin-sidebar .menu-item');
    const adminSections = document.querySelectorAll('.admin-section');
    const adminPageTitle = document.getElementById('page-title');

    adminSidebarItems.forEach(item => {
        item.addEventListener('click', () => {
            adminSidebarItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            
            const target = item.getAttribute('data-target');
            if (target) {
                adminSections.forEach(sec => {
                    sec.classList.remove('active');
                    if (sec.id === target) {
                        sec.classList.add('active');
                        
                        if (target === 'dashboard') loadAdminStats();
                        else if (target === 'doctor') loadAdminDoctors();
                        else if (target === 'patient') loadAdminPatients();
                    }
                });
                if (adminPageTitle) adminPageTitle.textContent = item.querySelector('span').textContent;
            }
        });
    });
    
    // Initial load
    loadAdminStats();
}

async function loadAdminStats() {
    const res = await API('/api/admin/stats', { method: 'GET' });
    if (res.ok && res.data) {
        if ($('adminStatDoctors')) $('adminStatDoctors').textContent = res.data.total_doctors;
        if ($('adminStatPatients')) $('adminStatPatients').textContent = res.data.total_patients;
        if ($('adminStatApps')) $('adminStatApps').textContent = res.data.total_appointments;
        if ($('adminStatRevenue')) $('adminStatRevenue').textContent = new Intl.NumberFormat('vi-VN').format(res.data.total_revenue) + 'đ';
    }
}

async function loadAdminDoctors() {
    const res = await API('/api/admin/doctors', { method: 'GET' });
    if (res.ok && res.data) {
        const tbody = $('adminDoctorTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        res.data.forEach(doc => {
            const statusClass = doc.status === 'active' ? 'active' : (doc.status === 'locked' ? 'inactive' : 'pending');
            const statusText = doc.status === 'active' ? 'Đang làm việc' : (doc.status === 'locked' ? 'Đã khóa' : doc.status);
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><input type="checkbox"></td>
                <td><span class="text-bold">${doc.code}</span></td>
                <td>
                    <div class="table-user">
                        <img src="${doc.avatar}" alt="Avatar" onerror="this.src='https://i.pravatar.cc/150?img=12'">
                        <span>${doc.name}</span>
                    </div>
                </td>
                <td>${doc.specialty}</td>
                <td>${doc.phone}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>
                    <button class="btn-icon" title="Tính năng đang cập nhật" onclick="alert('Tính năng chỉnh sửa đang phát triển!')"><i class="fa-solid fa-pen"></i></button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
}

async function loadAdminPatients() {
    const res = await API('/api/admin/patients', { method: 'GET' });
    if (res.ok && res.data) {
        const tbody = $('adminPatientTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        res.data.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><input type="checkbox"></td>
                <td><span class="text-bold">${p.code}</span></td>
                <td>${p.name}</td>
                <td>${p.dob || '—'}</td>
                <td>${p.gender === 'male' ? 'Nam' : (p.gender === 'female' ? 'Nữ' : (p.gender === 'other' ? 'Khác' : '—'))}</td>
                <td>${p.phone || '—'}</td>
                <td>
                    <button class="btn-icon" title="Tính năng đang cập nhật" onclick="alert('Tính năng chỉnh sửa đang phát triển!')"><i class="fa-solid fa-pen"></i></button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
}

function initAdminCharts() {
    if (!window.Chart) return;
    
    // Check if charts already initialized
    if (window.revenueChart) window.revenueChart.destroy();
    if (window.appointmentChart) window.appointmentChart.destroy();

    const revCtx = document.getElementById('revenueChart');
    if (revCtx) {
        window.revenueChart = new Chart(revCtx, {
            type: 'line',
            data: {
                labels: ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'],
                datasets: [{
                    label: 'Doanh thu (Triệu VNĐ)',
                    data: [120, 150, 180, 140, 200, 250, 220, 280, 300, 320, 350, 400],
                    borderColor: '#0077b6',
                    backgroundColor: 'rgba(0, 119, 182, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    const appCtx = document.getElementById('appointmentChart');
    if (appCtx) {
        window.appointmentChart = new Chart(appCtx, {
            type: 'doughnut',
            data: {
                labels: ['Hoàn thành', 'Chờ xác nhận', 'Đã hủy'],
                datasets: [{
                    data: [65, 25, 10],
                    backgroundColor: ['#06d6a0', '#ffd166', '#ef476f'],
                    borderWidth: 0
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: '70%' }
        });
    }
}