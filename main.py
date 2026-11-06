import sys
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
# استيراد كلاس تسجيل الدخول
from servo_system_v2 import MainApplication 

def main():
    # 1. يجب تفعيل OpenGL قبل إنشاء QApplication (ضروري جداً للرئة 3D)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    
    # 2. الآن ننشئ التطبيق
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    
    # 3. تشغيل شاشة تسجيل الدخول
    window = MainApplication() 
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()