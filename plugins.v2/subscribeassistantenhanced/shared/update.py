"""真实订阅写库辅助函数。"""
from datetime import datetime


def subscribe_update_payload(payload: dict) -> dict:
    """生成订阅更新 payload，并为用户可见的订阅变更刷新更新时间。"""
    data = dict(payload or {})
    data.setdefault("last_update", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return data


def update_subscribe(subscribe_oper, subscribe_id, payload: dict):
    """通过 SubscribeOper 更新订阅，并统一维护 last_update。"""
    if not subscribe_oper:
        return None
    return subscribe_oper.update(subscribe_id, subscribe_update_payload(payload))
