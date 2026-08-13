"""真实订阅写库辅助函数。"""


def subscribe_update_payload(payload: dict) -> dict:
    """生成订阅更新 payload，保持调用方字段边界。"""
    return dict(payload or {})


def update_subscribe(subscribe_oper, subscribe_id, payload: dict):
    """通过 SubscribeOper 更新订阅，并透传调用方声明的变更字段。"""
    if not subscribe_oper:
        return None
    data = subscribe_update_payload(payload)
    if not data:
        return None
    return subscribe_oper.update(subscribe_id, data)
