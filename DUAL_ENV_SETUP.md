# 🔄 دليل العمل على البيئتين (محلي + Render)

## ✅ ما تم تطبيقه

النظام الآن **يعمل تلقائياً** على:
- 💻 **محلياً**: `http://127.0.0.1:5000` أو `https://127.0.0.1:5000`
- 🌐 **Render**: `https://hhh-ftzf.onrender.com`

## 🔍 الكشف التلقائي

النظام يكتشف البيئة تلقائياً من:
- **Render**: وجود متغير `RENDER` أو `PORT` (غير 5000)
- **محلي**: عدم وجود المتغيرات أعلاه

## 🔗 Redirect URIs التلقائية

### TikTok OAuth
- **محلي**: `http://127.0.0.1:5000/tiktok/callback`
- **Render**: `https://hhh-ftzf.onrender.com/tiktok/callback`

### YouTube OAuth
- **محلي**: `http://127.0.0.1:5000/youtube/callback`
- **Render**: `https://hhh-ftzf.onrender.com/youtube/callback`

## 📋 إعدادات Render

### Environment Variables في Render Dashboard:

```
# المفاتيح الحساسة (مطلوبة)
FACEBOOK_PAGE_ID=...
FACEBOOK_ACCESS_TOKEN=...
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
APP_PASSWORD=...

# Redirect URIs (اختياري - النظام يكتشفها تلقائياً)
GOOGLE_REDIRECT_URI=https://hhh-ftzf.onrender.com/youtube/callback
TIKTOK_REDIRECT_URI=https://hhh-ftzf.onrender.com/tiktok/callback

# إعدادات عامة
SERVER_HOST=0.0.0.0
HTTPS_ENABLED=true
PORT=10000
```

## 📋 إعدادات محلية

### ملف `.env` (اختياري):

```env
FACEBOOK_PAGE_ID=...
FACEBOOK_ACCESS_TOKEN=...
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
APP_PASSWORD=admin

# محلي: يمكن استخدام HTTP
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/youtube/callback
TIKTOK_REDIRECT_URI=http://127.0.0.1:5000/tiktok/callback

SERVER_HOST=127.0.0.1
HTTPS_ENABLED=false
```

## 🔧 Developer Portals

### Google Cloud Console
أضف **كلا** Redirect URIs:
- `http://127.0.0.1:5000/youtube/callback` (محلي)
- `https://hhh-ftzf.onrender.com/youtube/callback` (Render)

### TikTok Developer Portal
أضف **كلا** Redirect URIs:
- `http://127.0.0.1:5000/tiktok/callback` (محلي)
- `https://hhh-ftzf.onrender.com/tiktok/callback` (Render)

## 🚀 التشغيل

### محلياً:
```powershell
.\run.ps1
```

### على Render:
1. ارفع الكود إلى GitHub
2. في Render Dashboard: Deploy
3. النظام سيكتشف البيئة تلقائياً

## 🎯 الميزات

✅ **كشف تلقائي للبيئة**
✅ **Redirect URIs تلقائية**
✅ **واجهة تعرض البيئة الحالية**
✅ **يعمل على HTTP محلياً و HTTPS على Render**

## 📝 ملاحظات

- النظام يستخدم `RENDER_EXTERNAL_URL` من Render إذا كان متاحاً
- إذا لم يكن متاحاً، يستخدم `https://hhh-ftzf.onrender.com` كافتراضي
- يمكنك تحديث الرابط في `get_base_url()` إذا تغير اسم التطبيق
