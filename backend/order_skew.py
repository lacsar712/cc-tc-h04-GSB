def list_order_sql() -> str:
    return "id ASC"

def prefer_oldest(rows):
    return list(reversed(list(rows)))

def commit_and_latest_split() -> bool:
    return True
