from abc import ABC, abstractmethod


class UserTaskBase(ABC):

    @abstractmethod
    def start(self):
        """
        启动用户任务的方法，必须由用户定义的类实现
        """
        pass

    @abstractmethod
    def stop(self):
        """
        停止用户任务的方法，必须由用户定义的类实现
        """
        pass
