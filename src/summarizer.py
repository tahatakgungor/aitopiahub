import os
import subprocess

LLM_MODEL = os.getenv("LLM_MODEL", "llama3:latest")

def generate_tweet_content(trend: str) -> str:
    """
    Trend başlığını Llama3 modelini kullanarak Türkçe, ilgi çekici ve haber tarzı tweet'e dönüştürür.
    """
    prompt = f"""
Sen Twitter için içerik üreten bir sosyal medya uzmanısın.
Aşağıdaki trend başlığını, kullanıcıyı okumaya ve paylaşmaya teşvik eden,
haber tarzında ve kısa (280 karakteri geçmeyecek) bir tweet'e çevir.

Trend başlığı: {trend}

Kurallar:
- Türkçe yaz
- Haber tonu kullanılmalı
- Kullanıcı ilgisini çekecek şekilde yaz
- Emoji veya hashtag ekleyebilirsin ama abartma
- Retweet ve beğeni alabilecek şekilde yaz

Sadece tweet metnini yaz, ek açıklama yapma.
"""

    try:
        result = subprocess.run(
            ["ollama", "run", LLM_MODEL, prompt],
            capture_output=True,
            text=True,
            check=True
        )
        tweet = result.stdout.strip()
        return tweet

    except subprocess.CalledProcessError as e:
        print("Ollama ile içerik üretirken hata:", e)
        return trend  # Hata olursa fallback
