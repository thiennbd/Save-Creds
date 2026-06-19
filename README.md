# Save Creds - Burp Suite Extension

**Save Creds** là một extension gọn nhẹ dành cho Burp Suite giúp người dùng thu thập, quản lý và xuất các thông tin định danh (Cookies, Tokens, JWTs) dưới dạng danh sách từ khóa.

---

## 🚀 Tính Năng Nổi Bật

- **Thu Thập & Chèn Nhanh:** Thêm cookie bằng menu "Send to Save Creds" và chèn lại vào Editor bằng menu "Add Creds".
- **Quản Lý Dạng Thẻ:** Giao diện trực quan cho phép đặt tên (Title), kéo thả, sao chép và tìm kiếm nhanh chóng.
- **Xuất Dữ Liệu Tùy Chọn:** Chọn lọc cookie cần xuất, tuỳ chọn format xuất.
- **Lưu Theo Project:** Dữ liệu tự động lưu riêng biệt cho từng Burp Project.

---

## 📖 Hướng Dẫn Sử Dụng

1. **Thu Thập Cookie:** Bôi đen giá trị cookie/token ở bất kỳ đâu trong Burp -> Chuột phải -> **Extensions** -> **Save Creds** -> **Send to Save Creds (New)**.
2. **Chỉnh Sửa & Quản Lý:** Chuyển sang tab **Save Creds**. Tại đây bạn có thể đặt Title, sửa giá trị, xoá thẻ, hoặc tích chọn (checkbox) các thẻ muốn lưu.
3. **Sử Dụng Lại Cookie:** 
   - Cách 1: Copy thủ công bằng nút Copy.
   - Cách 2: Trong tab Repeater/Proxy, nhấp chuột phải tại vị trí cần chèn -> **Extensions** -> **Save Creds** -> **Add Creds** -> Chọn tên cookie đã lưu để chèn trực tiếp.
4. **Xuất Danh Sách:** Nhấn **Export Wordlist** để lưu các giá trị đã tích chọn ra file `.txt` (có hỏi tuỳ chọn format khi xuất).

---

## 🛠️ Yêu Cầu Hệ Thống

- **Burp Suite**
- **Jython Standalone JAR**

---

## 📦 Hướng Dẫn Cài Đặt

1. Thiết lập Jython trong **Extensions** -> **Extension settings** -> **Python environment**.
2. Truy cập **Extensions** -> **Installed** -> **Add**.
3. Chọn **Extension type:** `Python` và chọn file `savecreds.py` của bạn để nạp.

---

# Save Creds - Burp Suite Extension (English)

**Save Creds** is a lightweight Burp Suite extension that helps users collect, manage, and export credentials (Cookies, Tokens, JWTs) as a wordlist.

---

## 🚀 Key Features

- **Quick Collect & Insert:** Add cookies via "Send to Save Creds" and insert them back into any Editor using "Add Creds".
- **Card-based Management:** Intuitive UI to name, drag & drop, copy, and search values quickly.
- **Customizable Export:** Select specific cookies, customize export format.
- **Project-Specific Storage:** Data is automatically saved and isolated per Burp Project.

---

## 📖 Usage Guide

1. **Collect Cookies:** Highlight a cookie/token value anywhere in Burp -> Right-click -> **Extensions** -> **Save Creds** -> **Send to Save Creds (New)**.
2. **Edit & Manage:** Go to the **Save Creds** tab. Here you can set Titles, edit values, delete cards, or check the boxes of the ones you want to export.
3. **Reuse Cookies:**
   - Option 1: Copy manually using the Copy button.
   - Option 2: In any Editor tab (e.g., Repeater), Right-click where you want to insert -> **Extensions** -> **Save Creds** -> **Add Creds** -> Select the saved cookie to insert it directly.
4. **Export Wordlist:** Click **Export Wordlist** to save checked items to a `.txt` file (prompts for format options).

---

## 🛠️ System Requirements

- **Burp Suite**
- **Jython Standalone JAR**

---

## 📦 Installation Guide

1. Configure Jython in **Extensions** -> **Extension settings** -> **Python environment**.
2. Go to **Extensions** -> **Installed** -> **Add**.
3. Select **Extension type:** `Python` and choose your `savecreds.py` file to load.