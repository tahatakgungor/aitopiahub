import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import pickle

def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    # Opsiyonel: Headless mod
    # options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    return driver

def login(driver):
    driver.get("https://twitter.com/login")
    time.sleep(3)

    username = driver.find_element(By.NAME, "text")
    username.send_keys(os.getenv("TWITTER_USERNAME"))  # .env'den çekebilirsin
    username.send_keys(Keys.RETURN)
    time.sleep(2)

    password = driver.find_element(By.NAME, "password")
    password.send_keys(os.getenv("TWITTER_PASSWORD"))  # .env'den çekebilirsin
    password.send_keys(Keys.RETURN)
    time.sleep(5)

def is_logged_in(driver):
    driver.get("https://twitter.com/home")
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
    driver.get("https://twitter.com")
    with open(path, "rb") as f:
        cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
    driver.refresh()
    time.sleep(3)
