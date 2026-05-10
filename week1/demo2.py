import requests, time, random, pandas as pd
from sqlalchemy import create_engine

# ===== 筛选条件（按需修改） =====
FILTER = {"primaryInvestType": "私募证券投资基金管理人", "fundScale": None}  # 基金规模可填 "10-20亿元" 等
FILTER = {k: v for k, v in FILTER.items() if v is not None}

def fetch_page(page):
    params = {"rand": random.random(), "page": page, "size": 100, **FILTER}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Content-Type": "application/json",
        "Referer": "https://gs.amac.org.cn/amac-infodisc/res/pof/manager/managerList.html",
        "Origin": "https://gs.amac.org.cn",
        "X-Requested-With": "XMLHttpRequest",
    }
    s = requests.Session()
    s.get("https://gs.amac.org.cn/amac-infodisc/res/pof/manager/managerList.html", headers=headers, timeout=15)
    resp = s.post("https://gs.amac.org.cn/amac-infodisc/api/pof/manager", params=params, json={}, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()

# 自动分页爬取
first = fetch_page(0)
if not first or "content" not in first: exit("❌ 无法获取数据")
total_pages = first["totalPages"]
all_rows = first["content"]
print(f"总页数：{total_pages}，第1页获取 {len(all_rows)} 条")

for p in range(1, total_pages):
    time.sleep(random.uniform(1, 2))
    data = fetch_page(p)
    if data and "content" in data:
        all_rows.extend(data["content"])
        print(f"第{p+1}页完成，累计 {len(all_rows)} 条")

df = pd.DataFrame(all_rows)
if df.empty: exit("⚠️ 无数据")

# 字段映射与清洗
col_map = {
    "managerName": "私募基金管理人名称", "primaryInvestType": "机构类型",
    "registerNo": "登记编号", "regAdrAgg": "注册地", "officeAddress": "办公地",
    "establishDate": "成立时间", "registerDate": "登记时间",
    "fundCount": "在管基金数量", "fundScale": "基金规模",
    "hasSpecialTips": "是否有提示信息", "hasCreditTips": "是否有诚信信息", "id": "管理人ID"
}
df = df[[c for c in col_map if c in df.columns]].rename(columns=col_map)
for col in ["成立时间", "登记时间"]:
    if col in df.columns: df[col] = pd.to_datetime(df[col].astype(float), unit='ms').dt.strftime("%Y-%m-%d")
for col in ["是否有提示信息", "是否有诚信信息"]:
    if col in df.columns: df[col] = df[col].apply(lambda x: "是" if str(x).lower() == "true" else "否")

# ===== 写入 MySQL（intern 库）=====
engine = create_engine(
    "mysql+pymysql://readonly:readonly123+@120.48.57.24:3306/intern?charset=utf8mb4"
)
table = "private_fund_managers"

try:
    existing_ids = pd.read_sql(f"SELECT `管理人ID` FROM `{table}`", engine)["管理人ID"].tolist()
except Exception:
    existing_ids = []

new_df = df[~df["管理人ID"].isin(existing_ids)] if "管理人ID" in df.columns else df

if not new_df.empty:
    new_df.to_sql(table, engine, if_exists="append", index=False)
    print(f"✅ 新增 {len(new_df)} 条，数据库累计 {len(existing_ids)+len(new_df)} 条")
else:
    print("ℹ️ 无新增数据")