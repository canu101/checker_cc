# استخدام نسخة بايثون خفيفة ومستقرة
FROM python:3.10-slim

# تحديد فولدر العمل داخل السيرفر
WORKDIR /app

# نسخ ملف المكتبات أولاً لتسريع الـ Build
COPY requirements.txt .

# تثبيت مكتبات بايثون
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات البوت للسيرفر
COPY . .

# أمر تشغيل الملف الرئيسي للبوت
CMD ["python", "main.py"]
