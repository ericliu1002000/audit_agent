# 开发常用命令速查

面向日常开发与联调，把最常用的命令集中放在这里，避免来回翻日志。

## 环境准备

- 激活 Conda 环境：`conda activate audit_agent`
- 安装 Python 依赖：`pip install -r requirements.txt`
- 安装/更新前端依赖（首次或有变更时）：`npm install`

## Django 后端

- 启动开发服务器：`python manage.py runserver`
- 同步数据库：`python manage.py migrate`
- 创建管理员账号：`python manage.py createsuperuser`
- 快速检查配置：`python manage.py check`

## 前端样式（Tailwind CSS）

- 开发模式实时监听：`npm run tailwind:watch`
- 生成压缩产物（部署前）：`npm run tailwind:build`

> 小提示：跑前端命令前建议先执行一次 `npm install`，确保 `tailwindcss` 等工具安装完毕。
