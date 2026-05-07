import time
import random
import pandas as pd
from sqlalchemy import create_engine
from selenium import webdriver
from selenium.webdriver.edge.options import Options


# =========================
# 1. 基础配置
# =========================

PAGE_URL = "https://gs.amac.org.cn/amac-infodisc/res/pof/manager/managerList.html"
PAGE_SIZE = 100


# =========================
# 2. 字段映射
# =========================

COLUMN_MAP = {
    "managerName": "私募基金管理人名称",
    "artificialPersonName": "法定代表人/执行事务合伙人(委派代表)姓名",
    "primaryInvestType": "机构类型",
    "registerNo": "登记编号",
    "registerProvince": "注册地省份",
    "registerCity": "注册地城市",
    "regAdrAgg": "注册地",
    "officeProvince": "办公地省份",
    "officeCity": "办公地城市",
    "officeAddress": "办公地",
    "establishDate": "成立时间",
    "registerDate": "登记时间",
    "fundCount": "在管基金数量",
    "fundScale": "基金规模",
    "paidInCapital": "实缴资本",
    "subscribedCapital": "认缴资本",
    "hasSpecialTips": "是否有提示信息",
    "hasCreditTips": "是否有诚信信息",
    "inBlacklist": "是否在黑名单",
    "id": "管理人ID",
}


# =========================
# 3. 启动 Edge 浏览器
# =========================

def create_driver():
    """
    启动 Microsoft Edge 浏览器。
    如果你的普通 Edge 能打开中基协网页，这个版本通常更合适。
    """
    options = Options()

    options.add_argument("--start-maximized")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")

    driver = webdriver.Edge(options=options)
    return driver


# =========================
# 4. 通过浏览器内部 fetch 请求数据
# =========================

def fetch_page_by_browser(driver, page, size=PAGE_SIZE):
    """
    通过 Edge 浏览器内部的 fetch 请求中基协接口。
    page 从 0 开始。
    """

    js_code = """
    const callback = arguments[arguments.length - 1];
    const page = arguments[0];
    const size = arguments[1];
    const rand = Math.random();

    fetch(`/amac-infodisc/api/pof/manager?rand=${rand}&page=${page}&size=${size}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json;charset=UTF-8"
        },
        body: JSON.stringify({})
    })
    .then(response => response.json())
    .then(data => callback(data))
    .catch(error => callback({"error": String(error)}));
    """

    data = driver.execute_async_script(js_code, page, size)
    return data


# =========================
# 5. 爬取数据
# =========================

def crawl_data(max_pages=3):
    """
    爬取私募基金管理人数据。
    max_pages=3 表示测试阶段只爬前 3 页。
    如果跑通后想爬全部，可以改成 max_pages=None。
    """

    driver = create_driver()
    all_rows = []

    try:
        print("正在打开网页...")
        driver.get(PAGE_URL)
        time.sleep(6)

        print("正在请求第1页数据...")
        first_data = fetch_page_by_browser(driver, page=0, size=PAGE_SIZE)

        if not first_data:
            print("第1页获取失败：返回为空")
            return pd.DataFrame()

        if "error" in first_data:
            print("第1页获取失败：", first_data["error"])
            return pd.DataFrame()

        total_pages = first_data.get("totalPages", 1)
        total_elements = first_data.get("totalElements", 0)

        print("网站总页数：", total_pages)
        print("网站总记录数：", total_elements)

        if max_pages is not None:
            total_pages = min(total_pages, max_pages)

        rows = first_data.get("content", [])
        all_rows.extend(rows)

        print(f"第1页完成，获取 {len(rows)} 条")

        for page in range(1, total_pages):
            print(f"正在爬取第{page + 1}页...")

            data = fetch_page_by_browser(driver, page=page, size=PAGE_SIZE)

            if not data:
                print(f"第{page + 1}页失败：返回为空")
                continue

            if "error" in data:
                print(f"第{page + 1}页失败：", data["error"])
                continue

            rows = data.get("content", [])
            all_rows.extend(rows)

            print(f"第{page + 1}页完成，获取 {len(rows)} 条，累计 {len(all_rows)} 条")

            time.sleep(random.uniform(1, 2))

    finally:
        driver.quit()

    return pd.DataFrame(all_rows)


# =========================
# 6. 数据清洗函数
# =========================

def timestamp_to_date(value):
    """
    把毫秒时间戳转为日期。
    """
    if pd.isna(value):
        return None

    try:
        value = int(value)
        if value <= 0:
            return None
        return pd.to_datetime(value, unit="ms").strftime("%Y-%m-%d")
    except Exception:
        return value


def convert_bool(value):
    """
    把 True/False 转成 是/否。
    """
    if value is True:
        return "是"
    if value is False:
        return "否"

    value_str = str(value).lower()

    if value_str == "true":
        return "是"
    if value_str == "false":
        return "否"

    return value


def fund_scale_to_range(value):
    """
    根据基金规模数值生成规模区间。
    注意：这里主要用于完成“基金规模筛选”的测试。
    具体单位以中基协接口实际口径为准。
    """

    try:
        value = float(value)
    except Exception:
        return "未知"

    if value >= 1000000:
        return "100亿元以上"
    elif value >= 500000:
        return "50-100亿元"
    elif value >= 200000:
        return "20-50亿元"
    elif value >= 100000:
        return "10-20亿元"
    elif value >= 50000:
        return "5-10亿元"
    elif value > 0:
        return "0-5亿元"
    else:
        return "0或未披露"


def clean_data(df):
    """
    清洗数据：
    1. 保留常用字段
    2. 英文字段名改成中文
    3. 日期格式转换
    4. True/False 转成 是/否
    5. 生成基金规模区间
    """

    if df.empty:
        return df

    print("接口返回原始字段：")
    print(df.columns.tolist())

    keep_cols = [col for col in COLUMN_MAP if col in df.columns]
    df = df[keep_cols].copy()

    df = df.rename(columns=COLUMN_MAP)

    for date_col in ["成立时间", "登记时间"]:
        if date_col in df.columns:
            df[date_col] = df[date_col].apply(timestamp_to_date)

    for bool_col in ["是否有提示信息", "是否有诚信信息", "是否在黑名单"]:
        if bool_col in df.columns:
            df[bool_col] = df[bool_col].apply(convert_bool)

    if "基金规模" in df.columns:
        df["基金规模区间"] = df["基金规模"].apply(fund_scale_to_range)
    else:
        print("接口返回数据中没有 fundScale 字段，暂时无法生成基金规模区间。")

    return df


# =========================
# 7. 筛选函数
# =========================

def filter_data(df, institution_type=None, fund_scale_range=None, selected_fields=None):
    """
    支持：
    1. 机构类型筛选
    2. 基金规模筛选
    3. 字段筛选
    """

    if df.empty:
        return df

    result = df.copy()

    # 1. 机构类型筛选
    if institution_type:
        if "机构类型" in result.columns:
            result = result[
                result["机构类型"].astype(str).str.contains(institution_type, na=False)
            ]
        else:
            print("没有找到字段：机构类型")

    # 2. 基金规模筛选
    if fund_scale_range:
        if "基金规模区间" in result.columns:
            result = result[result["基金规模区间"] == fund_scale_range]
        else:
            print("没有找到字段：基金规模区间，无法按基金规模筛选。")

    # 3. 字段筛选
    if selected_fields:
        existing_fields = [field for field in selected_fields if field in result.columns]
        missing_fields = [field for field in selected_fields if field not in result.columns]

        if missing_fields:
            print("以下字段不存在，已跳过：", missing_fields)

        result = result[existing_fields]

    return result


# =========================
# 8. 写入数据库
# =========================

def write_to_database(df):
    """
    写入 SQLite 数据库。
    会在当前运行目录生成 amac_private_fund.db。
    """

    engine = create_engine("sqlite:///amac_private_fund.db")

    df.to_sql(
        name="private_fund_managers",
        con=engine,
        if_exists="replace",
        index=False
    )

    print("数据已写入数据库：amac_private_fund.db")
    print("数据表名称：private_fund_managers")
    print("写入数据行数：", len(df))


# =========================
# 9. 主程序
# =========================

def main():
    # 测试阶段先只爬前 3 页
    raw_df = crawl_data(max_pages=3)

    if raw_df.empty:
        print("没有获取到数据。")
        return

    print("原始数据行列数：", raw_df.shape)

    clean_df = clean_data(raw_df)

    print("清洗后字段：")
    print(clean_df.columns.tolist())

    # =========================
    # 这里修改筛选条件
    # =========================

    # 机构类型筛选
    institution_type = "私募证券投资基金管理人"

    # 基金规模筛选
    # 可选值：
    # "100亿元以上"
    # "50-100亿元"
    # "20-50亿元"
    # "10-20亿元"
    # "5-10亿元"
    # "0-5亿元"
    # None 表示不按基金规模筛选
    fund_scale_range = None

    # 字段筛选
    selected_fields = [
        "私募基金管理人名称",
        "法定代表人/执行事务合伙人(委派代表)姓名",
        "机构类型",
        "登记编号",
        "注册地",
        "办公地",
        "成立时间",
        "登记时间",
        "在管基金数量",
        "基金规模",
        "基金规模区间",
        "是否有提示信息",
        "是否有诚信信息",
    ]

    result_df = filter_data(
        df=clean_df,
        institution_type=institution_type,
        fund_scale_range=fund_scale_range,
        selected_fields=selected_fields
    )

    print("筛选后数据行数：", len(result_df))
    print(result_df.head())

    # 写入数据库
    write_to_database(result_df)

    # 导出 CSV 和 Excel，方便检查
    result_df.to_csv("private_fund_managers.csv", index=False, encoding="utf-8-sig")
    result_df.to_excel("private_fund_managers.xlsx", index=False)

    print("已导出：private_fund_managers.csv")
    print("已导出：private_fund_managers.xlsx")


if __name__ == "__main__":
    main()