from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import pyperclip
import time

def post_tweet(driver, content: str):
    driver.get("https://twitter.com/compose/tweet")
    wait = WebDriverWait(driver, 20)

    # Tweet kutusunu bekle
    tweet_box = wait.until(
        EC.presence_of_element_located((By.XPATH, '//div[@role="textbox"]'))
    )

    # Clipboard'a kopyala ve yapıştır
    pyperclip.copy(content)
    tweet_box.click()

    # Mac için CMD+V, Windows için Keys.CONTROL + "v"
    tweet_box.send_keys(Keys.COMMAND, "v")  # Mac
    # tweet_box.send_keys(Keys.CONTROL, "v")  # Windows kullanıyorsan bunu aç

    time.sleep(0.5)  # İçeriğin yapışması için bekle

    # Tweet butonunu bekle
    tweet_button = wait.until(
        EC.presence_of_element_located((
            By.XPATH, '//div[@data-testid="tweetButtonInline"] | //button[.//span[text()="Post"]]'
        ))
    )

    # Buton görünür olana kadar scroll ve JS tıklama
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tweet_button)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", tweet_button)
    time.sleep(2)
