import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import io
import os
import cv2
import numpy as np
from PIL import Image, ImageTk
import threading
import time
import datetime

class ThemeColors:
    """SecureDrive theme colors for consistent UI styling"""
    PRIMARY = "#0F2C59"      # Koyu lacivert - ana tema rengi
    SECONDARY = "#164B78"    # Orta lacivert - ikincil bileşenler için
    ACCENT = "#2E7EB8"       # Açık mavi - vurgu öğeleri için
    TEXT_LIGHT = "#F8F9FA"   # Saf beyaza yakın - koyu arka planlardaki metin
    TEXT_DARK = "#212529"    # Yumuşak siyah - ana metin rengi
    SUCCESS = "#28A745"      # Belirgin ama rahatsız etmeyen yeşil
    WARNING = "#FFC107"      # Standart uyarı sarısı
    ERROR = "#DC3545"        # Standart hata kırmızısı
    BACKGROUND = "#F0F2F5"   # Hafif gri-mavi arka plan tonu

class PlateDetectionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SecureDrive")
        self.root.geometry("1200x800")
        self.root.minsize(900, 700)
        
        # Set theme colors
        self.colors = ThemeColors
        
        # Customize the ttk style for a professional look
        self.setup_styles()
        
        # Veritabanı bağlantısı
        self.conn = None
        self.db_path = None
        
        # Görüntü önbelleği
        self.image_cache = {}
        
        # Son seçilen plaka ID
        self.selected_plate_id = None
        
        # Filtre ayarları
        self.max_plates = 5  # Gösterilecek maksimum plaka sayısı - artırıldı
        self.min_confidence = 0.7  # Minimum güven değeri
        
        # Arayüzü oluştur
        self.create_gui()
        
        # Varsayılan veritabanı
        default_db = 'plates.db'
        if os.path.exists(default_db):
            self.connect_database(default_db)
    
    def setup_styles(self):
        """Set up ttk styles for a professional look"""
        style = ttk.Style()
        
        # Configure the main theme
        style.configure("TFrame", background=self.colors.BACKGROUND)
        style.configure("TLabel", background=self.colors.BACKGROUND, foreground=self.colors.TEXT_DARK)
        style.configure("TLabelframe", background=self.colors.BACKGROUND)
        style.configure("TLabelframe.Label", background=self.colors.BACKGROUND, foreground=self.colors.TEXT_DARK, font=("Segoe UI", 10, "bold"))
        
        # Custom buttons
        style.configure("Primary.TButton", 
                        background=self.colors.PRIMARY, 
                        foreground=self.colors.TEXT_LIGHT,
                        font=("Segoe UI", 9))
        
        style.configure("Secondary.TButton", 
                        background=self.colors.SECONDARY, 
                        foreground=self.colors.TEXT_LIGHT,
                        font=("Segoe UI", 9))
        
        style.configure("Accent.TButton", 
                        background=self.colors.ACCENT, 
                        foreground=self.colors.TEXT_LIGHT,
                        font=("Segoe UI", 9))
        
        style.configure("Warning.TButton", 
                        background=self.colors.WARNING, 
                        foreground=self.colors.TEXT_DARK,
                        font=("Segoe UI", 9))
        
        style.configure("Error.TButton", 
                        background=self.colors.ERROR, 
                        foreground=self.colors.TEXT_LIGHT,
                        font=("Segoe UI", 9))
        
        # Custom heading
        style.configure("Heading.TLabel", 
                        font=("Segoe UI", 16, "bold"), 
                        foreground=self.colors.PRIMARY,
                        background=self.colors.BACKGROUND)
        
        # Status bar
        style.configure("Status.TLabel", 
                        background="#dcdde1", 
                        foreground=self.colors.TEXT_DARK,
                        relief=tk.SUNKEN)
        
        # Info labels
        style.configure("Info.TLabel", 
                        font=("Segoe UI", 10),
                        background=self.colors.BACKGROUND)
        
        # Info heading
        style.configure("InfoHeading.TLabel", 
                        font=("Segoe UI", 10, "bold"),
                        background=self.colors.BACKGROUND)
        
        # Treeview
        style.configure("Treeview", 
                        background="white", 
                        foreground=self.colors.TEXT_DARK,
                        rowheight=25,
                        fieldbackground="white",
                        font=("Segoe UI", 9))
        
        style.configure("Treeview.Heading", 
                        font=("Segoe UI", 10, "bold"),
                        background=self.colors.PRIMARY,
                        foreground=self.colors.TEXT_LIGHT)
        
        # Map
        style.map("Treeview", 
                 background=[("selected", self.colors.ACCENT)],
                 foreground=[("selected", self.colors.TEXT_LIGHT)])
        
    def create_gui(self):
        # Ana çerçeve
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Company banner with logo at the top
        self.create_header(main_frame)
        
        # Üst kontrol paneli
        control_frame = ttk.LabelFrame(main_frame, text="Kontrol Paneli", padding="8")
        control_frame.pack(fill=tk.X, pady=10)
        
        # İlk satır
        control_row1 = ttk.Frame(control_frame)
        control_row1.pack(fill=tk.X, expand=True, pady=5)
        
        # Veritabanı seçme düğmesi
        ttk.Button(control_row1, text="Veritabanı Aç", style="Primary.TButton", 
                   command=self.open_database).pack(side=tk.LEFT, padx=5)
        
        # Veritabanı bilgisi
        self.db_label = ttk.Label(control_row1, text="Veritabanı: Bağlantı yok", style="Info.TLabel")
        self.db_label.pack(side=tk.LEFT, padx=5)
        
        # İkinci satır
        control_row2 = ttk.Frame(control_frame)
        control_row2.pack(fill=tk.X, expand=True, pady=5)
        
        # Filtre ayarları
        ttk.Label(control_row2, text="Gösterilecek Plaka Sayısı:", style="Info.TLabel").pack(side=tk.LEFT, padx=5)
        self.max_plates_var = tk.IntVar(value=self.max_plates)
        max_plates_spinbox = ttk.Spinbox(control_row2, from_=1, to=100, width=5, textvariable=self.max_plates_var)
        max_plates_spinbox.pack(side=tk.LEFT, padx=5)
        max_plates_spinbox.bind("<Return>", lambda e: self.update_filters())
        
        ttk.Label(control_row2, text="Min. Güven Skoru:", style="Info.TLabel").pack(side=tk.LEFT, padx=5)
        self.min_confidence_var = tk.DoubleVar(value=self.min_confidence)
        confidence_spinbox = ttk.Spinbox(control_row2, from_=0.0, to=1.0, increment=0.05, width=5, 
                                         textvariable=self.min_confidence_var, format="%.2f")
        confidence_spinbox.pack(side=tk.LEFT, padx=5)
        confidence_spinbox.bind("<Return>", lambda e: self.update_filters())
        
        # Yenile düğmesi
        ttk.Button(control_row2, text="Filtre Uygula", style="Secondary.TButton", 
                   command=self.update_filters).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_row2, text="Listeyi Yenile", style="Accent.TButton", 
                   command=self.refresh_plate_list).pack(side=tk.RIGHT, padx=5)
        
        # Ana içerik bölümü - iki panele böl
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Sol panel - plaka listesi
        list_frame = ttk.LabelFrame(content_frame, text="Plaka Listesi", padding="8")
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10), pady=5, ipadx=5, ipady=5)
        list_frame.config(width=350)  # Minimum genişlik
        
        # Arama kutusu
        search_frame = ttk.Frame(list_frame)
        search_frame.pack(fill=tk.X, pady=8)
        
        ttk.Label(search_frame, text="Plaka Ara:", style="InfoHeading.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda name, index, mode: self.filter_plate_list())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=("Segoe UI", 10))
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Plaka listesi
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Treeview için scrollbar
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Plaka listesi treeview
        self.plate_tree = ttk.Treeview(list_container, columns=("id", "plate_id", "date", "clarity", "conf"), 
                                        show="headings", selectmode="browse", style="Treeview")
        
        # Sütun başlıkları
        self.plate_tree.heading("id", text="ID")
        self.plate_tree.heading("plate_id", text="Plaka")
        self.plate_tree.heading("date", text="Tarih")
        self.plate_tree.heading("clarity", text="Netlik")
        self.plate_tree.heading("conf", text="Güven")
        
        # Sütun genişlikleri
        self.plate_tree.column("id", width=50, anchor=tk.CENTER)
        self.plate_tree.column("plate_id", width=100)
        self.plate_tree.column("date", width=130)
        self.plate_tree.column("clarity", width=70, anchor=tk.CENTER)
        self.plate_tree.column("conf", width=70, anchor=tk.CENTER)
        
        # Scrollbar bağlantısı
        self.plate_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=self.plate_tree.yview)
        
        # Treeview'e tıklama olayı
        self.plate_tree.bind("<<TreeviewSelect>>", self.on_plate_select)
        
        # Treeview'i paketleme
        self.plate_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Sağ panel - plaka detayları
        details_frame = ttk.LabelFrame(content_frame, text="Plaka Detayları", padding="8")
        details_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, pady=5)
        
        # Bilgi alanı
        info_frame = ttk.Frame(details_frame)
        info_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # Bilgi grid düzeni
        info_grid = ttk.Frame(info_frame)
        info_grid.pack(fill=tk.X, expand=True)
        
        # İki sütunlu düzen
        left_info = ttk.Frame(info_grid)
        left_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        right_info = ttk.Frame(info_grid)
        right_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # Sol kolon bilgileri
        ttk.Label(left_info, text="Plaka No:", style="InfoHeading.TLabel").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.info_plate_id = ttk.Label(left_info, text="-", style="Info.TLabel")
        self.info_plate_id.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(left_info, text="Tarih:", style="InfoHeading.TLabel").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.info_date = ttk.Label(left_info, text="-", style="Info.TLabel")
        self.info_date.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(left_info, text="Veritabanı ID:", style="InfoHeading.TLabel").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        self.info_id = ttk.Label(left_info, text="-", style="Info.TLabel")
        self.info_id.grid(row=2, column=1, sticky=tk.W, padx=5, pady=3)
        
        # Sağ kolon bilgileri
        ttk.Label(right_info, text="Güven:", style="InfoHeading.TLabel").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.info_conf = ttk.Label(right_info, text="-", style="Info.TLabel")
        self.info_conf.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(right_info, text="Netlik:", style="InfoHeading.TLabel").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.info_clarity = ttk.Label(right_info, text="-", style="Info.TLabel")
        self.info_clarity.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(right_info, text="Rotasyon:", style="InfoHeading.TLabel").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        self.info_rotation = ttk.Label(right_info, text="-", style="Info.TLabel")
        self.info_rotation.grid(row=2, column=1, sticky=tk.W, padx=5, pady=3)
        
        # Dosya yolu
        file_info = ttk.Frame(info_frame)
        file_info.pack(fill=tk.X, expand=True, pady=5, padx=5)
        
        ttk.Label(file_info, text="Dosya Yolu:", style="InfoHeading.TLabel").pack(side=tk.LEFT, padx=5)
        self.info_path = ttk.Label(file_info, text="-", style="Info.TLabel")
        self.info_path.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Görüntü alanının çevresi
        image_container = ttk.Frame(details_frame, style="TFrame")
        image_container.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        
        # Görüntü alanı
        self.image_frame = ttk.Frame(image_container, style="TFrame", relief=tk.SUNKEN, borderwidth=1)
        self.image_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Görüntü etiketi
        self.image_label = ttk.Label(self.image_frame, text="Plaka seçilmedi")
        self.image_label.pack(fill=tk.BOTH, expand=True)
        
        # Alt panel - işlem düğmeleri
        button_frame = ttk.Frame(details_frame)
        button_frame.pack(fill=tk.X, pady=10, padx=5)
        
        ttk.Button(button_frame, text="Plaka Görüntüsünü Dışa Aktar", style="Secondary.TButton", 
                   command=self.export_plate_image).pack(side=tk.LEFT, padx=5)
                   
        ttk.Button(button_frame, text="Büyüt", style="Accent.TButton",
                   command=self.show_large_image).pack(side=tk.LEFT, padx=5)
                   
        ttk.Button(button_frame, text="Plakayı Sil", style="Error.TButton", 
                   command=self.delete_plate).pack(side=tk.RIGHT, padx=5)
        
        # Durum çubuğu
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_var = tk.StringVar()
        self.status_var.set("Hazır")
        status_bar = ttk.Label(status_frame, textvariable=self.status_var, style="Status.TLabel", anchor=tk.W)
        status_bar.pack(fill=tk.X, ipady=3)
        
        # Footer with company info
        self.create_footer(main_frame)
    
    def create_header(self, parent):
        """Create a header with company logo and name"""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create a canvas for the header background
        header_canvas = tk.Canvas(header_frame, height=60, bg=self.colors.PRIMARY, highlightthickness=0)
        header_canvas.pack(fill=tk.X)
        
        # Add company name as text
        header_canvas.create_text(20, 30, text="SecureDrive", anchor=tk.W, 
                                 font=("Segoe UI", 22, "bold"), fill=self.colors.TEXT_LIGHT)
        
        # Add tagline
        header_canvas.create_text(220, 32, text="Plaka Tespit Sistemi", anchor=tk.W, 
                                 font=("Segoe UI", 15), fill=self.colors.TEXT_LIGHT)
        
        # Add current date/time on the right
        self.time_text = header_canvas.create_text(header_canvas.winfo_reqwidth()+280, 30, 
                                                  anchor=tk.E, font=("Segoe UI", 15), 
                                                  fill=self.colors.TEXT_LIGHT)
        
        # Update time every second
        self.update_time(header_canvas)
    
    def update_time(self, canvas):
        """Update the time display in the header"""
        current_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        canvas.itemconfig(self.time_text, text=current_time)
        self.root.after(1000, lambda: self.update_time(canvas))
    
    def create_footer(self, parent):
        """Create a footer with company information"""
        footer_frame = ttk.Frame(parent)
        footer_frame.pack(fill=tk.X, pady=(5, 0))
        
        footer_text = "© 2025 SecureDrive Güvenlik Sistemleri | Tüm Hakları Saklıdır"
        footer_label = ttk.Label(footer_frame, text=footer_text, 
                                 foreground=self.colors.TEXT_DARK, font=("Segoe UI", 8))
        footer_label.pack(side=tk.RIGHT, padx=5)
    
    def update_filters(self):
        """Filtre ayarlarını güncelle ve listeyi yenile"""
        try:
            self.max_plates = self.max_plates_var.get()
            self.min_confidence = self.min_confidence_var.get()
            self.refresh_plate_list()
        except Exception as e:
            messagebox.showerror("Filtre Hatası", str(e))
    
    def open_database(self):
        """Veritabanı dosyası seç ve bağlan"""
        db_path = filedialog.askopenfilename(
            title="Veritabanı Dosyası Seç",
            filetypes=[("SQLite Veritabanı", "*.db"), ("Tüm Dosyalar", "*.*")]
        )
        
        if db_path:
            self.connect_database(db_path)
    
    def connect_database(self, db_path):
        """Veritabanına bağlan"""
        try:
            # Eski bağlantıyı kapat
            if self.conn:
                self.conn.close()
            
            # Yeni bağlantı oluştur
            self.conn = sqlite3.connect(db_path)
            self.db_path = db_path
            
            # Bağlantıyı doğrula
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='plates'")
            if not cursor.fetchone():
                messagebox.showerror("Hata", "Seçilen dosya geçerli bir plaka veritabanı değil!")
                self.conn.close()
                self.conn = None
                self.db_path = None
                self.db_label.config(text="Veritabanı: Bağlantı yok")
                return False
            
            # Toplam kayıt sayısını göster
            cursor.execute("SELECT COUNT(*) FROM plates")
            total_count = cursor.fetchone()[0]
            
            # Bağlantı bilgisini güncelle
            self.db_label.config(text=f"Veritabanı: {os.path.basename(db_path)} ({total_count} kayıt)")
            
            # Plaka listesini yenile
            self.refresh_plate_list()
            return True
            
        except Exception as e:
            messagebox.showerror("Bağlantı Hatası", str(e))
            self.conn = None
            self.db_path = None
            self.db_label.config(text="Veritabanı: Bağlantı yok")
            return False
    
    def refresh_plate_list(self):
        """Plaka listesini yenile - belirtilen sayıda en yüksek güven değerine sahip plakaları göster"""
        if not self.conn:
            messagebox.showinfo("Bilgi", "Önce bir veritabanı açın!")
            return
        
        # Eski kayıtları temizle
        for item in self.plate_tree.get_children():
            self.plate_tree.delete(item)
        
        try:
            # Tabloyu sorgula
            cursor = self.conn.cursor()
            
            # Sütunları kontrol et
            cursor.execute("PRAGMA table_info(plates)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Sorguyu sütunlara göre oluştur
            query = "SELECT id, plate_id"
            
            # İsteğe bağlı sütunlar
            if "clarity" in columns:
                query += ", clarity"
            else:
                query += ", 0 as clarity"
                
            if "confidence" in columns:
                query += ", confidence"
            else:
                query += ", 0 as confidence"
                
            if "rotation" in columns:
                query += ", rotation"
            else:
                query += ", 0 as rotation"
                
            if "capture_date" in columns:
                query += ", capture_date"
            else:
                query += ", NULL as capture_date"
                
            if "file_path" in columns:
                query += ", file_path"
            else:
                query += ", NULL as file_path"
            
            # En yüksek güvenirliğe sahip plakaları göster
            query += f" FROM plates WHERE confidence >= {self.min_confidence} ORDER BY confidence DESC LIMIT {self.max_plates}"
            
            cursor.execute(query)
            plates = cursor.fetchall()
            
            # Verileri tree view'e ekle
            for i, plate in enumerate(plates):
                plate_id = plate[0]
                plate_name = plate[1]
                clarity = plate[2] if plate[2] is not None else 0
                conf = plate[3] if plate[3] is not None else 0
                date = plate[5] if len(plate) > 5 and plate[5] else "Bilinmiyor"
                
                # Alternatif satır renklendirmesi için etiket
                tag = "even" if i % 2 == 0 else "odd"
                
                self.plate_tree.insert("", tk.END, values=(
                    plate_id, plate_name, date, f"{clarity:.1f}", f"{conf:.2f}"
                ), tags=(tag,))
            
            # Satır renklerini ayarla
            self.plate_tree.tag_configure("even", background="#f0f0f0")
            self.plate_tree.tag_configure("odd", background="white")
            
            self.status_var.set(f"En yüksek güven değerine sahip {len(plates)} plaka gösteriliyor")
            
            # İlk plakayı otomatik seç
            if self.plate_tree.get_children():
                first_item = self.plate_tree.get_children()[0]
                self.plate_tree.selection_set(first_item)
                self.plate_tree.focus(first_item)
                self.on_plate_select(None)  # Seçimi işle
            
        except Exception as e:
            messagebox.showerror("Sorgulama Hatası", str(e))
            self.status_var.set("Hata: Plaka listesi yüklenemedi")
    
    def filter_plate_list(self):
        """Arama kutusuna göre plaka listesini filtrele"""
        search_text = self.search_var.get().lower()
        
        # Eski kayıtları temizle
        for item in self.plate_tree.get_children():
            self.plate_tree.delete(item)
        
        if not self.conn:
            return
        
        try:
            # Tabloyu sorgula
            cursor = self.conn.cursor()
            
            # Sütunları kontrol et
            cursor.execute("PRAGMA table_info(plates)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Sorguyu sütunlara göre oluştur
            query = "SELECT id, plate_id"
            
            # İsteğe bağlı sütunlar
            if "clarity" in columns:
                query += ", clarity"
            else:
                query += ", 0 as clarity"
                
            if "confidence" in columns:
                query += ", confidence"
            else:
                query += ", 0 as confidence"
                
            if "rotation" in columns:
                query += ", rotation"
            else:
                query += ", 0 as rotation"
                
            if "capture_date" in columns:
                query += ", capture_date"
            else:
                query += ", NULL as capture_date"
                
            if "file_path" in columns:
                query += ", file_path"
            else:
                query += ", NULL as file_path"
            
            # Arama metnine göre filtrele
            if search_text:
                query += f" FROM plates WHERE LOWER(plate_id) LIKE '%{search_text}%' AND confidence >= {self.min_confidence} ORDER BY confidence DESC LIMIT {self.max_plates}"
            else:
                query += f" FROM plates WHERE confidence >= {self.min_confidence} ORDER BY confidence DESC LIMIT {self.max_plates}"
            
            cursor.execute(query)
            plates = cursor.fetchall()
            
            # Verileri tree view'e ekle
            for i, plate in enumerate(plates):
                plate_id = plate[0]
                plate_name = plate[1]
                clarity = plate[2] if plate[2] is not None else 0
                conf = plate[3] if plate[3] is not None else 0
                date = plate[5] if len(plate) > 5 and plate[5] else "Bilinmiyor"
                
                # Alternatif satır renklendirmesi için etiket
                tag = "even" if i % 2 == 0 else "odd"
                
                self.plate_tree.insert("", tk.END, values=(
                    plate_id, plate_name, date, f"{clarity:.1f}", f"{conf:.2f}"
                ), tags=(tag,))
            
            # Satır renklerini ayarla
            self.plate_tree.tag_configure("even", background="#f0f0f0")
            self.plate_tree.tag_configure("odd", background="white")
            
            if search_text:
                self.status_var.set(f"'{search_text}' araması için {len(plates)} plaka bulundu")
            else:
                self.status_var.set(f"En yüksek güven değerine sahip {len(plates)} plaka gösteriliyor")
            
        except Exception as e:
            self.status_var.set(f"Filtreleme hatası: {str(e)}")
    
    def on_plate_select(self, event):
        """Plaka seçildiğinde detayları göster"""
        selection = self.plate_tree.selection()
        if not selection:
            return
        
        # Seçilen plakanın ID'sini al
        item = self.plate_tree.item(selection[0])
        plate_id = item['values'][0]
        self.selected_plate_id = plate_id
        
        if not self.conn:
            return
        
        try:
            # Plaka detaylarını sorgula
            cursor = self.conn.cursor()
            
            # Sütunları kontrol et
            cursor.execute("PRAGMA table_info(plates)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Sorguyu oluştur
            query = "SELECT id, plate_id, image"
            
            if "clarity" in columns:
                query += ", clarity"
            else:
                query += ", NULL as clarity"
                
            if "confidence" in columns:
                query += ", confidence"
            else:
                query += ", NULL as confidence"
                
            if "rotation" in columns:
                query += ", rotation"
            else:
                query += ", NULL as rotation"
                
            if "capture_date" in columns:
                query += ", capture_date"
            else:
                query += ", NULL as capture_date"
                
            if "file_path" in columns:
                query += ", file_path"
            else:
                query += ", NULL as file_path"
            
            query += f" FROM plates WHERE id = {plate_id}"
            
            cursor.execute(query)
            plate = cursor.fetchone()
            
            if not plate:
                messagebox.showerror("Hata", f"ID: {plate_id} olan plaka bulunamadı!")
                return
            
            # Plaka bilgilerini al
            db_id = plate[0]
            plate_name = plate[1]
            image_blob = plate[2]
            
            idx = 3
            clarity = plate[idx] if plate[idx] is not None else "-"
            idx += 1
            confidence = plate[idx] if plate[idx] is not None else "-"
            idx += 1
            rotation = plate[idx] if plate[idx] is not None else "-"
            idx += 1
            date = plate[idx] if idx < len(plate) and plate[idx] is not None else "Bilinmiyor"
            idx += 1
            file_path = plate[idx] if idx < len(plate) and plate[idx] is not None else "-"
            
            # Bilgi etiketlerini güncelle
            self.info_id.config(text=f"{db_id}")
            self.info_plate_id.config(text=f"{plate_name}")
            
            if clarity != "-":
                self.info_clarity.config(text=f"{clarity:.2f}")
            else:
                self.info_clarity.config(text=f"{clarity}")
                
            if confidence != "-":
                self.info_conf.config(text=f"{confidence:.2f}")
            else:
                self.info_conf.config(text=f"{confidence}")
                
            if rotation != "-":
                self.info_rotation.config(text=f"{rotation}°")
            else:
                self.info_rotation.config(text=f"{rotation}")
                
            self.info_date.config(text=f"{date}")
            self.info_path.config(text=f"{os.path.basename(file_path) if file_path != '-' else '-'}")
            
            # Görüntüyü yükle ve göster
            if image_blob:
                # Önbellekte varsa oradan kullan
                if plate_id in self.image_cache:
                    photo = self.image_cache[plate_id]
                    self.image_label.config(image=photo)
                    self.image_label.image = photo
                else:
                    # Arkaplanda yükle
                    self.status_var.set(f"Görüntü yükleniyor: ID {plate_id}...")
                    threading.Thread(target=self.load_image, args=(plate_id, image_blob)).start()
            else:
                self.image_label.config(image='', text="Görüntü bulunamadı")
                
        except Exception as e:
            messagebox.showerror("Detay Hatası", str(e))
            self.status_var.set(f"Hata: {str(e)}")
    
    def load_image(self, plate_id, image_blob):
        """Görüntüyü arkaplanda yükle"""
        try:
            # BLOB verisini PIL Image'a dönüştür
            pil_img = Image.open(io.BytesIO(image_blob))
            
            # Uygun boyuta getir
            max_size = (800, 600)
            pil_img.thumbnail(max_size, Image.LANCZOS)
            
            # ImageTk.PhotoImage'a dönüştür
            photo = ImageTk.PhotoImage(pil_img)
            
            # Önbelleğe ekle
            self.image_cache[plate_id] = photo
            
            # Ana thread üzerinde görüntüyü güncelle
            if self.selected_plate_id == plate_id:  # Hala aynı plaka seçiliyse
                self.root.after(0, lambda: self.update_image_label(photo))
                
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Görüntü yükleme hatası: {str(e)}"))
    
    def update_image_label(self, photo):
        """Görüntü etiketini güncelle (ana thread üzerinde)"""
        self.image_label.config(image=photo, text="")
        self.image_label.image = photo
        self.status_var.set("Görüntü yüklendi")
    
    def show_large_image(self):
        """Seçili plaka görüntüsünü büyük pencerede göster"""
        if not self.selected_plate_id:
            messagebox.showinfo("Bilgi", "Önce bir plaka seçin!")
            return
        
        if not self.conn:
            return
        
        try:
            # Plaka görüntüsünü al
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT plate_id, image FROM plates WHERE id = {self.selected_plate_id}")
            result = cursor.fetchone()
            
            if not result or not result[1]:
                messagebox.showerror("Hata", "Plaka görüntüsü bulunamadı!")
                return
            
            plate_name = result[0]
            image_blob = result[1]
            
            # Yeni pencere oluştur
            img_window = tk.Toplevel(self.root)
            img_window.title(f"Plaka Detayı: {plate_name}")
            img_window.geometry("1024x768")
            img_window.minsize(800, 600)
            
            # Yeni pencereyi yapılandır
            img_window.configure(bg=self.colors.BACKGROUND)
            img_window.focus_set()
            
            # Pencere içeriği
            frame = ttk.Frame(img_window, padding=10)
            frame.pack(fill=tk.BOTH, expand=True)
            
            # Başlık
            ttk.Label(frame, text=f"Plaka: {plate_name}", style="Heading.TLabel").pack(pady=(0, 10))
            
            # Görüntü alanı
            img_frame = ttk.Frame(frame, style="TFrame", relief=tk.SUNKEN, borderwidth=1)
            img_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Görüntü etiketi
            img_label = ttk.Label(img_frame)
            img_label.pack(fill=tk.BOTH, expand=True)
            
            # Görüntüyü yükle
            try:
                # BLOB verisini PIL Image'a dönüştür
                pil_img = Image.open(io.BytesIO(image_blob))
                
                # Pencere boyutuna göre ayarla (en-boy oranını koru)
                max_size = (1000, 700)
                pil_img.thumbnail(max_size, Image.LANCZOS)
                
                # ImageTk.PhotoImage'a dönüştür
                photo = ImageTk.PhotoImage(pil_img)
                
                # Görüntüyü göster
                img_label.config(image=photo)
                img_label.image = photo
                
            except Exception as e:
                img_label.config(text=f"Görüntü yükleme hatası: {str(e)}")
            
            # Kapat düğmesi
            ttk.Button(frame, text="Kapat", command=img_window.destroy, style="Primary.TButton").pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("Görüntüleme Hatası", str(e))
    
    def export_plate_image(self):
        """Seçili plaka görüntüsünü dışa aktar"""
        if not self.selected_plate_id:
            messagebox.showinfo("Bilgi", "Önce bir plaka seçin!")
            return
        
        if not self.conn:
            messagebox.showinfo("Bilgi", "Veritabanı bağlantısı yok!")
            return
        
        try:
            # Plaka görüntüsünü al
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT plate_id, image FROM plates WHERE id = {self.selected_plate_id}")
            result = cursor.fetchone()
            
            if not result or not result[1]:
                messagebox.showerror("Hata", "Plaka görüntüsü bulunamadı!")
                return
            
            plate_name = result[0]
            image_blob = result[1]
            
            # Kaydedilecek dosya adını seç
            current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"SecureDrive_Plaka_{plate_name}_{current_time}.jpg"
            
            file_path = filedialog.asksaveasfilename(
                title="Plaka Görüntüsünü Kaydet",
                defaultextension=".jpg",
                initialfile=default_name,
                filetypes=[("JPEG Dosyası", "*.jpg"), ("PNG Dosyası", "*.png"), ("Tüm Dosyalar", "*.*")]
            )
            
            if not file_path:
                return
            
            # Görüntüyü işle ve kaydet
            pil_img = Image.open(io.BytesIO(image_blob))
            
            # Dosya formatına göre kaydet
            pil_img.save(file_path)
            
            self.status_var.set(f"Görüntü kaydedildi: {os.path.basename(file_path)}")
            messagebox.showinfo("Başarılı", f"Plaka görüntüsü şuraya kaydedildi:\n{file_path}")
            
        except Exception as e:
            messagebox.showerror("Dışa Aktarma Hatası", str(e))
            self.status_var.set(f"Hata: {str(e)}")
    
    def delete_plate(self):
        """Seçili plakayı sil"""
        if not self.selected_plate_id:
            messagebox.showinfo("Bilgi", "Önce bir plaka seçin!")
            return
        
        if not self.conn:
            messagebox.showinfo("Bilgi", "Veritabanı bağlantısı yok!")
            return
        
        # Onay iste
        confirmation = messagebox.askyesno(
            "Onay", 
            f"ID: {self.selected_plate_id} olan plakayı silmek istediğinizden emin misiniz?"
        )
        
        if not confirmation:
            return
        
        try:
            # Plakayı sil
            cursor = self.conn.cursor()
            cursor.execute(f"DELETE FROM plates WHERE id = {self.selected_plate_id}")
            self.conn.commit()
            
            # Önbelleği temizle
            if self.selected_plate_id in self.image_cache:
                del self.image_cache[self.selected_plate_id]
            
            # Görüntüyü temizle
            self.image_label.config(image='', text="Plaka silindi")
            
            # Bilgileri temizle
            self.info_id.config(text="-")
            self.info_plate_id.config(text="-")
            self.info_date.config(text="-")
            self.info_clarity.config(text="-")
            self.info_conf.config(text="-")
            self.info_rotation.config(text="-")
            self.info_path.config(text="-")
            
            # Listeyi yenile
            self.refresh_plate_list()
            
            self.status_var.set(f"Plaka silindi: ID {self.selected_plate_id}")
            
        except Exception as e:
            messagebox.showerror("Silme Hatası", str(e))
            self.status_var.set(f"Hata: {str(e)}")

# Uygulamayı başlat
if __name__ == "__main__":
    root = tk.Tk()
    app = PlateDetectionGUI(root)
    root.mainloop()