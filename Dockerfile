FROM python:3.10-slim

WORKDIR /app

# لو عندك ملف requirements.txt انسخه وثبته
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# انسخ كل ملفات البوت والواجهة جوه الحاوية
COPY . .

# هنا بنفتح البورت بتاع واجهة الأدمن (مثلاً بورت 8080)
EXPOSE 8080

# أمر تشغيل البوت أو الواجهة (اكتب اسم الملف الرئيسي بتاعك مكان main.py)
CMD ["python", "main.py"]
