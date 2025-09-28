import os
import subprocess

LLM_MODEL = os.getenv("LLM_MODEL", "llama3:latest")

def generate_tweet_content(trend: str) -> str:
    """
    Trend başlığını Llama3 modelini kullanarak mantıklı bir tweet'e dönüştürür.
    """
    prompt = f"Bu trend başlığını kısa ve mantıklı bir tweet haline getir: {trend}"

    # Ollama CLI çağrısı
    result = subprocess.run(
        ["ollama", "run", LLM_MODEL, prompt],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("Ollama hata verdi:", result.stderr)
        return trend

    return result.stdout.strip()
