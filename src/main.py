from dotenv import load_dotenv
load_dotenv()

from twitter_bot import create_driver, login, is_logged_in, save_cookies, load_cookies
from trends import get_trends
from summarizer import generate_tweet_content
from x_poster import post_tweet
import os

def main():
    driver = create_driver()

    # Cookie varsa yükle
    if os.path.exists("cookies.pkl"):
        load_cookies(driver, "cookies.pkl")

    # Giriş yapılmamışsa login ol
    if not is_logged_in(driver):
        login(driver)
        save_cookies(driver, "cookies.pkl")

    trends = get_trends(driver)

    for trend in trends:
        print("İşleniyor:", trend)
        content = generate_tweet_content(trend)
        print("Tweet atılıyor:", content)
        post_tweet(driver, content)

    driver.quit()

if __name__ == "__main__":
    main()
