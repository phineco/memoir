#!/usr/bin/env python3
"""一次性初始化空数据库；已有库只使用 migrate.py，勿与服务并行执行。"""
import sys

from sqlalchemy import create_engine, inspect

from config import Config
from models import Base


def initialize_database(database_url):
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            if inspect(connection).get_table_names():
                raise ValueError("数据库已有表，已停止初始化；已有库请备份后执行 python migrate.py")
            Base.metadata.create_all(connection)
    finally:
        engine.dispose()


def main():
    try:
        initialize_database(Config.DATABASE_URL)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("空库初始化完成。请执行 python migrate.py，然后创建管理员并启动服务。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
