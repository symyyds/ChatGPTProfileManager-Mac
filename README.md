# ChatGPT Profile Manager for macOS

一个面向 macOS 的本地 ChatGPT 多账号独立浏览器环境管理台。每个账号使用独立 Chrome `user-data-dir`，方便分别登录、在独立 Chrome 窗口启动官方 OAuth 授权获取 auth.json、保存备注状态。

## 前置要求

- macOS
- Google Chrome 安装在 `/Applications`
- Python 3
- 如果要获取官方 `auth.json`，需要安装 Codex CLI 并能在终端执行 `codex`

## 启动

双击：

```text
start.command
```

或在终端运行：

```bash
chmod +x ./start.sh ./start.command
./start.sh
```

默认地址：

```text
http://127.0.0.1:8765
```

## 功能

- 新建独立账号环境，不需要先输入邮箱
- 账号列表按创建时间倒序排列，后创建的在最上面
- 账号环境名可编辑，点“保存现有信息”会真正重命名文件夹
- 每行保留四个操作：打开 ChatGPT 官网、第二步 获取JSON、保存现有信息、删除账号
- JSON 状态下面提供查看和下载 `auth.json`
- 支持批量预创建账号文件夹

## 本地私有数据

以下目录只保留空文件夹占位，不会提交账号内容：

```text
chatgpt-profiles/
deleted-profiles/
```

这些目录里会生成 Chrome 登录状态、Cookie、缓存、auth.json 等敏感文件。不要手动提交它们。

`auth-links.json` 是本地链接配置，也不会提交。需要示例时参考 `auth-links.example.json`。
