import os
import subprocess
import shlex
import time

# Varsayılan model: llama3.1 8B
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")
OLLAMA_BIN = os.getenv("OLLAMA_BIN", "ollama")

def _run_ollama(model: str, prompt: str, timeout: int = 20) -> str:
    """
    Ollama'yı subprocess ile çağırır, stdout'u döner. Timeout ve hatalar yönetilir.
    """
    # Ollama run komutu: ["ollama", "run", model, prompt]
    # prompt'ı doğrudan argüman olarak vermek bazen shell/escaping sorunlarına yol açar,
    # bu yüzden shlex.quote ile güvenli hale getirebiliriz (burada subprocess list ile veriyoruz).
    cmd = [OLLAMA_BIN, "run", model, prompt]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError("Ollama çağrısı zaman aşımına uğradı")
    except subprocess.CalledProcessError as e:
        # Ollama hata mesajını kullanıcıya verebiliriz (log amaçlı)
        raise RuntimeError(f"Ollama hatası: {e.stderr.strip() or e.stdout.strip()}")

def generate_tweet_content(trend: str, retries: int = 2) -> str:
    """
    Trend başlığını Llama 3.1 8B (Ollama) kullanarak Türkçe, haber tarzı ve 280 karakteri geçmeyecek bir tweet'e dönüştürür.
    Retries ile kısa hatalarda tekrar deneyebilir.
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

    last_err = None
    for attempt in range(1, retries + 2):  # retries = 0 -> 1 attempt
        try:
            response = _run_ollama(LLM_MODEL, prompt, timeout=25)
            tweet = response.strip()
            # Basit validasyon: boş değil ve 280 char altı
            if not tweet:
                raise RuntimeError("Model boş çıktı verdi")
            if len(tweet) > 280:
                tweet = tweet[:279]  # kesme fallback'i (ideal: prompt ile token limit talep et)
            return tweet
        except Exception as exc:
            last_err = exc
            # Kısa bekleme ve retry
            if attempt <= retries:
                time.sleep(1 + attempt)
                continue
            else:
                # Son çare: fallback olarak trend başlığını geri döndür (ve logla)
                print(f"[generate_tweet_content] Hata: {exc}")
                return trend[:280]

# Örnek kullanım
if __name__ == "__main__":
    example = "Yeni elektrikli otomobil vergilendirme paketi açıklandı"
    print("Üretilen tweet:", generate_tweet_content(example))
