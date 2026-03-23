日常启动：
- 双击 `tools\Launch-Webnovel-Dashboard.bat`
- 或双击桌面快捷方式

常用入口：
- 启动工作台：`tools\Start-Webnovel-Writer.bat`
- 打开兼容菜单：`tools\Start-Webnovel-Writer.bat menu`
- 开启局域网共享：`tools\Start-Webnovel-Writer.bat dashboard-lan`
- 登录创作命令行：`tools\Start-Webnovel-Writer.bat login`
- 打开项目终端：`tools\Start-Webnovel-Writer.bat shell`

当前默认行为：
1. 双击后直接进入 Web 工作台，不再先弹旧菜单或目录选择框。
2. 启动脚本会先检查本机 `8765` 端口上的 Dashboard 实例是否可复用。
3. 工作台模式会探测 `GET /api/workbench/hub`；项目模式会探测 `GET /api/project/director-hub?project_root=...`。
4. 如果发现旧实例存在，但当前模式对应的健康探针没有返回有效 JSON，会自动停止旧实例并重启最新后端。
5. 只有在健康检查通过后才会打开浏览器，避免落到旧前端或残缺后端。

如果要直接运行 PowerShell 脚本：
- `tools\Launch-Webnovel-Dashboard.ps1`

说明：
- 不传 `-ProjectRoot` 时，默认进入全局工作台。
- 只有显式传入已初始化项目目录时，才会直接进入单项目视图。
- 启动器只会复用“属于当前工作区且健康探针通过”的已有实例。
