import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  createApiClient,
  fileToDataUrl,
  loadRuntimeSettings,
  normalizeServerUrl,
} from "./api";
import "./styles.css";

const ROOM_STATUSES = ["available", "reserved", "occupied", "cleaning", "maintenance"];
const PAYMENT_STATUSES = ["unpaid", "partial", "paid", "refunded"];
const SHIFT_STATUSES = ["scheduled", "completed", "cancelled"];
const ROOM_TYPES = ["Standard", "Deluxe", "Suite"];
const IMAGE_TYPES_BY_EXTENSION = {
  gif: "image/gif",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
};

const NAV_ITEMS = [
  { id: "dashboard", label: "Tổng quan" },
  { id: "rooms", label: "Phòng" },
  { id: "bookings", label: "Đặt phòng" },
  { id: "shifts", label: "Ca làm" },
  { id: "staff", label: "Nhân viên", adminOnly: true },
];

const EMPTY_ROOM_FORM = {
  number: "",
  room_type: "Standard",
  floor: 1,
  capacity: 2,
  price_per_night: 75,
  status: "available",
  amenities: "",
  notes: "",
};

const EMPTY_BOOKING_FORM = {
  room_id: "",
  check_in: today(),
  check_out: addDays(today(), 1),
  guest_name: "",
  guest_phone: "",
  guest_email: "",
  document_id: "",
  deposit: 0,
  payment_status: "unpaid",
};

const EMPTY_SHIFT_FORM = {
  staff_id: "",
  shift_date: today(),
  start_time: "09:00",
  end_time: "17:00",
  status: "scheduled",
  notes: "",
};

const EMPTY_STAFF_FORM = {
  username: "",
  full_name: "",
  password: "",
  is_active: true,
};

const VIEW_LABELS = {
  dashboard: "Tổng quan",
  rooms: "Phòng",
  bookings: "Đặt phòng",
  shifts: "Ca làm",
  staff: "Nhân viên",
};

const ROLE_LABELS = {
  admin: "Quản trị viên",
  staff: "Nhân viên",
};

const STATUS_LABELS = {
  active: "Đang hoạt động",
  available: "Sẵn sàng",
  cancelled: "Đã hủy",
  checked_in: "Đang lưu trú",
  cleaning: "Đang dọn",
  completed: "Hoàn tất",
  inactive: "Ngừng hoạt động",
  maintenance: "Bảo trì",
  occupied: "Đang ở",
  paid: "Đã thanh toán",
  partial: "Thanh toán một phần",
  refunded: "Đã hoàn tiền",
  reserved: "Đã đặt",
  scheduled: "Đã xếp lịch",
  unpaid: "Chưa thanh toán",
};

const ROOM_TYPE_LABELS = {
  Standard: "Tiêu chuẩn",
  Deluxe: "Cao cấp",
  Suite: "Suite",
};

const BOOKING_ACTION_MESSAGES = {
  cancel: "Đã hủy đặt phòng",
  checkin: "Đã nhận phòng",
  checkout: "Đã trả phòng",
};

const ACTIVITY_ACTION_LABELS = {
  cover: "đổi ảnh hiển thị",
  create: "tạo",
  delete: "xóa",
  login: "đăng nhập",
  status: "đổi trạng thái",
  update: "cập nhật",
  upload: "tải ảnh",
};

const ENTITY_LABELS = {
  booking: "đặt phòng",
  guest: "khách",
  room: "phòng",
  room_image: "ảnh phòng",
  shift: "ca làm",
  user: "người dùng",
};

function App() {
  const [serverUrl, setServerUrl] = useState("http://127.0.0.1:8000");
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [token, setToken] = useState(() => localStorage.getItem("hotel.token") || "");
  const [user, setUser] = useState(() => parseStoredUser());
  const [view, setView] = useState("dashboard");
  const [rooms, setRooms] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [staff, setStaff] = useState([]);
  const [summary, setSummary] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  const api = useMemo(
    () => createApiClient({ serverUrl, token, onUnauthorized: logout }),
    [serverUrl, token],
  );

  useEffect(() => {
    let alive = true;
    loadRuntimeSettings().then((url) => {
      if (!alive) {
        return;
      }
      setServerUrl(url);
      setSettingsLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (settingsLoaded && token) {
      refreshAll();
    }
  }, [settingsLoaded, token, serverUrl]);

  async function refreshAll() {
    setLoading(true);
    try {
      const [roomData, bookingData, shiftData, summaryData] = await Promise.all([
        api.request("/api/rooms"),
        api.request("/api/bookings"),
        api.request("/api/shifts"),
        api.request("/api/reports/summary"),
      ]);

      setRooms(roomData.rooms || []);
      setBookings(bookingData.bookings || []);
      setShifts(shiftData.shifts || []);
      setSummary(summaryData.summary || null);

      if (user?.role === "admin") {
        const [staffData, activityData] = await Promise.all([
          api.request("/api/staff"),
          api.request("/api/activity?limit=20"),
        ]);
        setStaff(staffData.staff || []);
        setActivity(activityData.activity || []);
      } else {
        setStaff([]);
        setActivity([]);
      }
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setLoading(false);
    }
  }

  async function login(credentials) {
    const cleanUrl = normalizeServerUrl(credentials.serverUrl);
    setServerUrl(cleanUrl);
    localStorage.setItem("hotel.serverUrl", cleanUrl);

    const loginApi = createApiClient({ serverUrl: cleanUrl, token: "" });
    const data = await loginApi.request("/api/login", {
      method: "POST",
      body: { username: credentials.username, password: credentials.password },
    });

    localStorage.setItem("hotel.token", data.token);
    localStorage.setItem("hotel.user", JSON.stringify(data.user));
    setToken(data.token);
    setUser(data.user);
    setView("dashboard");
    showToast(`Đã đăng nhập với tên ${data.user.full_name || data.user.username}.`, "success");
  }

  function logout() {
    localStorage.removeItem("hotel.token");
    localStorage.removeItem("hotel.user");
    setToken("");
    setUser(null);
    setRooms([]);
    setBookings([]);
    setShifts([]);
    setStaff([]);
    setActivity([]);
    setSummary(null);
  }

  function showToast(message, kind = "success") {
    setToast({ message, kind });
  }

  async function createRoom(values) {
    await api.request("/api/rooms", { method: "POST", body: values });
    showToast("Đã tạo phòng.");
    await refreshAll();
  }

  async function updateRoom(roomId, values) {
    try {
      await api.request(`/api/rooms/${roomId}`, { method: "PUT", body: values });
      showToast("Đã cập nhật phòng.");
      await refreshAll();
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    }
  }

  async function updateRoomStatus(roomId, status) {
    await api.request(`/api/rooms/${roomId}/status`, {
      method: "PATCH",
      body: { status },
    });
    showToast("Đã cập nhật trạng thái phòng.");
    await refreshAll();
  }

  async function uploadRoomImage(roomId, file, contentType = getImageContentType(file)) {
    const dataUrl = await fileToDataUrl(file);
    await api.request(`/api/rooms/${roomId}/images`, {
      method: "POST",
      body: {
        file_name: file.name,
        content_type: contentType,
        data_base64: dataUrl,
      },
    });
    showToast("Đã tải ảnh phòng.");
    await refreshAll();
  }

  async function deleteRoomImage(imageId) {
    await api.request(`/api/room-images/${imageId}`, { method: "DELETE" });
    showToast("Đã xóa ảnh phòng.");
    await refreshAll();
  }

  async function setRoomCoverImage(roomId, imageId) {
    await api.request(`/api/rooms/${roomId}/cover-image`, {
      method: "PATCH",
      body: { image_id: imageId },
    });
    showToast("Đã cập nhật ảnh hiển thị của phòng.");
    await refreshAll();
  }

  async function createBooking(values) {
    try {
      await api.request("/api/bookings", { method: "POST", body: values });
      showToast("Đã tạo đặt phòng.");
      await refreshAll();
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    }
  }

  async function bookingAction(booking, action) {
    let body = {};
    if (action === "checkout") {
      const nights = calculateNights(booking.check_in, booking.check_out);
      const baseTotal = nights * Number(booking.price_per_night || 0);
      const deposit = Number(booking.deposit || 0);
      const extraChargesInput = window.prompt(
        `Phụ phí (USD)\nSố đêm: ${nights}\nTiền phòng: ${currency(baseTotal)}\nĐã cọc: ${currency(deposit)}`,
        "0",
      );
      if (extraChargesInput === null) {
        return;
      }
      const extraCharges = Number(extraChargesInput || 0);
      if (Number.isNaN(extraCharges)) {
        showToast("Phụ phí phải là số.", "error");
        return;
      }
      if (extraCharges < 0) {
        showToast("Phụ phí không được âm.", "error");
        return;
      }
      const total = baseTotal + extraCharges;
      const due = total - deposit;
      const confirm = window.confirm(
        `Số đêm: ${nights}\nTổng tiền: ${currency(total)}\nĐã cọc: ${currency(deposit)}\nCần thanh toán: ${currency(due)}\nXác nhận trả phòng?`,
      );
      if (!confirm) {
        return;
      }
      body = { extra_charges: extraCharges, payment_status: "paid" };
    }

    await api.request(`/api/bookings/${booking.id}/${action}`, { method: "POST", body });
    showToast(BOOKING_ACTION_MESSAGES[action] || "Đã cập nhật đặt phòng.");
    await refreshAll();
  }

  async function createShift(values) {
    try {
      await api.request("/api/shifts", { method: "POST", body: values });
      showToast("Đã xếp ca làm.");
      await refreshAll();
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    }
  }

  async function cancelShift(shiftId) {
    await api.request(`/api/shifts/${shiftId}`, { method: "DELETE" });
    showToast("Đã hủy ca làm.");
    await refreshAll();
  }

  async function createStaff(values) {
    try {
      await api.request("/api/staff", { method: "POST", body: values });
      showToast("Đã tạo tài khoản nhân viên.");
      await refreshAll();
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    }
  }

  async function updateStaff(staffId, values) {
    try {
      await api.request(`/api/staff/${staffId}`, { method: "PUT", body: values });
      showToast("Đã cập nhật nhân viên.");
      await refreshAll();
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    }
  }

  async function deactivateStaff(staffId) {
    await api.request(`/api/staff/${staffId}`, { method: "DELETE" });
    showToast("Đã vô hiệu hóa tài khoản nhân viên.");
    await refreshAll();
  }

  async function deleteStaff(staffId) {
    try {
      await api.request(`/api/staff/${staffId}/delete`, { method: "POST" });
      showToast("Đã xóa tài khoản nhân viên.");
      await refreshAll();
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    }
  }

  async function changePassword(values) {
    try {
      await api.request("/api/me/password", { method: "POST", body: values });
      showToast("Đã cập nhật mật khẩu.");
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    }
  }

  if (!settingsLoaded) {
    return <Splash />;
  }

  if (!token || !user) {
    return (
      <LoginScreen
        serverUrl={serverUrl}
        onServerUrlChange={setServerUrl}
        onLogin={login}
        onError={(message) => showToast(message, "error")}
        toast={toast}
        onToastClose={() => setToast(null)}
      />
    );
  }

  return (
    <div className="app-shell">
      <Sidebar activeView={view} onNavigate={setView} user={user} />
      <main className="workspace">
        <Topbar user={user} view={view} loading={loading} onRefresh={refreshAll} onLogout={logout} />

        {view === "dashboard" && (
          <Dashboard
            rooms={rooms}
            bookings={bookings}
            shifts={shifts}
            staff={staff}
            summary={summary}
            activity={activity}
            user={user}
          />
        )}
        {view === "rooms" && (
          <RoomsView
            api={api}
            rooms={rooms}
            user={user}
            onCreateRoom={createRoom}
            onUpdateRoom={updateRoom}
            onStatusChange={updateRoomStatus}
            onUploadImage={uploadRoomImage}
            onDeleteImage={deleteRoomImage}
            onSetCoverImage={setRoomCoverImage}
          />
        )}
        {view === "bookings" && (
          <BookingsView
            bookings={bookings}
            rooms={rooms}
            user={user}
            onCreateBooking={createBooking}
            onBookingAction={bookingAction}
          />
        )}
        {view === "shifts" && (
          <ShiftsView
            shifts={shifts}
            staff={staff}
            user={user}
            onCreateShift={createShift}
            onCancelShift={cancelShift}
          />
        )}
        {view === "staff" && user.role === "admin" && (
          <StaffView
            staff={staff}
            onCreateStaff={createStaff}
            onUpdateStaff={updateStaff}
            onDeactivateStaff={deactivateStaff}
            onDeleteStaff={deleteStaff}
            onChangePassword={changePassword}
          />
        )}
      </main>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}

function Splash() {
  return (
    <div className="splash">
      <div className="loader" />
      <p>Đang tải không gian quản lý khách sạn...</p>
    </div>
  );
}

function LoginScreen({ serverUrl, onServerUrlChange, onLogin, onError, toast, onToastClose }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onLogin({ serverUrl, username, password });
    } catch (error) {
      onError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <section className="login-copy">
        <h1>Khách sạn Mường Thanh</h1>
        <p>
          Quản lý phòng, đặt phòng, ca làm và thông tin phòng.
        </p>
      </section>
      <form className="login-panel" onSubmit={handleSubmit}>
        <div>
          <h2>Đăng nhập</h2>
          <p>Dùng mật khẩu quản trị được in ở máy chủ hoặc tài khoản nhân viên do quản trị viên tạo.</p>
        </div>
        <label>
          Địa chỉ máy chủ
          <input
            value={serverUrl}
            onChange={(event) => onServerUrlChange(event.target.value)}
            spellCheck="false"
          />
        </label>
        <label>
          Tên đăng nhập
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoFocus />
        </label>
        <label>
          Mật khẩu
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
          />
        </label>
        <button className="primary-button" disabled={submitting}>
          {submitting ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>
      <Toast toast={toast} onClose={onToastClose} />
    </div>
  );
}

function Sidebar({ activeView, onNavigate, user }) {
  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark">HM</div>
        <div>
          <strong>Quản lý khách sạn</strong>
          <span>{user.role === "admin" ? "Bảng quản trị" : "Bảng nhân viên"}</span>
        </div>
      </div>
      <nav>
        {NAV_ITEMS.filter((item) => !item.adminOnly || user.role === "admin").map((item) => (
          <button
            key={item.id}
            className={activeView === item.id ? "active" : ""}
            onClick={() => onNavigate(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <span>Đang đăng nhập</span>
        <strong>{user.full_name || user.username}</strong>
      </div>
    </aside>
  );
}

function Topbar({ user, view, loading, onRefresh, onLogout }) {
  return (
    <header className="topbar">
      <div className="topbar-title">
        <p className="eyebrow">{loading ? "Đang đồng bộ dữ liệu" : "Không gian làm việc trực tiếp"}</p>
        <h1>{titleCase(view)}</h1>
      </div>
      <div className="topbar-actions">
        <span className={`sync-state ${loading ? "is-loading" : ""}`}>
          {loading ? "Đang cập nhật" : "Sẵn sàng"}
        </span>
        <div className="user-chip">
          <span>{user.full_name || user.username}</span>
          <small>{ROLE_LABELS[user.role] || user.role}</small>
        </div>
        <button className="secondary-button" onClick={onRefresh}>
          Làm mới
        </button>
        <button className="ghost-button" onClick={onLogout}>
          Đăng xuất
        </button>
      </div>
    </header>
  );
}

function Dashboard({ rooms, bookings, shifts, staff, summary, activity, user }) {
  const statusCounts = summary?.rooms || countBy(rooms, "status");
  const typeCounts = countBy(rooms, "room_type");
  const activeBookings = bookings.filter((booking) =>
    ["reserved", "checked_in"].includes(booking.status),
  ).length;
  const todayShifts = shifts.filter((shift) => shift.shift_date === today()).length;

  return (
    <div className="dashboard-grid">
      <MetricTile label="Phòng" value={rooms.length} helper="Tổng số phòng" tone="blue" />
      <MetricTile label="Đặt phòng đang mở" value={activeBookings} helper="Đã đặt và đang lưu trú" tone="green" />
      <MetricTile label="Khách đến" value={summary?.arrivals_today || 0} helper="Dự kiến hôm nay" tone="amber" />
      <MetricTile label="Khách đi" value={summary?.departures_today || 0} helper="Dự kiến hôm nay" tone="rose" />
      {user.role === "admin" && (
        <MetricTile
          label="Doanh thu"
          value={currency(summary?.completed_revenue || 0)}
          helper="Lượt ở đã hoàn tất"
          tone="ink"
        />
      )}
      {user.role === "admin" && (
        <MetricTile label="Nhân viên" value={staff.length} helper="Tài khoản đang quản lý" tone="purple" />
      )}

      <section className="panel chart-panel">
        <PanelHeader title="Trạng thái phòng" detail="Tổng quan vận hành" />
        <DonutChart data={statusCounts} />
      </section>
      <section className="panel chart-panel">
        <PanelHeader title="Phân bổ phòng" detail="Theo loại phòng" />
        <BarChart data={typeCounts} />
      </section>
      <section className="panel table-panel">
        <PanelHeader title="Đặt phòng gần đây" detail={`${bookings.length} bản ghi`} />
        <BookingMiniList bookings={bookings.slice(0, 6)} />
      </section>
      <section className="panel table-panel">
        <PanelHeader
          title={user.role === "admin" ? "Hoạt động" : "Ca làm của tôi"}
          detail={`${todayShifts} ca hôm nay`}
        />
        {user.role === "admin" ? <ActivityList activity={activity} /> : <ShiftMiniList shifts={shifts.slice(0, 6)} />}
      </section>
    </div>
  );
}

function RoomsView({
  api,
  rooms,
  user,
  onCreateRoom,
  onUpdateRoom,
  onStatusChange,
  onUploadImage,
  onDeleteImage,
  onSetCoverImage,
}) {
  const [filters, setFilters] = useState({
    search: "",
    type: "",
    status: "",
    minPrice: "",
    maxPrice: "",
  });
  const [selectedRoomId, setSelectedRoomId] = useState(null);

  useEffect(() => {
    if (selectedRoomId && !rooms.some((room) => room.id === selectedRoomId)) {
      setSelectedRoomId(null);
    }
  }, [rooms, selectedRoomId]);

  const roomTypes = uniqueValues(rooms.map((room) => room.room_type));
  const selectedRoom = rooms.find((room) => room.id === selectedRoomId) || rooms[0] || null;
  const filteredRooms = rooms.filter((room) => roomMatchesFilters(room, filters));

  return (
    <div className="rooms-layout">
      <section className="panel room-browser">
        <PanelHeader title="Phòng" detail={`${filteredRooms.length} đang hiển thị`} />
        <div className="filter-row">
          <input
            placeholder="Tìm số phòng, loại phòng, tiện nghi"
            value={filters.search}
            onChange={(event) => setFilters({ ...filters, search: event.target.value })}
          />
          <select value={filters.type} onChange={(event) => setFilters({ ...filters, type: event.target.value })}>
            <option value="">Tất cả loại phòng</option>
            {roomTypes.map((type) => (
              <option key={type} value={type}>
                {roomTypeLabel(type)}
              </option>
            ))}
          </select>
          <select
            value={filters.status}
            onChange={(event) => setFilters({ ...filters, status: event.target.value })}
          >
            <option value="">Tất cả trạng thái</option>
            {ROOM_STATUSES.map((status) => (
              <option key={status} value={status}>
                {label(status)}
              </option>
            ))}
          </select>
          <input
            type="number"
            min="0"
            placeholder="Giá thấp nhất"
            value={filters.minPrice}
            onChange={(event) => setFilters({ ...filters, minPrice: event.target.value })}
          />
          <input
            type="number"
            min="0"
            placeholder="Giá cao nhất"
            value={filters.maxPrice}
            onChange={(event) => setFilters({ ...filters, maxPrice: event.target.value })}
          />
        </div>
        <div className="room-grid">
          {filteredRooms.map((room) => (
            <RoomTile
              key={room.id}
              api={api}
              room={room}
              selected={selectedRoom?.id === room.id}
              onSelect={() => setSelectedRoomId(room.id)}
              onStatusChange={onStatusChange}
            />
          ))}
        </div>
      </section>

      <aside className="room-side-stack">
        <RoomDetails
          api={api}
          room={selectedRoom}
          canUpload={["admin", "staff"].includes(user.role)}
          canEdit={user.role === "admin"}
          onUpdateRoom={onUpdateRoom}
          onUploadImage={onUploadImage}
          onDeleteImage={onDeleteImage}
          onSetCoverImage={onSetCoverImage}
        />

        {user.role === "admin" && (
          <section className="panel create-panel">
            <PanelHeader title="Thêm phòng" detail="Chỉ quản trị viên" />
            <RoomForm onSubmit={onCreateRoom} />
          </section>
        )}
      </aside>
    </div>
  );
}

function RoomTile({ api, room, selected, onSelect, onStatusChange }) {
  return (
    <article className={`room-tile ${selected ? "selected" : ""}`} onClick={onSelect}>
      <div className="room-image-frame">
        <AuthorizedImage api={api} path={room.cover_image_url} alt={`Phòng ${room.number}`} />
      </div>
      <div className="room-tile-body">
        <div>
          <strong>Phòng {room.number}</strong>
          <span>{roomTypeLabel(room.room_type)}</span>
        </div>
        <p>
          Tầng {room.floor} / {room.capacity} khách / {currency(room.price_per_night)}
        </p>
        <div className="tile-footer">
          <select
            className={`status-select status-${room.status}`}
            value={room.status}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => onStatusChange(room.id, event.target.value)}
          >
            {ROOM_STATUSES.map((status) => (
              <option key={status} value={status}>
                {label(status)}
              </option>
            ))}
          </select>
          <span>{room.image_count || 0} ảnh</span>
        </div>
      </div>
    </article>
  );
}

function RoomDetails({
  api,
  room,
  canUpload,
  canEdit,
  onUpdateRoom,
  onUploadImage,
  onDeleteImage,
  onSetCoverImage,
}) {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [settingCoverId, setSettingCoverId] = useState(null);
  const [previewImage, setPreviewImage] = useState(null);
  const [imageError, setImageError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    if (!room) {
      setImages([]);
      setImageError("");
      setPreviewImage(null);
      return undefined;
    }

    setLoading(true);
    setImageError("");
    api
      .request(`/api/rooms/${room.id}/images`)
      .then((data) => {
        if (alive) {
          setImages(data.images || []);
        }
      })
      .catch(() => {
        if (alive) {
          setImages([]);
          setImageError("Không thể tải ảnh phòng.");
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, [api, room, reloadKey]);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !room) {
      return;
    }
    const contentType = getImageContentType(file);
    if (!contentType) {
      setImageError("Vui lòng chọn tệp hình ảnh.");
      return;
    }

    setUploading(true);
    setImageError("");
    try {
      await onUploadImage(room.id, file, contentType);
      setReloadKey((value) => value + 1);
    } catch (error) {
      setImageError(error.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(imageId) {
    setImageError("");
    try {
      await onDeleteImage(imageId);
      if (previewImage?.id === imageId) {
        setPreviewImage(null);
      }
      setReloadKey((value) => value + 1);
    } catch (error) {
      setImageError(error.message);
    }
  }

  async function handleSetCover(imageId) {
    if (!room || imageId === room.cover_image_id) {
      return;
    }

    setSettingCoverId(imageId);
    setImageError("");
    try {
      await onSetCoverImage(room.id, imageId);
      setReloadKey((value) => value + 1);
    } catch (error) {
      setImageError(error.message);
    } finally {
      setSettingCoverId(null);
    }
  }

  if (!room) {
    return (
      <section className="panel details-panel">
        <PanelHeader title="Chi tiết phòng" detail="Chọn một phòng" />
        <p className="empty-state">Chưa chọn phòng.</p>
      </section>
    );
  }

  return (
    <section className="panel details-panel">
      <PanelHeader title={`Phòng ${room.number}`} detail={roomTypeLabel(room.room_type)} />
      <div className="details-list">
        <div>
          <span>Trạng thái</span>
          <strong>{label(room.status)}</strong>
        </div>
        <div>
          <span>Giá</span>
          <strong>{currency(room.price_per_night)}</strong>
        </div>
        <div>
          <span>Sức chứa</span>
          <strong>{room.capacity} khách</strong>
        </div>
      </div>

      <div className="additional-info">
        <h3>Thông tin bổ sung</h3>
        <p>
          <strong>Tiện nghi:</strong> {room.amenities || "Chưa nhập tiện nghi."}
        </p>
        <p>
          <strong>Ghi chú:</strong> {room.notes || "Chưa có ghi chú phòng."}
        </p>
      </div>

      {canEdit && (
        <div className="details-editor">
          <h3>Chỉnh sửa phòng</h3>
          <RoomEditForm room={room} onSubmit={onUpdateRoom} />
        </div>
      )}

      <div className="media-header">
        <div>
          <h3>Ảnh phòng</h3>
          <p>{loading ? "Đang tải ảnh..." : `${images.length} ảnh đã tải`}</p>
        </div>
        {canUpload && (
          <label className="file-button">
            {uploading ? "Đang tải..." : "Thêm ảnh"}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        )}
      </div>
      {imageError && <p className="inline-error">{imageError}</p>}
      <div className="image-grid">
        {images.map((image) => (
          <figure key={image.id} className={`image-card ${image.is_cover ? "is-cover" : ""}`}>
            <button
              type="button"
              className="image-preview-button"
              onClick={() => setPreviewImage(image)}
              aria-label={`Xem ${image.file_name}`}
            >
              <AuthorizedImage api={api} path={image.url} alt={image.file_name} />
              {image.is_cover && <span className="cover-badge">Hiển thị</span>}
            </button>
            <figcaption>
              <span title={image.file_name}>{image.file_name}</span>
              {canUpload && (
                <div className="image-actions">
                  <button
                    type="button"
                    className="text-button"
                    disabled={image.is_cover || settingCoverId === image.id}
                    onClick={() => handleSetCover(image.id)}
                  >
                    {image.is_cover ? "Hiển thị" : settingCoverId === image.id ? "Đang lưu..." : "Dùng"}
                  </button>
                  <button type="button" className="text-button danger" onClick={() => handleDelete(image.id)}>
                    Xóa
                  </button>
                </div>
              )}
            </figcaption>
          </figure>
        ))}
        {!loading && images.length === 0 && <p className="empty-state">Phòng này chưa có ảnh.</p>}
      </div>
      {previewImage && (
        <ImageLightbox
          api={api}
          image={previewImage}
          room={room}
          onClose={() => setPreviewImage(null)}
        />
      )}
    </section>
  );
}

function RoomEditForm({ room, onSubmit }) {
  const [form, setForm] = useState(() => ({
    number: room?.number || "",
    room_type: room?.room_type || "Standard",
    floor: room?.floor ?? 1,
    capacity: room?.capacity ?? 2,
    price_per_night: room?.price_per_night ?? 0,
    status: room?.status || "available",
    amenities: room?.amenities || "",
    notes: room?.notes || "",
  }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setForm({
      number: room?.number || "",
      room_type: room?.room_type || "Standard",
      floor: room?.floor ?? 1,
      capacity: room?.capacity ?? 2,
      price_per_night: room?.price_per_night ?? 0,
      status: room?.status || "available",
      amenities: room?.amenities || "",
      notes: room?.notes || "",
    });
    setError("");
  }, [room]);

  function validate(values) {
    if (!values.number.trim()) {
      return "Vui lòng nhập số phòng.";
    }
    if (!values.room_type) {
      return "Vui lòng chọn loại phòng.";
    }
    const floorValue = Number(values.floor);
    if (Number.isNaN(floorValue) || floorValue < 0) {
      return "Tầng phải là số không âm.";
    }
    const capacityValue = Number(values.capacity);
    if (Number.isNaN(capacityValue) || capacityValue <= 0) {
      return "Sức chứa phải lớn hơn 0.";
    }
    const priceValue = Number(values.price_per_night);
    if (Number.isNaN(priceValue) || priceValue < 0) {
      return "Giá phải là số không âm.";
    }
    return "";
  }

  function updateForm(next) {
    setForm(next);
    if (error) {
      setError("");
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validate(form);
    if (message) {
      setError(message);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(room.id, {
        number: form.number.trim(),
        room_type: form.room_type,
        floor: Number(form.floor),
        capacity: Number(form.capacity),
        price_per_night: Number(form.price_per_night),
        status: form.status,
        amenities: form.amenities.trim(),
        notes: form.notes.trim(),
      });
    } catch (submitError) {
      setError(submitError?.message || "Không thể cập nhật phòng.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit}>
      <label>
        Số phòng
        <input value={form.number} onChange={(event) => updateForm({ ...form, number: event.target.value })} />
      </label>
      <label>
        Loại phòng
        <select
          value={form.room_type}
          onChange={(event) => updateForm({ ...form, room_type: event.target.value })}
        >
          {ROOM_TYPES.map((type) => (
            <option key={type} value={type}>
              {roomTypeLabel(type)}
            </option>
          ))}
        </select>
      </label>
      <div className="split-fields">
        <label>
          Tầng
          <input
            type="number"
            min="0"
            value={form.floor}
            onChange={(event) => updateForm({ ...form, floor: event.target.value })}
          />
        </label>
        <label>
          Sức chứa
          <input
            type="number"
            min="1"
            value={form.capacity}
            onChange={(event) => updateForm({ ...form, capacity: event.target.value })}
          />
        </label>
      </div>
      <label>
        Giá
        <input
          type="number"
          min="0"
          value={form.price_per_night}
          onChange={(event) => updateForm({ ...form, price_per_night: event.target.value })}
        />
      </label>
      <label>
        Trạng thái
        <select value={form.status} onChange={(event) => updateForm({ ...form, status: event.target.value })}>
          {ROOM_STATUSES.map((status) => (
            <option key={status} value={status}>
              {label(status)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tiện nghi
        <textarea
          value={form.amenities}
          onChange={(event) => updateForm({ ...form, amenities: event.target.value })}
        />
      </label>
      <label>
        Ghi chú
        <textarea value={form.notes} onChange={(event) => updateForm({ ...form, notes: event.target.value })} />
      </label>
      {error && <p className="inline-error">{error}</p>}
      <button className="primary-button" disabled={submitting}>
        {submitting ? "Đang lưu..." : "Lưu thay đổi"}
      </button>
    </form>
  );
}

function ImageLightbox({ api, image, room, onClose }) {
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="image-lightbox" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="image-lightbox-panel" onClick={(event) => event.stopPropagation()}>
        <div className="image-lightbox-header">
          <div>
            <strong>Phòng {room.number}</strong>
            <span>{image.file_name}</span>
          </div>
          <button type="button" className="ghost-button compact-button" onClick={onClose}>
            Đóng
          </button>
        </div>
        <div className="image-lightbox-frame">
          <AuthorizedImage api={api} path={image.url} alt={image.file_name} />
        </div>
      </div>
    </div>
  );
}

function RoomForm({ onSubmit }) {
  const [form, setForm] = useState(EMPTY_ROOM_FORM);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onSubmit({
        ...form,
        floor: Number(form.floor),
        capacity: Number(form.capacity),
        price_per_night: Number(form.price_per_night),
      });
      setForm({ ...EMPTY_ROOM_FORM });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit}>
      <label>
        Số phòng
        <input value={form.number} onChange={(event) => setForm({ ...form, number: event.target.value })} />
      </label>
      <label>
        Loại phòng
        <select value={form.room_type} onChange={(event) => setForm({ ...form, room_type: event.target.value })}>
          {ROOM_TYPES.map((type) => (
            <option key={type} value={type}>
              {roomTypeLabel(type)}
            </option>
          ))}
        </select>
      </label>
      <div className="split-fields">
        <label>
          Tầng
          <input
            type="number"
            value={form.floor}
            onChange={(event) => setForm({ ...form, floor: event.target.value })}
          />
        </label>
        <label>
          Sức chứa
          <input
            type="number"
            value={form.capacity}
            onChange={(event) => setForm({ ...form, capacity: event.target.value })}
          />
        </label>
      </div>
      <label>
        Giá
        <input
          type="number"
          min="0"
          value={form.price_per_night}
          onChange={(event) => setForm({ ...form, price_per_night: event.target.value })}
        />
      </label>
      <label>
        Trạng thái
        <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
          {ROOM_STATUSES.map((status) => (
            <option key={status} value={status}>
              {label(status)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tiện nghi
        <textarea value={form.amenities} onChange={(event) => setForm({ ...form, amenities: event.target.value })} />
      </label>
      <label>
        Ghi chú
        <textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
      </label>
      <button className="primary-button" disabled={submitting}>
        {submitting ? "Đang tạo..." : "Tạo phòng"}
      </button>
    </form>
  );
}

function BookingsView({ bookings, rooms, user, onCreateBooking, onBookingAction }) {
  return (
    <div className="two-column-view">
      <section className="panel table-panel wide-panel">
        <PanelHeader title="Đặt phòng" detail={`${bookings.length} bản ghi`} />
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Khách</th>
                <th>Phòng</th>
                <th>Ngày</th>
                <th>Trạng thái</th>
                <th>Thanh toán</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((booking) => (
                <tr key={booking.id}>
                  <td>
                    <strong>{booking.guest_name}</strong>
                    <span>{booking.guest_phone}</span>
                  </td>
                  <td>{booking.room_number}</td>
                  <td>
                    {booking.check_in} đến {booking.check_out}
                  </td>
                  <td>
                    <StatusPill value={booking.status} />
                  </td>
                  <td>{label(booking.payment_status)}</td>
                  <td className="action-cell">
                    {booking.status === "reserved" && (
                      <button className="text-button" onClick={() => onBookingAction(booking, "checkin")}>
                        Nhận phòng
                      </button>
                    )}
                    {booking.status === "checked_in" && (
                      <button className="text-button" onClick={() => onBookingAction(booking, "checkout")}>
                        Trả phòng
                      </button>
                    )}
                    {user.role === "admin" && ["reserved", "checked_in"].includes(booking.status) && (
                      <button className="text-button danger" onClick={() => onBookingAction(booking, "cancel")}>
                        Hủy
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel create-panel">
        <PanelHeader title="Đặt phòng mới" detail="Thông tin khách và lưu trú" />
        <BookingForm rooms={rooms} onSubmit={onCreateBooking} />
      </section>
    </div>
  );
}

function BookingForm({ rooms, onSubmit }) {
  const [form, setForm] = useState(EMPTY_BOOKING_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function validate(values) {
    if (!values.room_id) {
      return "Vui lòng chọn phòng.";
    }
    if (!values.check_in) {
      return "Vui lòng chọn ngày nhận phòng.";
    }
    if (!values.check_out) {
      return "Vui lòng chọn ngày trả phòng.";
    }
    const checkInDate = Date.parse(values.check_in);
    const checkOutDate = Date.parse(values.check_out);
    if (Number.isNaN(checkInDate) || Number.isNaN(checkOutDate)) {
      return "Ngày nhận và trả phòng phải theo định dạng YYYY-MM-DD.";
    }
    if (checkOutDate <= checkInDate) {
      return "Ngày trả phòng phải sau ngày nhận phòng.";
    }
    if (!values.guest_name.trim()) {
      return "Vui lòng nhập tên khách.";
    }
    if (!values.guest_phone.trim()) {
      return "Vui lòng nhập số điện thoại khách.";
    }
    const depositValue = Number(values.deposit || 0);
    if (Number.isNaN(depositValue)) {
      return "Tiền đặt cọc phải là số.";
    }
    if (depositValue < 0) {
      return "Tiền đặt cọc không được âm.";
    }
    return "";
  }

  function updateForm(next) {
    setForm(next);
    if (error) {
      setError("");
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validate(form);
    if (message) {
      setError(message);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({
        room_id: Number(form.room_id),
        check_in: form.check_in,
        check_out: form.check_out,
        deposit: Number(form.deposit || 0),
        payment_status: form.payment_status,
        guest: {
          full_name: form.guest_name.trim(),
          phone: form.guest_phone.trim(),
          email: form.guest_email.trim(),
          document_id: form.document_id.trim(),
        },
      });
      setForm({ ...EMPTY_BOOKING_FORM });
    } catch (submitError) {
      setError(submitError?.message || "Không thể tạo đặt phòng.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit}>
      <label>
        Phòng
        <select
          value={form.room_id}
          onChange={(event) => updateForm({ ...form, room_id: event.target.value })}
        >
          <option value="">Chọn phòng</option>
          {rooms.map((room) => (
            <option key={room.id} value={room.id}>
              {room.number} - {roomTypeLabel(room.room_type)} - {currency(room.price_per_night)}
            </option>
          ))}
        </select>
      </label>
      <div className="split-fields">
        <label>
          Ngày nhận phòng
          <input
            type="date"
            value={form.check_in}
            onChange={(event) => updateForm({ ...form, check_in: event.target.value })}
          />
        </label>
        <label>
          Ngày trả phòng
          <input
            type="date"
            value={form.check_out}
            onChange={(event) => updateForm({ ...form, check_out: event.target.value })}
          />
        </label>
      </div>
      <label>
        Tên khách
        <input
          value={form.guest_name}
          onChange={(event) => updateForm({ ...form, guest_name: event.target.value })}
          required
        />
      </label>
      <label>
        Số điện thoại
        <input
          value={form.guest_phone}
          onChange={(event) => updateForm({ ...form, guest_phone: event.target.value })}
          required
        />
      </label>
      <label>
        Email
        <input
          value={form.guest_email}
          onChange={(event) => updateForm({ ...form, guest_email: event.target.value })}
        />
      </label>
      <label>
        Giấy tờ
        <input
          value={form.document_id}
          onChange={(event) => updateForm({ ...form, document_id: event.target.value })}
        />
      </label>
      <div className="split-fields">
        <label>
          Tiền đặt cọc
          <input
            type="number"
            min="0"
            value={form.deposit}
            onChange={(event) => updateForm({ ...form, deposit: event.target.value })}
          />
        </label>
        <label>
          Trạng thái thanh toán
          <select
            value={form.payment_status}
            onChange={(event) => updateForm({ ...form, payment_status: event.target.value })}
          >
            {PAYMENT_STATUSES.map((status) => (
              <option key={status} value={status}>
                {label(status)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="inline-error">{error}</p>}
      <button className="primary-button" disabled={submitting}>
        {submitting ? "Đang tạo..." : "Tạo đặt phòng"}
      </button>
    </form>
  );
}
function ShiftsView({ shifts, staff, user, onCreateShift, onCancelShift }) {
  return (
    <div className="two-column-view">
      <section className="panel table-panel wide-panel">
        <PanelHeader title={user.role === "admin" ? "Quản lý ca làm" : "Ca làm của tôi"} detail={`${shifts.length} ca`} />
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Nhân viên</th>
                <th>Ngày</th>
                <th>Thời gian</th>
                <th>Trạng thái</th>
                <th>Ghi chú</th>
                {user.role === "admin" && <th>Thao tác</th>}
              </tr>
            </thead>
            <tbody>
              {shifts.map((shift) => (
                <tr key={shift.id}>
                  <td>{shift.staff_name || shift.staff_username}</td>
                  <td>{shift.shift_date}</td>
                  <td>
                    {shift.start_time} đến {shift.end_time}
                  </td>
                  <td>
                    <StatusPill value={shift.status} />
                  </td>
                  <td>{shift.notes || "-"}</td>
                  {user.role === "admin" && (
                    <td>
                      {shift.status !== "cancelled" && (
                        <button className="text-button danger" onClick={() => onCancelShift(shift.id)}>
                          Hủy
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {user.role === "admin" && (
        <section className="panel create-panel">
          <PanelHeader title="Xếp ca làm" detail="Chỉ quản trị viên" />
          <ShiftForm staff={staff} onSubmit={onCreateShift} />
        </section>
      )}
    </div>
  );
}

function ShiftForm({ staff, onSubmit }) {
  const [form, setForm] = useState(EMPTY_SHIFT_FORM);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onSubmit({ ...form, staff_id: Number(form.staff_id) });
      setForm({ ...EMPTY_SHIFT_FORM });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit}>
      <label>
        Nhân viên
        <select value={form.staff_id} onChange={(event) => setForm({ ...form, staff_id: event.target.value })}>
          <option value="">Chọn nhân viên</option>
          {staff
            .filter((member) => member.is_active)
            .map((member) => (
              <option key={member.id} value={member.id}>
                {member.full_name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Ngày
        <input
          type="date"
          value={form.shift_date}
          onChange={(event) => setForm({ ...form, shift_date: event.target.value })}
        />
      </label>
      <div className="split-fields">
        <label>
          Bắt đầu
          <input
            type="time"
            value={form.start_time}
            onChange={(event) => setForm({ ...form, start_time: event.target.value })}
          />
        </label>
        <label>
          Kết thúc
          <input
            type="time"
            value={form.end_time}
            onChange={(event) => setForm({ ...form, end_time: event.target.value })}
          />
        </label>
      </div>
      <label>
        Trạng thái
        <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
          {SHIFT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {label(status)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Ghi chú
        <textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
      </label>
      <button className="primary-button" disabled={submitting || !form.staff_id}>
        {submitting ? "Đang xếp ca..." : "Xếp ca"}
      </button>
    </form>
  );
}

function StaffView({
  staff,
  onCreateStaff,
  onUpdateStaff,
  onDeactivateStaff,
  onDeleteStaff,
  onChangePassword,
}) {
  const [editingStaff, setEditingStaff] = useState(null);

  useEffect(() => {
    if (!editingStaff) {
      return;
    }
    const match = staff.find((member) => member.id === editingStaff.id);
    if (!match) {
      setEditingStaff(null);
    } else if (match !== editingStaff) {
      setEditingStaff(match);
    }
  }, [staff, editingStaff]);

  async function handleDelete(member) {
    const confirmed = window.confirm(`Xóa tài khoản ${member.username}?`);
    if (!confirmed) {
      return;
    }
    await onDeleteStaff(member.id);
    if (editingStaff?.id === member.id) {
      setEditingStaff(null);
    }
  }

  return (
    <div className="two-column-view">
      <section className="panel table-panel wide-panel">
        <PanelHeader title="Tài khoản nhân viên" detail={`${staff.length} tài khoản`} />
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Tên</th>
                <th>Tên đăng nhập</th>
                <th>Trạng thái</th>
                <th>Ngày tạo</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {staff.map((member) => (
                <tr key={member.id}>
                  <td>{member.full_name}</td>
                  <td>{member.username}</td>
                  <td>
                    <StatusPill value={member.is_active ? "active" : "inactive"} />
                  </td>
                  <td>{member.created_at}</td>
                  <td>
                    <div className="action-stack">
                      <button className="text-button" onClick={() => setEditingStaff(member)}>
                        Sửa
                      </button>
                      {member.is_active ? (
                        <button className="text-button danger" onClick={() => onDeactivateStaff(member.id)}>
                          Vô hiệu hóa
                        </button>
                      ) : null}
                      <button className="text-button danger" onClick={() => handleDelete(member)}>
                        Xóa
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <aside className="side-stack">
        <section className="panel create-panel">
          <PanelHeader title="Thêm nhân viên" detail="Chỉ quản trị viên" />
          <StaffForm onSubmit={onCreateStaff} />
        </section>
        {editingStaff && (
          <section className="panel create-panel">
            <PanelHeader title="Cập nhật nhân viên" detail={editingStaff.username} />
            <StaffEditForm
              staff={editingStaff}
              onSubmit={onUpdateStaff}
              onCancel={() => setEditingStaff(null)}
            />
          </section>
        )}
        <section className="panel create-panel">
          <PanelHeader title="Đổi mật khẩu" detail="Tài khoản quản trị" />
          <PasswordChangeForm onSubmit={onChangePassword} />
        </section>
      </aside>
    </div>
  );
}

function StaffForm({ onSubmit }) {
  const [form, setForm] = useState(EMPTY_STAFF_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function validate(values) {
    if (!values.username.trim()) {
      return "Vui lòng nhập tên đăng nhập.";
    }
    if (!values.full_name.trim()) {
      return "Vui lòng nhập họ và tên.";
    }
    if (!values.password) {
      return "Vui lòng nhập mật khẩu.";
    }
    if (values.password.length < 8) {
      return "Mật khẩu phải có ít nhất 8 ký tự.";
    }
    return "";
  }

  function updateForm(next) {
    setForm(next);
    if (error) {
      setError("");
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validate(form);
    if (message) {
      setError(message);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({
        ...form,
        username: form.username.trim(),
        full_name: form.full_name.trim(),
      });
      setForm({ ...EMPTY_STAFF_FORM });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit}>
      <label>
        Tên đăng nhập
        <input
          value={form.username}
          onChange={(event) => updateForm({ ...form, username: event.target.value })}
          required
        />
      </label>
      <label>
        Họ và tên
        <input
          value={form.full_name}
          onChange={(event) => updateForm({ ...form, full_name: event.target.value })}
          required
        />
      </label>
      <label>
        Mật khẩu
        <input
          type="password"
          value={form.password}
          onChange={(event) => updateForm({ ...form, password: event.target.value })}
          minLength={8}
          required
        />
      </label>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => updateForm({ ...form, is_active: event.target.checked })}
        />
        Tài khoản hoạt động
      </label>
      {error && <p className="inline-error">{error}</p>}
      <button className="primary-button" disabled={submitting}>
        {submitting ? "Đang tạo..." : "Tạo nhân viên"}
      </button>
    </form>
  );
}

function StaffEditForm({ staff, onSubmit, onCancel }) {
  const [form, setForm] = useState(() => ({
    username: staff.username || "",
    full_name: staff.full_name || "",
    password: "",
    is_active: Boolean(staff.is_active),
  }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setForm({
      username: staff.username || "",
      full_name: staff.full_name || "",
      password: "",
      is_active: Boolean(staff.is_active),
    });
    setError("");
  }, [staff]);

  function validate(values) {
    if (!values.username.trim()) {
      return "Vui lòng nhập tên đăng nhập.";
    }
    if (!values.full_name.trim()) {
      return "Vui lòng nhập họ và tên.";
    }
    if (values.password && values.password.length < 8) {
      return "Mật khẩu phải có ít nhất 8 ký tự.";
    }
    return "";
  }

  function updateForm(next) {
    setForm(next);
    if (error) {
      setError("");
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validate(form);
    if (message) {
      setError(message);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(staff.id, {
        username: form.username.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        is_active: form.is_active,
      });
      onCancel();
    } catch (submitError) {
      setError(submitError?.message || "Không thể cập nhật nhân viên.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit}>
      <label>
        Tên đăng nhập
        <input
          value={form.username}
          onChange={(event) => updateForm({ ...form, username: event.target.value })}
          required
        />
      </label>
      <label>
        Họ và tên
        <input
          value={form.full_name}
          onChange={(event) => updateForm({ ...form, full_name: event.target.value })}
          required
        />
      </label>
      <label>
        Mật khẩu mới
        <input
          type="password"
          value={form.password}
          onChange={(event) => updateForm({ ...form, password: event.target.value })}
          minLength={8}
          placeholder="Để trống nếu không đổi"
        />
      </label>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => updateForm({ ...form, is_active: event.target.checked })}
        />
        Tài khoản hoạt động
      </label>
      {error && <p className="inline-error">{error}</p>}
      <div className="form-actions">
        <button type="button" className="ghost-button" onClick={onCancel} disabled={submitting}>
          Hủy
        </button>
        <button className="primary-button" disabled={submitting}>
          {submitting ? "Đang lưu..." : "Lưu thay đổi"}
        </button>
      </div>
    </form>
  );
}

function PasswordChangeForm({ onSubmit }) {
  const [form, setForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function validate(values) {
    if (!values.current_password) {
      return "Vui lòng nhập mật khẩu hiện tại.";
    }
    if (!values.new_password) {
      return "Vui lòng nhập mật khẩu mới.";
    }
    if (values.new_password.length < 8) {
      return "Mật khẩu mới phải có ít nhất 8 ký tự.";
    }
    if (values.new_password !== values.confirm_password) {
      return "Mật khẩu xác nhận không khớp.";
    }
    return "";
  }

  function updateForm(next) {
    setForm(next);
    if (error) {
      setError("");
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validate(form);
    if (message) {
      setError(message);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({
        current_password: form.current_password,
        new_password: form.new_password,
      });
      setForm({ current_password: "", new_password: "", confirm_password: "" });
    } catch (submitError) {
      setError(submitError?.message || "Không thể đổi mật khẩu.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit}>
      <label>
        Mật khẩu hiện tại
        <input
          type="password"
          value={form.current_password}
          onChange={(event) => updateForm({ ...form, current_password: event.target.value })}
          required
        />
      </label>
      <label>
        Mật khẩu mới
        <input
          type="password"
          value={form.new_password}
          onChange={(event) => updateForm({ ...form, new_password: event.target.value })}
          minLength={8}
          required
        />
      </label>
      <label>
        Xác nhận mật khẩu mới
        <input
          type="password"
          value={form.confirm_password}
          onChange={(event) => updateForm({ ...form, confirm_password: event.target.value })}
          minLength={8}
          required
        />
      </label>
      {error && <p className="inline-error">{error}</p>}
      <button className="primary-button" disabled={submitting}>
        {submitting ? "Đang cập nhật..." : "Cập nhật mật khẩu"}
      </button>
    </form>
  );
}

function AuthorizedImage({ api, path, alt }) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [path]);

  if (!path || failed) {
    return <div className="image-placeholder">Chưa có ảnh</div>;
  }

  return <img src={api.imageUrl(path)} alt={alt} onError={() => setFailed(true)} />;
}

function MetricTile({ label: labelText, value, helper, tone }) {
  return (
    <section className={`metric-tile tone-${tone}`}>
      <span>{labelText}</span>
      <strong>{value}</strong>
      <small>{helper}</small>
    </section>
  );
}

function PanelHeader({ title, detail }) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      <span>{detail}</span>
    </div>
  );
}

function DonutChart({ data }) {
  const entries = Object.entries(data || {}).filter(([, value]) => value > 0);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  const circumference = 2 * Math.PI * 44;
  let offset = 0;

  return (
    <div className="donut-wrap">
      <svg className="donut-chart" viewBox="0 0 120 120" role="img" aria-label="Biểu đồ trạng thái phòng">
        <circle className="donut-track" cx="60" cy="60" r="44" />
        {entries.map(([name, value], index) => {
          const length = (value / total) * circumference;
          const dashOffset = -offset;
          offset += length;
          return (
            <circle
              key={name}
              className={`donut-segment segment-${index}`}
              cx="60"
              cy="60"
              r="44"
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={dashOffset}
            />
          );
        })}
        <text x="60" y="55" textAnchor="middle" className="donut-total">
          {total}
        </text>
        <text x="60" y="72" textAnchor="middle" className="donut-caption">
          phòng
        </text>
      </svg>
      <div className="chart-legend">
        {entries.length === 0 && <span>Chưa có dữ liệu</span>}
        {entries.map(([name, value], index) => (
          <span key={name}>
            <i className={`legend-dot segment-${index}`} />
            {label(name)}: {value}
          </span>
        ))}
      </div>
    </div>
  );
}

function BarChart({ data }) {
  const entries = Object.entries(data || {}).filter(([, value]) => value > 0);
  const max = Math.max(1, ...entries.map(([, value]) => value));

  return (
    <div className="bar-list">
      {entries.length === 0 && <p className="empty-state">Chưa có dữ liệu loại phòng.</p>}
      {entries.map(([name, value]) => (
        <div className="bar-row" key={name}>
          <div className="bar-label">
            <span>{roomTypeLabel(name)}</span>
            <strong>{value}</strong>
          </div>
          <div className="bar-track">
            <div style={{ width: `${(value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function BookingMiniList({ bookings }) {
  if (bookings.length === 0) {
    return <p className="empty-state">Chưa có đặt phòng.</p>;
  }

  return (
    <div className="mini-list">
      {bookings.map((booking) => (
        <div key={booking.id}>
          <strong>{booking.guest_name}</strong>
          <span>
            Phòng {booking.room_number} / {label(booking.status)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ShiftMiniList({ shifts }) {
  if (shifts.length === 0) {
    return <p className="empty-state">Chưa có ca làm.</p>;
  }

  return (
    <div className="mini-list">
      {shifts.map((shift) => (
        <div key={shift.id}>
          <strong>{shift.shift_date}</strong>
          <span>
            {shift.start_time} đến {shift.end_time} / {label(shift.status)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ActivityList({ activity }) {
  if (activity.length === 0) {
    return <p className="empty-state">Chưa có hoạt động.</p>;
  }

  return (
    <div className="mini-list">
      {activity.slice(0, 7).map((item) => (
        <div key={item.id}>
          <strong>{item.username}</strong>
          <span>
            {activityActionLabel(item.action)} {entityLabel(item.entity)} {item.entity_id ? `#${item.entity_id}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

function StatusPill({ value }) {
  return <span className={`status-pill status-${value}`}>{label(value)}</span>;
}

function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timer = window.setTimeout(onClose, 4200);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);

  if (!toast) {
    return null;
  }

  return (
    <div className={`toast toast-${toast.kind}`}>
      <span>{toast.message}</span>
      <button onClick={onClose}>Đóng</button>
    </div>
  );
}

function parseStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("hotel.user") || "null");
  } catch {
    return null;
  }
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function addDays(dateText, days) {
  const date = new Date(`${dateText}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function calculateNights(checkIn, checkOut) {
  const start = new Date(`${checkIn}T00:00:00`);
  const end = new Date(`${checkOut}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 1;
  }
  const diffDays = Math.round((end - start) / (24 * 60 * 60 * 1000));
  return Math.max(1, diffDays);
}

function currency(value) {
  return Number(value || 0).toLocaleString("vi-VN", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function label(value) {
  const text = String(value || "");
  return STATUS_LABELS[text] || text.replaceAll("_", " ");
}

function titleCase(value) {
  return VIEW_LABELS[value] || label(value || "dashboard");
}

function roomTypeLabel(value) {
  return ROOM_TYPE_LABELS[value] || value || "Không xác định";
}

function activityActionLabel(value) {
  return ACTIVITY_ACTION_LABELS[value] || label(value);
}

function entityLabel(value) {
  return ENTITY_LABELS[value] || label(value);
}

function countBy(items, key) {
  return items.reduce((counts, item) => {
    const value = item[key] || "Không xác định";
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))].sort((first, second) => first.localeCompare(second));
}

function roomMatchesFilters(room, filters) {
  const search = filters.search.trim().toLowerCase();
  const minPrice = filters.minPrice === "" ? -Infinity : Number(filters.minPrice);
  const maxPrice = filters.maxPrice === "" ? Infinity : Number(filters.maxPrice);
  const price = Number(room.price_per_night || 0);
  const text = `${room.number} ${room.room_type} ${room.amenities} ${room.notes}`.toLowerCase();

  return (
    (!search || text.includes(search)) &&
    (!filters.type || room.room_type === filters.type) &&
    (!filters.status || room.status === filters.status) &&
    (Number.isNaN(minPrice) || price >= minPrice) &&
    (Number.isNaN(maxPrice) || price <= maxPrice)
  );
}

function getImageContentType(file) {
  if (file.type && file.type.startsWith("image/")) {
    return file.type;
  }
  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  return IMAGE_TYPES_BY_EXTENSION[extension] || "";
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
