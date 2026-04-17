import os
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

# .env dosyasındaki bilgileri yükle
load_dotenv()

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

# YouTube API için gerekli kapsamlar
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("HATA: .env dosyasında YOUTUBE_CLIENT_ID veya YOUTUBE_CLIENT_SECRET bulunamadı!")
        return

    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    # Flow başlat
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    
    # Yerel bir server başlatıp tarayıcıyı açar
    # Not: Eğer sunucu üzerindeyse console flow da denenebilir ama 
    # masaüstü uygulaması olarak oluşturduğumuz için bu en güvenli yoldur.
    credentials = flow.run_local_server(port=0)

    print("\n" + "="*50)
    print("GİRİŞ BAŞARILI!")
    print("="*50)
    print(f"YOUTUBE_REFRESH_TOKEN: {credentials.refresh_token}")
    print("="*50)
    print("\nLütfen yukarıdaki REFRESH_TOKEN değerini .env dosyanıza ekleyin.")

if __name__ == "__main__":
    main()
