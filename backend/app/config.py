"""
全局配置。

业务库里的表按品牌分表，命名规律：品牌简写_表类型（如 kp_order）。
新增品牌时在 BRANDS 里照抄一段、改表名即可，业务代码不用动。

列名映射分两层：
- COLUMNS：全局默认（按多数品牌的列名取值）
- BRANDS[品牌]["columns"]：品牌级覆盖，只写和全局不一样的差异项
  - 同一含义不同列名：kp_order 的"下单分类"与 xj_order 的"下单时间分类"都映射到逻辑名 meal_type；
    kp/xj/zz 的"城市/战区/大区"都映射到逻辑名 region
  - 某品牌独有的列只写在它自己的覆盖里（如 xj 的 org_code）
  - 值写 None 表示该品牌没有这个列（如 kp_order 没有订单编号 -> "order_id": None）
查询只会 SELECT 用到的逻辑字段，没登记的列自动忽略。
"""
import os

from dotenv import load_dotenv

load_dotenv()

# 基础配置
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./demo.db",  # 仅当未设置 DATABASE_URL 时的回退；正常由 backend/.env 指向 MySQL
)
APP_DB_URL = os.getenv(
    "APP_DB_URL",
    "sqlite:///./app.db",  # 程序自身的数据（用户/授权表）；线上与业务库同一个 MySQL 的独立库
)
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "12"))

# AI 自由问答（云端 OpenAI 兼容；只经白名单聚合工具取数，不给模型 DB/SQL）
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() in ("1", "true", "yes")
AI_API_BASE = os.getenv("AI_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_MAX_TOOL_ROUNDS = int(os.getenv("AI_MAX_TOOL_ROUNDS", "4"))
AI_RATE_LIMIT_PER_MIN = int(os.getenv("AI_RATE_LIMIT_PER_MIN", "10"))

# 品牌注册表：key 为品牌简写（与业务表前缀一致），label 为页面显示名
BRANDS: dict[str, dict] = {
    "kp": {
        "label": "品牌1",
        "tables": {
            "order": "kp_order",      # 订单表
            "product": "kp_product",  # 商品表
            "account": "kp_account",  # 销售数据表
            "exposure": "kp_exposure",  # 曝光数据表
            "info": "kp_info",        # 品牌信息表
            "profit": "kp_profit",    # 品牌利润表
            "activity": "kp_activity",  # 营销活动拆解（按日/门店/活动分类）
        },
        # 本品牌与全局默认不一致的列，只写差异项（None = 该品牌没有此列）
        "columns": {
            "order": {
                "order_id": None,  # kp_order 没有订单编号列，计数类查询退化为按行数
                "region": "城市",
            },
            "product": {
                "region": "城市",
            },
            "account": {
                "region": "城市",
            },
            "exposure": {
                "region": "城市",
            },
        },
    },
    "xj": {
        "label": "品牌2",
        "tables": {
            "order": "xj_order",
            "product": "xj_product",
            "account": "xj_account",  # 销售数据表
            "exposure": "xj_exposure",  # 曝光数据表
            "info": "xj_info",        # 品牌信息表
            "abnormal": "xj_abnormal",  # 美团异常订单（店铺ID = 美团门店 ID）
        },
        "columns": {
            "order": {
                "store_id": "店铺ID",        # xj 的门店列叫"店铺ID"
                "meal_type": "下单时间分类",  # xj 的时段分类列叫"下单时间分类"
                "is_activity": None,        # xj_order 没有"是否参加活动"
                "region": "战区",
                "org_code": "机构编码",      # xj 独有
            },
            "product": {
                "store_id": "店铺ID",
                "qty": "商品销售数量",
                "date": "下单时间",  # xj 商品表用"下单时间"做日期列
                "region": "战区",
                "org_code": "机构编码",
                "category": "商品分类",
            },
            "account": {
                "region": "战区",
                "org_code": "机构编码",
            },
            "exposure": {
                "region": "战区",
                "org_code": "机构编码",
                # xj 流量源没有新客/老客拆分，导入也不产出这两列
                "new_customers": None,
                "old_customers": None,
            },
        },
    },
    "zz": {
        "label": "品牌3",
        "tables": {
            "order": "zz_order",
            "product": "zz_product",
            "account": "zz_account",
            "exposure": "zz_exposure",
            "info": "zz_info",
        },
        "columns": {
            "order": {
                "region": "大区",
            },
            "product": {
                "region": "大区",
            },
            "account": {
                "region": "大区",
            },
            "exposure": {
                "region": "大区",
            },
        },
    },
}

# 逻辑字段 -> 实际列名映射（按表类型），取多数品牌的列名做全局默认；差异项写在 BRANDS[品牌]["columns"] 里
COLUMNS: dict[str, dict[str, str]] = {
    "account": {  # 销售数据表
        "id": "id",
        "date": "日期",
        "store_id": "门店id",
        "store_name": "门店名称",
        "platform": "平台",
        "revenue": "营业额",
        "orders": "有效订单数",
        "commission": "平台佣金",
        "subsidy": "商家补贴金额",
        "income": "收入",
        "create_time": "创建时间",
    },
    "order": {  # 订单表（按 kp/zz 多数取默认，xj 差异在其覆盖里）
        "id": "id",
        "order_id": "订单编号",       # kp 没有 -> 覆盖 None
        "time": "下单时间",
        "store_id": "门店id",         # xj 叫"店铺ID"
        "store_name": "门店名称",
        "platform": "平台",
        "meal_type": "下单分类",      # xj 叫"下单时间分类"
        "amount": "订单金额",
        "paid": "订单实付",
        "is_activity": "是否参加活动",  # xj 没有 -> 覆盖 None
        "amount_class": "下单金额分类",
        "paid_class": "订单实付分类",
    },
    "product": {  # 商品表（kp/zz 用默认，xj 差异在其覆盖里）
        "id": "id",
        "date": "日期",              # xj 用"下单时间"
        "store_id": "门店id",         # xj 叫"店铺ID"
        "store_name": "门店名称",
        "platform": "平台",
        "name": "商品名称",
        "qty": "商品销量",            # xj 叫"商品销售数量"
        "amount": "商品销售额",
        "create_time": "创建时间",
    },
    "exposure": {  # 曝光/流量表
        "date": "日期",
        "store_id": "门店id",
        "store_name": "门店名称",
        "platform": "平台",
        "exposure": "曝光人数",
        "visitors": "入店人数",
        "orderers": "下单人数",
        "new_customers": "下单新客人数",
        "old_customers": "下单老客人数",
        "create_time": "创建时间",
    },
    "info": {  # 品牌/门店信息表
        "id": "id",
        "store_name": "机构名称",
        "p_id": "pid",
        "create_time": "创建时间",
    },
    "activity": {  # 营销活动表（目前仅 kp；一单多活动时营业额会分别计入各类）
        "id": "id",
        "date": "日期",
        "store_id": "门店id",
        "store_name": "门店名称",
        "platform": "平台",
        "category": "活动分类",
        "revenue": "营业额",
        "merchant_spend": "商家活动支出",
        "orders": "订单数",
        "region": "城市",
        "create_time": "创建时间",
    },
    "abnormal": {  # 异常订单（当前仅 xj 美团；店铺ID 为美团门店 ID）
        "id": "id",
        "order_id": "订单编号",
        "time": "下单时间",
        "store_id": "店铺ID",
        "store_name": "门店名称",
        "platform": "平台",
        "issue": "商家服务问题",
        "create_time": "创建时间",
    },
    "profit": {  # 利润表
        "id": "id",
        "order_id": "订单单号",
        "settlement_amount": "结算金额",
        "revenue": "营业额",
        "store_id": "门店ID",
        "store_name": "门店名称",
        "bill_date": "账单日期",
        "offline_revenue": "线下营业额",
        "cost_amount": "成本金额",
        "cost_rate": "结算占比",
        "profit_amount": "利润",
        "profit_rate": "利润率",
        "city": "城市",
        "platform": "平台",
        "create_time": "创建时间",
    },
}


def get_brand(brand: str) -> dict | None:
    """获取品牌配置。"""
    return BRANDS.get(brand)


def table_name(brand: str, ttype: str) -> str:
    """获取品牌表名。"""
    return BRANDS[brand]["tables"][ttype]


def has_table(brand: str, ttype: str) -> bool:
    """该品牌是否配置了某类业务表（如 kp 独有 profit）。"""
    return ttype in BRANDS.get(brand, {}).get("tables", {})


def brand_columns(brand: str, ttype: str) -> dict[str, str]:
    """列名解析：品牌级覆盖优先，未覆盖的用全局默认。"""
    cols = dict(COLUMNS.get(ttype, {}))
    cols.update(BRANDS.get(brand, {}).get("columns", {}).get(ttype, {}))
    return cols


def col(ttype: str, key: str) -> str:
    """全局默认列名（不带品牌覆盖；业务查询请用 brand_columns）。"""
    return COLUMNS[ttype][key]
