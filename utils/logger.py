"""
日誌設定與脫敏處理
"""
import logging
import sys


def mask_secret(value: str) -> str:
    """
    對敏感資訊進行脫敏處理
    
    Args:
        value: 要脫敏的字串
        
    Returns:
        脫敏後的字串（前 4 碼 + ****）
    """
    if not value or len(value) <= 8:
        return "****"
    return value[:4] + "****"


def setup_logger(name: str = __name__) -> logging.Logger:
    """
    設定並返回 logger
    
    Args:
        name: logger 名稱
        
    Returns:
        配置好的 logger
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # 輸出到 stdout（Zeabur 自動收集）
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        
        # 格式：時間 | 層級 | 模組 | 訊息
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
    
    return logger
