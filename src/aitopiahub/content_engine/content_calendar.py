"""
İçerik Takvimi (Content Calendar)
Görevi: Her gün için yeni bir çocuk kanalı konusu belirlemek.
"""

import datetime

TOPICS = [
    {"keyword": "Güneş Sistemi", "finding": "Gezegenlerin isimleri, büyüklükleri ve ilginç özellikleri."},
    {"keyword": "Dinozorlar Alemi", "finding": "T-Rex'ten Triceratops'a kadar en meşhur dinozorlar ve yaşamları."},
    {"keyword": "Okyanusun Derinlikleri", "finding": "Mavi balinalar, köpekbalıkları ve parlayan derin deniz canlıları."},
    {"keyword": "Vücudumuzun Sırları", "finding": "Kalp nasıl atar? Beynimiz nasıl düşünür? İskeletimiz ne işe yarar?"},
    {"keyword": "Mısır Piramitleri", "finding": "Piramitler nasıl yapıldı? Firavunlar kimdi? Mumyalar nedir?"},
    {"keyword": "Ormandaki Dostlarımız", "finding": "Aslanlar, filler ve zürafaların ormandaki gizli yaşamı."},
    {"keyword": "Uzay Yolculuğu", "finding": "Astronotlar ne yer? Roketler nasıl uçar? Ay'da yürümek nasıl bir his?"},
    {"keyword": "İyilik ve Yardımseverlik", "finding": "Küçük bir iyiliğin dünyayı nasıl değiştirebileceğine dair bir hikaye."},
    {"keyword": "Doğayı Koruyalım", "finding": "Geri dönüşüm nedir? Ağaçlar neden nefes almamızı sağlar?"},
    {"keyword": "Böceklerin Mikro Dünyası", "finding": "Karıncaların gücü, arıların bal yapma serüveni."},
]

class ContentCalendar:
    @staticmethod
    def get_topic_for_today():
        # Gün sayısına göre döngüsel konu seçimi
        day_of_year = datetime.datetime.now().timetuple().tm_yday
        index = day_of_year % len(TOPICS)
        return TOPICS[index]
