"""
爬虫运行脚本
从项目根目录运行爬虫
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler.crawler import main

if __name__ == "__main__":
    main()

