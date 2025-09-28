from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import os

def create_driver():
    driver = webdriver.Chrome()  # ChromeDriver kurulu olmalı
    driver.maximize_window()
    return driver

def login(driver):
    driver.get("https://twitter.com/login")
    time.sleep(3)

    # Kullanıcı adı
    username = driver.find_element(By.NAME, "text")
    username.send_keys(os.getenv("TWITTER_USERNAME"))
    username.send_keys(Keys.RETURN)
    time.sleep(2)

    # Şifre
    password = driver.find_element(By.NAME, "password")
    password.send_keys(os.getenv("TWITTER_PASSWORD"))
    password.send_keys(Keys.RETURN)
    time.sleep(5)

def is_logged_in(driver):
    driver.get("https://twitter.com/home")
    time.sleep(3)
    return "login" not in driver.current_url
