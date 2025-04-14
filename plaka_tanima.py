import cv2
import torch
import numpy as np
import argparse
import time
import os
import io
import sqlite3
from PIL import Image
from collections import Counter
from ultralytics import YOLO

class SpeedDetector:
    """
    Plaka resimleri arasında hız tespiti yapmak için kullanılır
    """
    def __init__(self, fps, distance_meters=15.0, debug_mode=False):
        self.fps = fps
        self.distance_meters = distance_meters
        self.debug_mode = debug_mode
        self.plate_frames = {}  # {plate_id: [frame_number, ...]}
        self.plate_speeds = {}  # {plate_id: speed}
    
    def add_detection(self, plate_id, frame_number):
        """
        Bir plaka tespitini ekler ve eğer yeterli veri varsa hızı hesaplar
        """
        # Plaka ID'si daha önce görülmediyse yeni liste oluştur
        if plate_id not in self.plate_frames:
            self.plate_frames[plate_id] = []
        
        # Frame numarasını ekle
        self.plate_frames[plate_id].append(frame_number)
        
        # Eğer yeterli frame varsa hızı hesapla
        if len(self.plate_frames[plate_id]) >= 2:
            self.calculate_speed(plate_id)
    
    def calculate_speed(self, plate_id):
        """
        Belirli bir plaka ID'si için hızı hesaplar
        """
        frames = self.plate_frames[plate_id]
        if len(frames) < 2:
            return None
        
        # İlk ve son frame numaralarını al
        start_frame = frames[0]
        end_frame = frames[-1]
        
        # Frame farkını hesapla
        frame_diff = end_frame - start_frame
        
        # Frame farkı çok küçükse hesaplama yapma
        if frame_diff < 5:  # En az 5 frame farkı olsun
            return None
        
        # Zaman farkını hesapla (saniye cinsinden)
        time_diff = frame_diff / self.fps
        
        # Mesafenin tümünü kat ettiğini varsayarak hızı hesapla
        speed_m_s = self.distance_meters / time_diff
        speed_km_h = speed_m_s * 3.6
        
        # Aşırı yüksek hızları filtrele
        if speed_km_h > 200:  # 200 km/saat üzeri muhtemelen hatalı
            if self.debug_mode:
                print(f"Hız çok yüksek, muhtemelen hatalı: {speed_km_h:.2f} km/s")
            return None
        
        # Hızı kaydet
        self.plate_speeds[plate_id] = speed_km_h
        
        if self.debug_mode:
            print(f"Plaka {plate_id} için hız hesaplandı: {speed_km_h:.2f} km/s (frames: {start_frame}-{end_frame}, time: {time_diff:.2f}s)")
        
        return speed_km_h
    
    def get_speed(self, plate_id):
        """
        Bir plaka ID'si için kayıtlı hızı döndürür
        """
        return self.plate_speeds.get(plate_id)

class ImageDatabase:
    def __init__(self, db_name='plates.db'):
        # Veritabanı bağlantısını oluştur
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        
        # Plaka tablosunu oluştur - daha kapsamlı bilgiler eklendi
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS plates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_id TEXT,
            image BLOB,
            clarity REAL,
            confidence REAL,
            rotation INTEGER,
            capture_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            plate_text TEXT,
            speed REAL,  -- Hız bilgisi için yeni kolon
            UNIQUE(plate_text)  -- Aynı plaka metninin tekrar kaydedilmesini engelle
        )
        ''')
        
        self.conn.commit()
    
    def save_image(self, image_path, plate_id=None, clarity=0, confidence=0, rotation=0, plate_text=None, speed=None):
        """
        Plaka resmini veritabanına kaydet
        :param image_path: Resmin dosya yolu
        :param plate_id: Plaka ID (ör: PLATE001)
        :param clarity: Netlik skoru
        :param confidence: Güven değeri
        :param rotation: Rotasyon açısı
        :param plate_text: Okunan plaka metni
        :param speed: Hesaplanan hız (km/saat)
        """
        # Resmi oku
        with open(image_path, 'rb') as file:
            blob_data = file.read()
        
        try:
            # Resmi veritabanına kaydet - eğer aynı plaka metni mevcutsa, güncelle
            if plate_text:
                # Önce bu plaka metni zaten var mı kontrol et
                self.cursor.execute("SELECT id, clarity FROM plates WHERE plate_text = ?", (plate_text,))
                existing = self.cursor.fetchone()
                
                if existing and clarity <= existing[1]:
                    # Mevcut kayıt daha iyi veya eşit kalitede, kayıt yapma
                    # Ancak hız bilgisi varsa güncelle
                    if speed is not None:
                        self.cursor.execute("UPDATE plates SET speed = ? WHERE id = ?", (speed, existing[0]))
                        self.conn.commit()
                    return existing[0]
                elif existing:
                    # Mevcut kayıt var ama yeni görüntü daha net, güncelle
                    self.cursor.execute('''
                    UPDATE plates 
                    SET image = ?, clarity = ?, confidence = ?, rotation = ?, file_path = ?, speed = ?
                    WHERE plate_text = ?
                    ''', (blob_data, clarity, confidence, rotation, image_path, speed, plate_text))
                    self.conn.commit()
                    return existing[0]
                else:
                    # Yeni kayıt oluştur
                    self.cursor.execute('''
                    INSERT INTO plates (plate_id, image, clarity, confidence, rotation, file_path, plate_text, speed) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (plate_id, blob_data, clarity, confidence, rotation, image_path, plate_text, speed))
                    self.conn.commit()
                    return self.cursor.lastrowid
            else:
                # Plaka metni olmayan durumlar için eski davranışı koru
                self.cursor.execute('''
                INSERT INTO plates (plate_id, image, clarity, confidence, rotation, file_path, speed) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (plate_id, blob_data, clarity, confidence, rotation, image_path, speed))
                self.conn.commit()
                return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            # Benzersizlik kısıtlaması ihlali, kayıt eklenmedi
            # Hız bilgisi varsa güncelle
            if speed is not None and plate_text:
                self.cursor.execute("UPDATE plates SET speed = ? WHERE plate_text = ?", (speed, plate_text))
                self.conn.commit()
                
            self.cursor.execute("SELECT id FROM plates WHERE plate_text = ?", (plate_text,))
            return self.cursor.fetchone()[0]
    
    def save_cv2_image(self, cv2_image, plate_id=None, clarity=0, confidence=0, rotation=0, file_path=None, plate_text=None, speed=None):
        """
        OpenCV görüntü nesnesini doğrudan kaydet
        :param cv2_image: OpenCV görüntüsü (numpy array)
        :param plate_id: Plaka ID (ör: PLATE001)
        :param clarity: Netlik skoru
        :param confidence: Güven değeri
        :param rotation: Rotasyon açısı
        :param file_path: Disk üzerindeki dosya yolu (kaydedildiyse)
        :param plate_text: Okunan plaka metni
        :param speed: Hesaplanan hız (km/saat)
        """
        # CV2 görüntüsünü PIL'e dönüştür
        cv2_rgb = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(cv2_rgb)
        
        # Resmi bellek içi byte dizisine çevir
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        try:
            # Resmi veritabanına kaydet - eğer aynı plaka metni mevcutsa, güncelle
            if plate_text:
                # Önce bu plaka metni zaten var mı kontrol et
                self.cursor.execute("SELECT id, clarity FROM plates WHERE plate_text = ?", (plate_text,))
                existing = self.cursor.fetchone()
                
                if existing and clarity <= existing[1]:
                    # Mevcut kayıt daha iyi veya eşit kalitede, kayıt yapma
                    # Ancak hız bilgisi varsa güncelle
                    if speed is not None:
                        self.cursor.execute("UPDATE plates SET speed = ? WHERE id = ?", (speed, existing[0]))
                        self.conn.commit()
                    return existing[0]
                elif existing:
                    # Mevcut kayıt var ama yeni görüntü daha net, güncelle
                    self.cursor.execute('''
                    UPDATE plates 
                    SET image = ?, clarity = ?, confidence = ?, rotation = ?, file_path = ?, speed = ?
                    WHERE plate_text = ?
                    ''', (img_byte_arr, clarity, confidence, rotation, file_path, speed, plate_text))
                    self.conn.commit()
                    return existing[0]
                else:
                    # Yeni kayıt oluştur
                    self.cursor.execute('''
                    INSERT INTO plates (plate_id, image, clarity, confidence, rotation, file_path, plate_text, speed) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (plate_id, img_byte_arr, clarity, confidence, rotation, file_path, plate_text, speed))
                    self.conn.commit()
                    return self.cursor.lastrowid
            else:
                # Plaka için metin olmayan durumlar - otomatik plaka metni oluştur
                placeholder_text = f"PLATE_{plate_id}_{int(time.time())}"
                self.cursor.execute('''
                INSERT INTO plates (plate_id, image, clarity, confidence, rotation, file_path, plate_text, speed) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (plate_id, img_byte_arr, clarity, confidence, rotation, file_path, placeholder_text, speed))
                self.conn.commit()
                return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            # Benzersizlik kısıtlaması ihlali, kayıt eklenmedi
            # Hız bilgisi varsa güncelle
            if speed is not None and plate_text:
                self.cursor.execute("UPDATE plates SET speed = ? WHERE plate_text = ?", (speed, plate_text))
                self.conn.commit()
                
            if plate_text:
                self.cursor.execute("SELECT id FROM plates WHERE plate_text = ?", (plate_text,))
                return self.cursor.fetchone()[0]
            return None
    
    def update_speed(self, plate_id, speed):
        """
        Belirli bir plaka için hız bilgisini güncelle
        :param plate_id: Plaka ID
        :param speed: Hesaplanan hız değeri
        """
        try:
            # Plaka ID ile güncellemeyi dene
            self.cursor.execute('UPDATE plates SET speed = ? WHERE plate_id = ?', (speed, plate_id))
            
            # Değişiklik oldu mu kontrol et
            if self.cursor.rowcount == 0:
                # Plaka ID ile bulunamadıysa metin olarak da dene
                self.cursor.execute('UPDATE plates SET speed = ? WHERE plate_text = ?', (speed, plate_id))
            
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            print(f"Hız güncelleme hatası: {e}")
            return False
    
    def get_image(self, entry_id):
        """
        Belirli bir ID'ye sahip plaka resmini al
        :param entry_id: Veritabanındaki ID
        :return: PIL Image nesnesi
        """
        self.cursor.execute('SELECT image FROM plates WHERE id = ?', (entry_id,))
        image_blob = self.cursor.fetchone()
        
        if image_blob:
            # Blob veriyi PIL Image'a çevir
            return Image.open(io.BytesIO(image_blob[0]))
        return None
    
    def get_cv2_image(self, entry_id):
        """
        Belirli bir ID'ye sahip plaka resmini OpenCV formatında al
        :param entry_id: Veritabanındaki ID
        :return: OpenCV görüntüsü (numpy array)
        """
        pil_image = self.get_image(entry_id)
        if pil_image:
            # PIL Image'ı numpy array'e dönüştür
            numpy_image = np.array(pil_image)
            # RGB'den BGR'ye dönüştür (PIL -> OpenCV)
            return cv2.cvtColor(numpy_image, cv2.COLOR_RGB2BGR)
        return None
    
    def list_plates(self, limit=None):
        """
        Veritabanındaki tüm plaka kayıtlarını listele
        :param limit: Maksimum kayıt sayısı (opsiyonel)
        :return: Plaka bilgileri listesi
        """
        if limit:
            self.cursor.execute('''
            SELECT id, plate_id, clarity, confidence, rotation, capture_date, file_path, plate_text, speed
            FROM plates ORDER BY id DESC LIMIT ?
            ''', (limit,))
        else:
            self.cursor.execute('''
            SELECT id, plate_id, clarity, confidence, rotation, capture_date, file_path, plate_text, speed
            FROM plates ORDER BY id DESC
            ''')
        return self.cursor.fetchall()
    
    def delete_entry(self, entry_id):
        """
        Belirli bir kaydı sil
        :param entry_id: Silinecek kaydın ID'si
        """
        self.cursor.execute('DELETE FROM plates WHERE id = ?', (entry_id,))
        self.conn.commit()
    
    def close(self):
        """Veritabanı bağlantısını kapat"""
        self.conn.close()


def parse_arguments():
    parser = argparse.ArgumentParser(description='YOLOv8 ile plaka tespiti ve hız hesaplama')
    parser.add_argument('--model', type=str, default='best.pt', help='YOLOv8 model dosyası yolu')
    parser.add_argument('--video', type=str, required=True, help='Video dosyası yolu veya kamera indeksi (0, 1, vb.)')
    parser.add_argument('--conf', type=float, default=0.5, help='Tespit güven eşiği')
    parser.add_argument('--display', action='store_true', help='Video gösterimi aktif/pasif')
    parser.add_argument('--rotate', action='store_true', help='Görüntüyü farklı açılarda analiz et')
    parser.add_argument('--save-dir', type=str, default='plate_results', help='Sonuçların kaydedileceği dizin')
    parser.add_argument('--debug', action='store_true', help='Hata ayıklama modunda çalıştır')
    parser.add_argument('--db-name', type=str, default='plates.db', help='Veritabanı dosya adı')
    parser.add_argument('--db-only', action='store_true', help='Sadece veritabanına kaydet, dosya olarak kaydetme')
    parser.add_argument('--use-ocr', action='store_true', help='Plaka metni için OCR kullan')
    
    # Hız hesaplama için ek argümanlar
    parser.add_argument('--measure-speed', action='store_true', help='Hız ölçümü aktif/pasif')
    parser.add_argument('--distance', type=float, default=15.0, help='Ölçüm için kullanılacak mesafe (metre)')
    
    return parser.parse_args()


def calculate_clarity_score(image):
    """Görüntünün netlik skorunu hesapla (Laplacian varyans yöntemi)"""
    if image is None or image.size == 0:
        return 0
    
    # Gri tonlamaya dönüştür
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Laplacian filtresi uygula
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    
    # Varyansı hesapla - yüksek varyans daha net görüntü demektir
    score = np.var(laplacian)
    
    return score


def rotate_image(image, angle):
    """Görüntüyü belirtilen açıda döndürür"""
    # Görüntü merkezini al
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    
    # Dönüş matrisini hesapla
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    
    # Görüntüyü döndür
    rotated = cv2.warpAffine(image, rotation_matrix, (width, height), flags=cv2.INTER_LINEAR)
    
    return rotated


def calculate_image_similarity(img1, img2):
    """İki görüntü arasındaki benzerliği hesaplar"""
    # Görüntüleri aynı boyuta getir
    height = min(img1.shape[0], img2.shape[0])
    width = min(img1.shape[1], img2.shape[1])
    img1_resized = cv2.resize(img1, (width, height))
    img2_resized = cv2.resize(img2, (width, height))
    
    # Görüntüleri griye çevir
    gray1 = cv2.cvtColor(img1_resized, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2_resized, cv2.COLOR_BGR2GRAY)
    
    # MSE (Ortalama Kare Hatası) hesapla - düşük değer daha benzer demektir
    mse = np.mean((gray1 - gray2) ** 2)
    
    # Eğer MSE belirli bir eşiğin altındaysa, görüntüler benzer kabul edilir
    similarity_threshold = 500  # Daha düşük threshold değeri ile daha hassas kontrol
    return mse < similarity_threshold


# OCR fonksiyonunu ekle (isteğe bağlı)
def extract_plate_text(plate_img, debug_mode=False):
    """
    Plaka görüntüsünden metin çıkarma (OCR)
    Eğer pytesseract yüklü değilse, None döndürür.
    """
    try:
        import pytesseract
        
        # Görüntüyü ön işleme tabi tut
        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        # Plaka metnini çıkar
        config = '--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        text = pytesseract.image_to_string(gray, config=config).strip()
        
        # Boşlukları kaldır
        text = ''.join(text.split())
        
        if debug_mode:
            print(f"Okunan plaka metni: {text}")
        
        # Eğer metin çok kısa veya çok uzunsa muhtemelen hatalıdır
        if len(text) < 4 or len(text) > 15:
            return None
        
        return text
    except ImportError:
        # pytesseract yüklü değil
        if debug_mode:
            print("pytesseract kütüphanesi yüklü değil, OCR devre dışı.")
        return None
    except Exception as e:
        if debug_mode:
            print(f"OCR hatası: {e}")
        return None


def get_unique_plate_id(plate_img, existing_plates, debug_mode=False):
    """
    Görüntüye göre benzersiz bir plaka ID'si oluştur
    Mevcut plakalara benzer ise aynı ID'yi döndür
    """
    # OCR ile plaka metnini çıkarmayı dene
    plate_text = extract_plate_text(plate_img, debug_mode)
    
    # Eğer OCR ile metin bulunamazsa, görüntü benzerliği kontrol et
    if plate_text is None:
        for plate_id, plate_data in existing_plates.items():
            if calculate_image_similarity(plate_img, plate_data['image']):
                return plate_id, True, None
        
        # Benzersiz bir ID yoksa None döndür
        return None, False, None
    
    # OCR ile metin bulunduysa, bu metni kontrol et
    for plate_id, plate_data in existing_plates.items():
        # Eğer plaka metni zaten varsa
        if plate_data.get('plate_text') == plate_text:
            return plate_id, True, plate_text
    
    # Yeni bir metin ise benzersiz
    return None, False, plate_text


def run_video_detection(model_path, video_source, conf_threshold=0.5, display_video=True, 
                        enable_rotation=True, save_dir='plate_results', debug_mode=False,
                        db_name='plates.db', db_only=False, use_ocr=False,
                        measure_speed=False, distance_meters=15.0):
    # Veritabanını başlat
    db = ImageDatabase(db_name)
    print(f"Veritabanı başlatıldı: {db_name}")
    
    # Dosyaya kaydetme aktifse sonuçların kaydedileceği dizini oluştur
    if not db_only:
        os.makedirs(save_dir, exist_ok=True)
    
    # Modeli yükle
    try:
        print(f"Model yükleniyor: {model_path}")
        model = YOLO(model_path)
    except Exception as e:
        print(f"Model yüklenirken hata oluştu: {e}")
        db.close()
        return
    
    # Video kaynağını başlat
    try:
        # Eğer video_source bir sayı ise (kamera indeksi) int'e çevir
        if video_source.isdigit():
            video_source = int(video_source)
        
        print(f"Video kaynağı açılıyor: {video_source}")
        cap = cv2.VideoCapture(video_source)
        
        if not cap.isOpened():
            print("Video kaynağı açılamadı.")
            db.close()
            return
    except Exception as e:
        print(f"Video açılırken hata oluştu: {e}")
        db.close()
        return
    
    # Video özellikleri
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"Video özellikleri: {frame_width}x{frame_height} @ {fps} FPS")
    print(f"Rotasyon desteği: {'Aktif' if enable_rotation else 'Pasif'}")
    print(f"GPU kullanımı: {'Aktif' if torch.cuda.is_available() else 'Pasif'}")
    print(f"Kayıt modu: {'Sadece veritabanı' if db_only else 'Veritabanı ve dosya'}")
    print(f"OCR modu: {'Aktif' if use_ocr else 'Pasif'}")
    print(f"Hız ölçümü: {'Aktif' if measure_speed else 'Pasif'}")
    
    # Hız dedektörünü başlat
    speed_detector = None
    if measure_speed:
        speed_detector = SpeedDetector(fps, distance_meters, debug_mode)
        print(f"Hız dedektörü başlatıldı: Mesafe={distance_meters}m")
    
    # Her plaka için bulunan en iyi görüntüleri ve skorları sakla
    plate_detections = []
    
    # Benzersiz plakaları ve en net görüntülerini saklayacak sözlük
    unique_plates = {}  # {plate_id: {'image': best_image, 'clarity': best_clarity, 'conf': best_conf, 'path': file_path, 'plate_text': ocr_text, 'speed': speed}}
    
    # Performans ölçümü için değişkenler
    frame_count = 0
    start_time = time.time()
    
    # Netlik/güven eşik değerleri - bu değerler altındaki görüntüler kaydedilmeyecek
    MIN_CLARITY_THRESHOLD = 100  # Minimum netlik skoru
    MIN_CONFIDENCE_THRESHOLD = 0.55  # Minimum güven skoru
    
    # Plaka ID sayacı
    plate_id_counter = 1
    
    # Plaka görüntüsünü kaydet
    def save_plate_image(plate_img, clarity, conf, rotation_angle=0, current_frame=0):
        nonlocal plate_id_counter
        
        # Plaka görüntüsünün benzersiz ID'sini kontrol et (görüntü benzerliği veya OCR ile)
        existing_id, is_duplicate, plate_text = get_unique_plate_id(plate_img, unique_plates, debug_mode)
        
        # Eğer OCR kullanılıyorsa ve metin bulunamazsa, None olarak işaretle
        if use_ocr and plate_text is None:
            plate_text = f"UNKNOWN_{plate_id_counter}"
        
        # Hız değerini al
        speed = None
        if measure_speed and speed_detector:
            # Mevcut plaka için hız dedektörünü güncelle
            plate_id_for_speed = existing_id if existing_id else f"PLATE{plate_id_counter:03d}"
            speed_detector.add_detection(plate_id_for_speed, current_frame)
            speed = speed_detector.get_speed(plate_id_for_speed)
            
            if debug_mode and speed is not None:
                print(f"Hız hesaplandı: Plaka {plate_id_for_speed} -> {speed:.2f} km/s")
        
        # Benzer görüntü kontrolü
        if is_duplicate and existing_id:
            # Eğer yeni görüntü daha netse, güncelle
            if clarity > unique_plates[existing_id]['clarity']:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                ms = int((time.time() % 1) * 1000)
                
                # Dosya olarak kaydetme seçeneğine göre işlem yap
                plate_filename = None
                if not db_only:
                    plate_filename = f"{save_dir}/plate_{existing_id}_{timestamp}_{ms}_{clarity:.0f}_{int(conf*100)}.jpg"
                    cv2.imwrite(plate_filename, plate_img)
                    
                    # Eski dosyayı sil (isteğe bağlı)
                    if os.path.exists(unique_plates[existing_id].get('path', '')):
                        try:
                            os.remove(unique_plates[existing_id]['path'])
                        except:
                            pass
                
                # Veritabanına kaydet
                db.save_cv2_image(plate_img, existing_id, clarity, conf, rotation_angle, plate_filename, plate_text, speed)
                
                # Plaka verilerini güncelle
                unique_plates[existing_id] = {
                    'image': plate_img.copy(),
                    'clarity': clarity,
                    'conf': conf,
                    'path': plate_filename,
                    'id': existing_id,
                    'rotation': rotation_angle,
                    'plate_text': plate_text,
                    'speed': speed
                }
                
                if debug_mode:
                    print(f"Plaka {existing_id} daha net bir görüntü ile güncellendi: {plate_filename if plate_filename else 'sadece DB'}")
            elif speed is not None and speed != unique_plates[existing_id].get('speed'):
                # Sadece hız bilgisini güncelle
                unique_plates[existing_id]['speed'] = speed
                db.update_speed(existing_id, speed)
                if debug_mode:
                    print(f"Plaka {existing_id} için hız güncellendi: {speed:.2f} km/s")
            
            return existing_id, True
        
        # Yeni bir plaka ise
        plate_id = f"PLATE{plate_id_counter:03d}"
        plate_id_counter += 1
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        ms = int((time.time() % 1) * 1000)
        
        # Dosya olarak kaydetme seçeneğine göre işlem yap
        plate_filename = None
        if not db_only:
            plate_filename = f"{save_dir}/plate_{plate_id}_{timestamp}_{ms}_{clarity:.0f}_{int(conf*100)}.jpg"
            cv2.imwrite(plate_filename, plate_img)
        
        # Veritabanına kaydet
        db.save_cv2_image(plate_img, plate_id, clarity, conf, rotation_angle, plate_filename, plate_text, speed)
        
        # Plaka sözlüğünü güncelle
        unique_plates[plate_id] = {
            'image': plate_img.copy(),
            'clarity': clarity,
            'conf': conf,
            'path': plate_filename,
            'id': plate_id,
            'rotation': rotation_angle,
            'plate_text': plate_text,
            'speed': speed
        }
        
        if debug_mode:
            print(f"Yeni plaka görüntüsü kaydedildi: {plate_filename if plate_filename else 'sadece DB'}")
        
        return plate_id, False
    
    # Frame sayacı
    frame_num = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("Video sonu veya hata!")
            break
        
        # Frame sayacını artır
        frame_num += 1
        
        # FPS hesapla ve göster
        frame_count += 1
        elapsed_time = time.time() - start_time
        if elapsed_time >= 1:  # Her saniyede bir FPS güncelle
            current_fps = frame_count / elapsed_time
            print(f"İşleme hızı: {current_fps:.2f} FPS")
            frame_count = 0
            start_time = time.time()
        
        # Orijinal görüntüde ve döndürülmüş görüntülerde tespit yap
        results_original = model(frame, conf=conf_threshold, verbose=False)[0]
        
        # Rotasyon desteği aktifse, yatay plakalar için döndürülmüş görüntülerde de tespit yap
        rotated_results = []
        if enable_rotation:
            rotations = [90, -90, 180]  # Dönüş açıları
            for angle in rotations:
                rotated_frame = rotate_image(frame.copy(), angle)
                result = model(rotated_frame, conf=conf_threshold, verbose=False)[0]
                rotated_results.append((result, angle, rotated_frame))
        
        detected_something = False
        display_frame = frame.copy()
        frame_detections = []  # Bu karede tespit edilen tüm olası plakalar
        
        # Tespit işleme fonksiyonu
        def process_detections(detections, frame_to_process, is_rotated=False, rotation_angle=0):
            nonlocal detected_something
            processed_results = []
            
            for detection in detections.boxes.data.tolist():
                x1, y1, x2, y2, conf, cls = detection
                
                if conf < conf_threshold:
                    continue
                
                detected_something = True
                
                # Koordinatları integer'a çevir
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                
                # Geçerli bir bölge olduğunu kontrol et
                if x1 >= x2 or y1 >= y2 or x1 < 0 or y1 < 0 or x2 >= frame.shape[1] or y2 >= frame.shape[0]:
                    continue
                
                # Tespit edilen bölgeyi kırp
                if is_rotated:
                    # Döndürülmüş görüntüden plakayı kırp
                    try:
                        plate_img = frame_to_process[y1:y2, x1:x2]
                    except:
                        continue
                else:
                    plate_img = frame[y1:y2, x1:x2]
                
                # Görüntünün netlik skorunu hesapla
                clarity_score = calculate_clarity_score(plate_img)
                
                # Netlik/güven eşik değerlerini geçen plakaları kaydet
                if conf >= MIN_CONFIDENCE_THRESHOLD and clarity_score >= MIN_CLARITY_THRESHOLD:
                    plate_id, is_duplicate = save_plate_image(plate_img, clarity_score, conf, rotation_angle, frame_num)
                    
                    # Sonuçları kaydet
                    plate_info = {
                        'id': plate_id,
                        'conf': conf,
                        'clarity': clarity_score,
                        'coords': (x1, y1, x2, y2),
                        'rotation': rotation_angle,
                        'is_rotated': is_rotated,
                        'image': plate_img.copy(),
                        'is_duplicate': is_duplicate
                    }
                    processed_results.append(plate_info)
            
            return processed_results
        
        # Orijinal ve döndürülmüş görüntülerde tespitleri yap
        original_processed = process_detections(results_original, frame)
        frame_detections.extend(original_processed)
        
        # Rotasyon aktifse, döndürülmüş görüntülerdeki tespitleri işle
        if enable_rotation:
            for result, angle, rotated_frame in rotated_results:
                rotated_processed = process_detections(result, rotated_frame, is_rotated=True, rotation_angle=angle)
                
                # Döndürülmüş görüntüdeki koordinatları orijinal görüntüye çevir
                for item in rotated_processed:
                    x1, y1, x2, y2 = item['coords']
                    h, w = frame.shape[:2]
                    
                    if angle == 90:
                        # 90 derece döndürülmüş görüntüdeki koordinatları orijinal görüntüye çevir
                        new_x1 = y1
                        new_y1 = w - x2
                        new_x2 = y2
                        new_y2 = w - x1
                    elif angle == -90:
                        # -90 derece döndürülmüş görüntüdeki koordinatları orijinal görüntüye çevir
                        new_x1 = h - y2
                        new_y1 = x1
                        new_x2 = h - y1
                        new_y2 = x2
                    elif angle == 180:
                        # 180 derece döndürülmüş görüntüdeki koordinatları orijinal görüntüye çevir
                        new_x1 = w - x2
                        new_y1 = h - y2
                        new_x2 = w - x1
                        new_y2 = h - y1
                    else:
                        continue
                    
                    # Sınırları kontrol et
                    new_x1 = max(0, min(w-1, int(new_x1)))
                    new_y1 = max(0, min(h-1, int(new_y1)))
                    new_x2 = max(0, min(w-1, int(new_x2)))
                    new_y2 = max(0, min(h-1, int(new_y2)))
                    
                    item['coords'] = (new_x1, new_y1, new_x2, new_y2)
                
                frame_detections.extend(rotated_processed)
        
        # Tüm detections'ı ekle
        plate_detections.extend(frame_detections)
        
        # Bu karede tespit edilen plakalar için tespitleri göster
        for detection in frame_detections:
            if detection.get('is_duplicate', False):
                continue  # Duplike plakaları gösterme
                
            plate_id = detection['id']
            x1, y1, x2, y2 = detection['coords']
            conf = detection['conf']
            clarity = detection['clarity']
            rotation = detection['rotation']
            
            # Görüntüde tespit kutusunu çiz
            color = (0, 255, 0)  # Yeşil: orijinal görüntüde tespit
            if detection['is_rotated']:
                if rotation == 90 or rotation == -90:
                    color = (0, 0, 255)  # Kırmızı: yatay döndürülmüş görüntüde tespit
                else:
                    color = (255, 0, 0)  # Mavi: 180 derece döndürülmüş görüntüde tespit
            
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
            
            # Plaka metni ve hız bilgisini göster
            plate_text = unique_plates[plate_id].get('plate_text')
            speed = unique_plates[plate_id].get('speed')
            
            # Etiket metni oluştur
            label = ""
            if plate_text and not str(plate_text).startswith("UNKNOWN_"):
                label = f"ID: {plate_id}, {plate_text}, C:{clarity:.0f}, ({conf:.2f})"
            else:
                label = f"ID: {plate_id}, C:{clarity:.0f}, ({conf:.2f})"
                
            # Hız bilgisi varsa ekle
            if speed is not None:
                label += f", {speed:.1f} km/s"
                
            cv2.putText(display_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # Debug modda tespit bilgilerini yazdır
            if debug_mode:
                source_info = f"(Rot: {rotation}°, Netlik: {clarity:.2f})" if rotation != 0 else f"(Netlik: {clarity:.2f})"
                speed_info = f", Hız: {speed:.2f} km/s" if speed is not None else ""
                print(f"[{time.strftime('%H:%M:%S')}] Tespit: ID {plate_id} (Güven: {conf:.2f}) {source_info}{speed_info}")
        
        if not detected_something:
            cv2.putText(display_frame, "Plaka tespit edilemedi", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Şu ana kadar kaydedilen plaka sayısını göster
        cv2.putText(display_frame, f"Benzersiz plaka sayısı: {len(unique_plates)}", (20, 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Hız ölçüm bilgisini göster
        if measure_speed:
            cv2.putText(display_frame, f"Hız ölçüm mesafesi: {distance_meters}m", (20, 80), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Video göster
        if display_video:
            # Rotasyon durumunu ekranda göster
            rot_y_pos = 120
            if enable_rotation:
                cv2.putText(display_frame, "Rotasyon: AÇIK", (20, rot_y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            else:
                cv2.putText(display_frame, "Rotasyon: KAPALI", (20, rot_y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
            cv2.imshow("Plaka Tespiti", display_frame)
            
            # 'q' tuşuna basarak çık, 'r' tuşu ile rotasyonu aç/kapa
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                enable_rotation = not enable_rotation
                print(f"Rotasyon {'açıldı' if enable_rotation else 'kapatıldı'}")
            elif key == ord('c'):
                # Manuel olarak mevcut tespitleri temizle ve yeniden başla
                plate_detections = []
                print("Tespitler temizlendi, yeniden başlatılıyor...")
    
    # Kaynakları serbest bırak
    cap.release()
    if display_video:
        cv2.destroyAllWindows()

    # Sonuçları terminal ekranında göster
    print("\n" + "="*70)
    print("TESPIT EDILEN PLAKALAR")
    print("="*70)
    
    # Veritabanındaki son plaka kayıtlarını listele
    db_plates = db.list_plates(10)  # Son 10 plakayı getir
    print(f"Veritabanında toplam {len(db.list_plates())} plaka kaydı bulunuyor.")
    print(f"Son 10 plaka kaydı:")
    
    for plate in db_plates:
        plate_id = plate[1]      # plate_id
        clarity = plate[2]       # clarity
        conf = plate[3]          # confidence
        rotation = plate[4]      # rotation
        date = plate[5]          # capture_date
        file_path = plate[6]     # file_path
        plate_text = plate[7] if len(plate) > 7 else "Bilinmiyor"  # plate_text
        speed = plate[8] if len(plate) > 8 and plate[8] is not None else None  # speed
        
        print(f"Plaka ID: {plate_id}")
        print(f"Plaka Metni: {plate_text}")
        print(f"Netlik: {clarity:.2f}")
        print(f"Güven: {conf:.2f}")
        print(f"Rotasyon: {rotation}°")
        if speed is not None:
            print(f"Hız: {speed:.2f} km/s")
        else:
            print("Hız: Hesaplanamadı")
        print(f"Tarih: {date}")
        if file_path:
            print(f"Dosya: {os.path.basename(file_path)}")
        print("-" * 50)
    
    # Veritabanı bağlantısını kapat
    db.close()
    print("Veritabanı bağlantısı kapatıldı.")
    print("\nVideo işleme tamamlandı.")
    
    return unique_plates


if __name__ == "__main__":
    try:
        args = parse_arguments()
        
        # Video kaynağını belirle
        video_source = args.video
        
        # Model yolu
        model_path = args.model
        
        # Tespit eşiği
        confidence_threshold = args.conf
        
        # Video gösterimi
        display_video = args.display
        
        # Rotasyon desteği
        enable_rotation = args.rotate
        
        # Görüntülerin kaydedileceği dizin
        save_dir = args.save_dir
        
        # Hata ayıklama modu
        debug_mode = args.debug
        
        # Veritabanı adı
        db_name = args.db_name
        
        # Sadece veritabanına kaydet
        db_only = args.db_only
        
        # OCR kullan
        use_ocr = args.use_ocr
        
        # Hız ölçümü
        measure_speed = args.measure_speed
        distance_meters = args.distance
        
        # Plaka tespitini başlat
        run_video_detection(model_path, video_source, confidence_threshold, display_video, 
                           enable_rotation, save_dir, debug_mode, db_name, db_only, use_ocr,
                           measure_speed, distance_meters)
    except Exception as e:
        import traceback
        print(f"HATA: {e}")
        traceback.print_exc()