from selenium.webdriver.common.by import By
import time

def get_trends(driver):
    driver.get("https://twitter.com/explore/tabs/trending")
    time.sleep(3)

    trends_elements = driver.find_elements(By.XPATH, '//span[contains(text(), "#")]')
    trends = [t.text for t in trends_elements]

    return trends[:10]  # İlk 10 trend
