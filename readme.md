# iPhone 17 Pro Max 库存监控脚本（多店铺版）

## 功能
- 每 2 分钟检测苹果新加坡官网 iPhone 17 Pro Max 256GB (Cosmic Orange) 库存
- 店内有货或可配送都有 Telegram 提醒
- 防止重复提醒
- 消息包含店铺名、地址、电话、预约链接

## 配置
1. Fork 仓库到自己的 GitHub
2. 在仓库设置 → Secrets → Actions：
   - `BOT_TOKEN` = 你的 Telegram Bot Token
   - `CHAT_ID` = 你的 Telegram chat_id
3. 脚本默认检测新加坡邮编 018972，可根据需要修改 `CHECK_URL` 中的 `location` 参数
4. Workflow 已设置每 2 分钟运行一次

## 使用
- push 到仓库后，GitHub Actions 会自动执行
- 可手动触发 Workflow 检查库存
