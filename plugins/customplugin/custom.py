# 演示代码示例，继承UserTaskBase，并实现start以及stop
# 导入logger用于日志记录
from app.log import logger
# 导入UserTaskBase作为基类
from app.plugins.customplugin.task import UserTaskBase


# 定义一个继承自UserTaskBase的类HelloWorld
class HelloWorld(UserTaskBase):
    def start(self):
        """
        开始任务时调用此方法
        """
        # 记录任务开始的信息
        logger.info("Hello World. Start.")

    def stop(self):
        """
        停止任务时调用此方法
        """
        # 记录任务停止的信息
        logger.info("Hello World. Stop.")