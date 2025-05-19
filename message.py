import os
import requests
from loguru import logger
import dotenv
import json

# Load environment variables from .env file
dotenv.load_dotenv()

def send_telegram_message(message):
    # Get Telegram bot token and chat ID from environment variables
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    logger.info(f"bot_token: {bot_token}, chat_id: {chat_id}")
    
    # If Telegram credentials are not configured, just log and return
    if not bot_token or not chat_id:
        logger.warning("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable notifications.")
        return
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

def send_wechat_message(message):
    # 获取企业微信机器人webhook
    webhook_url = os.getenv("WECHAT_WEBHOOK_URL")
    
    if not webhook_url:
        logger.warning("企业微信未配置. 设置WECHAT_WEBHOOK_URL环境变量启用通知.")
        return
    
    try:
        headers = {"Content-Type": "application/json"}
        data = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }
        response = requests.post(webhook_url, headers=headers, data=json.dumps(data))
        if response.status_code != 200:
            logger.error(f"企业微信消息发送失败: {response.text}")
        return response
    except Exception as e:
        logger.error(f"企业微信消息发送出错: {e}")

# 示例用法
# if __name__ == '__main__':
#     result = send_telegram_message("✅ 测试消息：Python 成功发送到 Telegram！")
#     print(result)
#     result = send_wechat_message("✅ 测试消息：Python 成功发送到企业微信！")
#     print(result)