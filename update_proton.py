import os
import requests

# Konfigürasyon
REPO_OWNER = "bdefore"
REPO_NAME = "protondb-data"
FOLDER_PATH = "reports"
SAVE_DIR = "/home/ubuntu/gametrix/downloads" # Dosyanın kaydolacağı yer
LAST_FILE_TRACKER = "/home/ubuntu/gametrix/last_downloaded.txt"

# Klasörleri oluştur
os.makedirs(SAVE_DIR, exist_ok=True)

def get_latest_report():
    # GitHub API'sinden klasör içeriğini çekiyoruz
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FOLDER_PATH}"
    response = requests.get(url)
    if response.status_code != 200:
        print("GitHub API'sine erişilemedi.")
        return None
    
    files = response.json()
    # Sadece .tar.gz uzantılı olanları filtrele
    report_files = [f for f in files if f['name'].endswith('.tar.gz')]
    
    if not report_files:
        return None
    
    # Dosya adından en güncel olanı bul (tarihe göre sıralı geldikleri için son eleman en yenisidir)
    latest_file = report_files[-1]
    return latest_file['name'], latest_file['download_url']

def download_file(url, filename):
    local_path = os.path.join(SAVE_DIR, filename)
    print(f"İndiriliyor: {filename}...")
    
    # 1 GB RAM dostu streaming (parça parça) indirme yöntemi
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print("İndirme tamamlandı!")
    return local_path

def main():
    result = get_latest_report()
    if not result:
        print("Rapor bulunamadı.")
        return
        
    filename, download_url = result
    
    # Daha önce indirdiğimiz dosya adını kontrol et
    last_downloaded = ""
    if os.path.exists(LAST_FILE_TRACKER):
        with open(LAST_FILE_TRACKER, "r") as f:
            last_downloaded = f.read().strip()
            
    if filename == last_downloaded:
        print("Zaten en güncel dosya indirilmiş. İşlem iptal edildi.")
        return
        
    # Yeni dosya var, indir
    file_path = download_file(download_url, filename)
    
    # TODO: Burada indirilen dosyayı zipten çıkarıp SQLite veritabanına import eden fonksiyonunu tetikleyebilirsin.
    # Örnek: import_to_sqlite(file_path)
    
    # İndirme başarılı olunca takip dosyasına adını yaz
    with open(LAST_FILE_TRACKER, "w") as f:
        f.write(filename)

if __name__ == "__main__":
    main()