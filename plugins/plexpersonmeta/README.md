# Plex Plex演职人员刮削

实现刮削演职人员中文名称及角色

- **技术难点**：Plex 的 API 实现较为复杂，特别是在处理关联演职人员的 `tagKey`，我在尝试为 `actor.tag.tagKey` 赋值时遇到了问题。如果您对此有所了解，请不吝赐教，欢迎通过在项目的 GitHub 页面新增一个 issue 与我联系，我将非常感谢您的反馈和帮助。
- **操作警告**：在刮削演职人员信息后，可能会出现一些问题，例如丢失在线元数据，或者在 Plex 中无法通过点击演职人员的名字来查看其详细信息。请在操作前备份相关数据，以防不测。
- **免责声明**：
  - **实验性功能**：「保留在线元数据」选项目前处于实验性阶段。如果您选择启用此功能，建议先在非主要环境中测试以确保稳定性。由于结合数据库脚本使用该功能可能导致元数据丢失、播放失败或其他一系列未知问题。在启用此功能之前，请确保您了解可能的风险并已做好充分的预防措施。

在进行任何操作前，请确保您已经做好了完整的数据备份，并理解所有相关的技术细节和潜在风险。如果您有更多关于 Plex API 的技术问题或需求，欢迎与我联系或查阅更多资料。

#### 数据库脚本操作指南

1. **停用 Plex 服务**：首先，请确保停用 Plex 服务，以避免在备份或修改数据库时出现数据冲突。
2. **备份 Plex 数据库**：重要的步骤不能忽视，务必先备份您的 Plex 数据库。数据库文件通常位于 `/Plug-in Support/Databases/com.plexapp.plugins.library.db`。关于备份和修复数据库的具体操作，请参考以下官方链接：
   - [修复损坏的数据库](https://support.plex.tv/articles/repair-a-corrupted-database/)
   - [通过‘计划任务’恢复备份的数据库](https://support.plex.tv/articles/202485658-restore-a-database-backed-up-via-scheduled-tasks/)

3. **下载并执行 SQL 脚本**：
   - 在备份完成后，请下载附件中的 SQL 脚本。
   - 使用如 [SQLiteStudio](https://github.com/pawelsalawa/sqlitestudio)、[Navicat for SQLite](https://www.navicat.com/en/products/navicat-for-sqlite) 或 [DBeaver](https://dbeaver.com/docs/dbeaver/Database-driver-SQLite/) 等工具打开您的 Plex 数据库。
   - 执行下载的 SQL 脚本，更新数据库。

4. **验证脚本执行结果**：
   - 脚本执行完毕后，运行以下 SQL 查询以确认触发器是否已正确创建：
     ```sql
     SELECT name, tbl_name, sql
     FROM sqlite_master
     WHERE type = 'trigger';
     ```
   - 如果查询结果显示如附件截图中的红框内容，则表示脚本已成功执行。

   ![](../../images/2024-07-04-02-11-17.png)

5. **下载 SQL 脚本**：
   - 点击此处[下载脚本](resources/trigger.sql)。

请在操作过程中保持注意，确保每一步均正确执行，以防数据丢失或损坏。

#### 感谢

- 本插件基于 [官方插件](https://github.com/jxxghp/MoviePilot-Plugins) 编写，并参考了 [PrettyServer](https://github.com/Bespertrijun/PrettyServer) 项目，实现了插件的相关功能。
- 特此感谢 [jxxghp](https://github.com/jxxghp)、[Bespertrijun](https://github.com/Bespertrijun) 等贡献者的卓越代码贡献。
- 如有未能提及的作者，请告知我以便进行补充。

![](../../images/2024-07-04-01-57-02.png)
![](../../images/2024-06-25-02-57-20.png)
![](../../images/2024-06-25-02-57-53.png)

