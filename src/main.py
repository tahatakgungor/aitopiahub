from dotenv import load_dotenv
load_dotenv()

from twitter_bot import create_driver, login, is_logged_in
from trends import get_trends
from summarizer import generate_tweet_content
from x_poster import post_tweet

def main():
    driver = create_driver()

    if not is_logged_in(driver):
        login(driver)

    trends = get_trends(driver)

    for trend in trends:
        print("İşleniyor:", trend)
        content = generate_tweet_content(trend)
        print("Tweet atılıyor:", content)
        post_tweet(driver, content)

    driver.quit()

if __name__ == "__main__":
    main()
