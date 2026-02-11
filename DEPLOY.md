# 🚀 Hướng Dẫn Triển Khai Nanobot lên VPS

Tài liệu này hướng dẫn bạn cách đưa Nanobot lên chạy trên VPS Linux (Ubuntu/Debian) một cách chuyên nghiệp, ổn định 24/7.

## 📋 Yêu Cầu Chuẩn Bị
1.  **VPS**: Một máy chủ ảo chạy Ubuntu 20.04 hoặc 22.04 LTS.
    *   Cấu hình tối thiểu: 1 vCPU, 1GB RAM.
2.  **GitHub**: Tài khoản GitHub để lưu trữ code.
3.  **SSH Client**: Terminal (Mac/Linux) hoặc PuTTY (Windows) để kết nối VPS.

---

## Phần 1: Đẩy Code lên GitHub (Thực hiện trên máy Mac của bạn)

Nếu bạn chưa có repo trên GitHub, hãy tạo mới một repo (Private recommended) và làm theo:

1.  **Khởi tạo Git (nếu chưa có):**
    ```bash
    cd /Users/thesung/Documents/nanobot
    git init
    git branch -M main
    ```

2.  **Commit code:**
    ```bash
    git add .
    git commit -m "First commit: Nanobot setup with Docker"
    ```

3.  **Kết nối & Push lên GitHub:**
    ```bash
    git remote add origin https://github.com/YOUR_USERNAME/nanobot-repo.git
    git push -u origin main
    ```
    *(Thay `YOUR_USERNAME` và `nanobot-repo` bằng thông tin thật của bạn)*

---

## Phần 2: Cài Đặt Môi Trường trên VPS

Kết nối vào VPS của bạn qua SSH:
```bash
ssh root@<IP_VPS_CUA_BAN>
```

Sau khi vào được VPS, chạy lần lượt các lệnh sau:

### 1. Cài đặt Docker & Docker Compose
```bash
# Cập nhật hệ thống
apt update && apt upgrade -y

# Cài đặt công cụ cần thiết
apt install -y curl git

# Cài đặt Docker tự động
curl -fsSL https://get.docker.com | sh

# Bật Docker khởi động cùng hệ thống
systemctl enable --now docker
```

---

## Phần 3: Deploy Nanobot

### 1. Kéo Code về VPS
```bash
# Clone repo của bạn về thư mục /opt/nanobot
cd /opt
git clone https://github.com/YOUR_USERNAME/nanobot-repo.git nanobot
cd nanobot
```
*(Nếu repo Private, bạn cần nhập username/token hoặc setup SSH Key)*

### 2. Cấu hình Env
Tạo file `.env` hoặc copy config mẫu (nếu bạn commit file config lên - **lưu ý bảo mật**).
Cách tốt nhất là tạo file config trực tiếp trên VPS để tránh lộ API Key:

```bash
# Tạo thư mục config cho volume mapping
mkdir -p ~/.nanobot
nano ~/.nanobot/config.json
```
*(Copy nội dung file `config.json` từ máy bạn dán vào đây, rồi nhấn Ctrl+O -> Enter -> Ctrl+X để lưu)*

### 3. Khởi chạy Bot
Tại thư mục `/opt/nanobot`, chạy lệnh:
```bash
docker compose up -d --build
```
*   `-d`: Chạy ngầm (Detached mode).
*   `--build`: Build lại image nếu có thay đổi.

### 4. Kiểm tra
Xem bot có đang chạy không:
```bash
docker compose ps
```
Xem log của bot:
```bash
docker compose logs -f
```
*(Nhấn Ctrl+C để thoát xem log)*

---

## 🔄 Quy Trình Cập Nhật (Update Workflow)

Mỗi khi bạn sửa code hoặc cập nhật tính năng trên máy tính cá nhân:

1.  **Tại máy tính:**
    ```bash
    git add .
    git commit -m "Update feature X"
    git push
    ```

2.  **Tại VPS (SSH vào):**
    ```bash
    cd /opt/nanobot
    git pull
    docker compose up -d --build
    ```
    *Hệ thống sẽ tự động build lại phần thay đổi và khởi động lại bot (thời gian downtime chỉ vài giây).*

---

## 🛠️ Các Lệnh Hữu Ích Khác

*   **Khởi động lại bot:** `docker compose restart`
*   **Dừng bot:** `docker compose down`
*   **Xem log realtime:** `docker compose logs -f --tail=100`
*   **Dọn dẹp Docker rác:** `docker system prune -f`
