from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def post_tweet(driver, content: str):
    driver.get("https://twitter.com/compose/tweet")

    wait = WebDriverWait(driver, 20)

    # Tweet kutusu
    tweet_box = wait.until(
        EC.presence_of_element_located((By.XPATH, '//div[@role="textbox"]'))
    )
    tweet_box.click()
    tweet_box.send_keys(content)

    # Tweet butonu
    tweet_button = wait.until(
        EC.presence_of_element_located((By.XPATH, '//button[.//span[text()="Post"]]'))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", tweet_button)
    driver.execute_script("arguments[0].click();", tweet_button)
