# AlanOffer backend

Backend اولیه برای تست واقعی اهواز.

## معماری
- Node.js + Express
- SQLite روی دیسک پایدار
- ثبت عمومی -> صف pending
- تایید/رد مدیر -> بانک عمومی
- Neshan Search API فقط از سمت سرور

## اجرای محلی
```bash
cd backend
npm install
ADMIN_TOKEN='a-long-random-secret' npm start
```

## متغیرهای محیطی
```text
PORT=8787
DB_PATH=/app/data/alanoffer.db
CORS_ORIGINS=https://hajizadehmasoud5-ui.github.io
ADMIN_TOKEN=<long-random-secret>
NESHAN_API_KEY=<service-api-key-after-activation>
```

## استقرار Docker
این پوشه Dockerfile آماده دارد. روی سرویس میزبان یک دیسک persistent به `/app/data` متصل کنید تا دیتابیس با deploy مجدد پاک نشود.

پس از استقرار، آدرس HTTPS بک‌اند را در صفحه `backend-setup.html` ثبت کنید.

## صفحات مدیریتی سایت
- `backend-setup.html`: اتصال سایت به بک‌اند
- `admin.html`: تایید/رد ثبت‌های کاربران
- `import-neshan.html`: جست‌وجو در نشان و ورود انتخابی کسب‌وکارها

## APIهای اصلی
- `GET /api/health`
- `GET /api/businesses`
- `POST /api/submissions`
- `GET /api/admin/submissions`
- `POST /api/admin/submissions/:id/approve`
- `POST /api/admin/submissions/:id/reject`
- `POST /api/admin/businesses`
- `GET /api/neshan/search`
