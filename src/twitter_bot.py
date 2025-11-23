import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pickle


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    # options.add_argument("--headless")  # istersen aktif et
    driver = webdriver.Chrome(options=options)
    return driver


def login(driver):
    driver.get("https://x.com/login")
    wait = WebDriverWait(driver, 20)

    # 1️⃣ Kullanıcı adı alanı
    username = wait.until(EC.presence_of_element_located((By.NAME, "text")))
    username.send_keys(os.getenv("TWITTER_USERNAME"))
    username.send_keys(Keys.RETURN)
    time.sleep(2)

    # 2️⃣ Eğer "Telefon ya da kullanıcı adı sorusu" çıkarsa:
    try:
        alt_input = wait.until(
            EC.presence_of_element_located((By.XPATH, '//input[@name="text"]'))
        )
        if alt_input:
            alt_input.send_keys(os.getenv("TWITTER_USERNAME"))
            alt_input.send_keys(Keys.RETURN)
            time.sleep(2)
    except:
        pass

    # 3️⃣ Şifre alanı (bazı durumlarda dinamik yükleniyor)
    password = wait.until(EC.presence_of_element_located((By.NAME, "password")))
    password.send_keys(os.getenv("TWITTER_PASSWORD"))
    password.send_keys(Keys.RETURN)

    time.sleep(5)


def is_logged_in(driver):
    driver.get("https://x.com/home")
    time.sleep(3)
    try:
        driver.find_element(By.XPATH, '//a[@href="/home"]')
        return True
    except:
        return False


def save_cookies(driver, path):
    with open(path, "wb") as f:
        pickle.dump(driver.get_cookies(), f)


def load_cookies(driver, path):
    driver.get("https://x.com")
    with open(path, "rb") as f:
        cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
    driver.refresh()
    time.sleep(3)
