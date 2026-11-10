"""业务库导入工具：列类型 / 索引 / 按日覆盖，与 backend config + 看板查询对齐。

设计目标：
1. 列名保持中文业务名（与 config.COLUMNS / brand_columns 一致）
2. 日粒度字段用 DATE，订单时间用 DATETIME，金额用 DECIMAL，ID/平台用 VARCHAR
3. 为看板热路径 (日期/下单时间, 平台, 门店id) 建复合索引
4. append 时按日期区间覆盖，避免重复导入翻倍
5. 每次导入只快照被改到的行；作废最近一次导入时恢复这些行，其余历史数据不动
6. 写库前先把同一份数据导出到 DataProcess 2/data_export（与 data 同级，不进仓库）。写库失败或回滚数据库时不删除这些文件
"""
from __future__ import annotations

import logging
import os
import re
import sys
import uuid
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # 无 python-dotenv 时仍可用系统环境变量

logger = logging.getLogger(__name__)

# 与 DataProcess 2/data 同级。每次导入成功后覆盖写出，目录不存在则创建。
DATA_EXPORT_DIR = Path(__file__).resolve().parent.parent / "data_export"

# 日粒度列 -> MySQL DATE（account / product / exposure / profit）
DATE_COLUMNS = {"日期", "账单日期"}
# 含时分秒 -> DATETIME
DATETIME_COLUMNS = {"下单时间", "创建时间", "订单完成/退款完成时间"}
# 金额 / 比率
MONEY_COLUMNS = {
    "营业额", "收入", "平台佣金", "商家补贴金额", "订单金额", "订单实付",
    "商品销售额", "结算金额", "线下营业额", "成本金额", "利润",
    "结算占比", "利润率", "商家活动支出",
}
# 计数类
INT_COLUMNS = {
    "有效订单数", "商品销量", "商品销售数量", "曝光人数", "入店人数",
    "下单人数", "下单新客人数", "下单老客人数", "销量", "订单数",
}
# 门店 / 订单标识 -> 统一存字符串，避免 float 与前端筛选对不上
ID_COLUMNS = {
    "门店id", "门店ID", "店铺ID", "门店编号", "订单编号", "订单单号",
    "机构编码", "美团门店ID", "饿了么门店ID", "京东门店ID", "pid",
}
VARCHAR_COLUMNS = {
    "平台": 16,
    "门店名称": 128,
    "机构名称": 128,
    "商品名称": 255,
    "商品分类": 64,
    "下单分类": 16,
    "下单时间分类": 16,
    "下单金额分类": 32,
    "订单实付分类": 32,
    "是否参加活动": 8,
    "城市": 64,
    "战区": 64,
    "大区": 64,
    "品牌": 64,
    "商家服务问题": 64,
}

# 流量表列名：导入侧统一成 config 登记名
EXPOSURE_RENAME = {
    "下单新客": "下单新客人数",
    "下单老客": "下单老客人数",
}

# 表类型 -> 用于选日期列做按日覆盖
TABLE_DATE_COL = {
    "account": "日期",
    "product": "日期",  # xj_product 实际是「下单时间」，见 _resolve_date_column
    "exposure": "日期",
    "order": "下单时间",
    "profit": "账单日期",
    "abnormal": "下单时间",
    "activity": "日期",
}


def _beijing_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


def _table_type(table_name: str) -> str:
    """kp_account -> account"""
    if "_" not in table_name:
        return ""
    return table_name.split("_", 1)[1]


def _max_str_len(series: pd.Series) -> int:
    """Unicode 字符长度（utf8mb4 下 VARCHAR(n) 的 n）。"""
    s = series.dropna()
    if s.empty:
        return 0
    return int(s.astype(str).map(len).max())


def _varchar_len(col_name: str, series: Optional[pd.Series] = None, default: int = 255) -> int:
    """登记下限 + 实际数据长度，向上取整到 8 的倍数，避免 Data too long。"""
    base = VARCHAR_COLUMNS.get(col_name)
    if col_name in ID_COLUMNS:
        base = 64 if base is None else base
    if base is None:
        base = default
    need = _max_str_len(series) if series is not None else 0
    # 预留余量，且不超过 MySQL utf8mb4 单列索引友好上限
    size = max(base, need + 8)
    size = min(max(8, (size + 7) // 8 * 8), 1024)
    return size


def _mysql_type(col_name: str, dtype, series: Optional[pd.Series] = None) -> str:
    """按列名优先、dtype 兜底，映射成适合索引与聚合的 MySQL 类型。"""
    if col_name in DATE_COLUMNS:
        return "DATE"
    if col_name in DATETIME_COLUMNS:
        return "DATETIME"
    if col_name in ID_COLUMNS:
        return f"VARCHAR({_varchar_len(col_name, series, default=64)})"
    if col_name in VARCHAR_COLUMNS:
        return f"VARCHAR({_varchar_len(col_name, series)})"
    if col_name in MONEY_COLUMNS:
        return "DECIMAL(14,4)" if col_name.endswith("率") or col_name.endswith("占比") else "DECIMAL(14,2)"
    if col_name in INT_COLUMNS:
        return "INT"

    dtype_str = str(dtype)
    if "datetime" in dtype_str or "date" in dtype_str:
        return "DATE" if "日期" in col_name else "DATETIME"
    if "int" in dtype_str:
        return "BIGINT" if "订单" in col_name or "编号" in col_name else "INT"
    if "float" in dtype_str:
        return "DECIMAL(14,2)"
    if "bool" in dtype_str:
        return "TINYINT(1)"
    return f"VARCHAR({_varchar_len(col_name, series, default=255)})"

def _suggest_indexes(table_name: str, columns: list[str]) -> list[tuple[str, list[str]]]:
    """看板热路径索引：(日期/时间, 平台, 门店) + 门店维度。"""
    cols = set(columns)
    ttype = _table_type(table_name)
    indexes: list[tuple[str, list[str]]] = []

    date_col = None
    for c in ("日期", "账单日期", "下单时间"):
        if c in cols:
            date_col = c
            break
    plat = "平台" if "平台" in cols else None
    store = next((c for c in ("门店id", "店铺ID", "门店ID") if c in cols), None)

    if date_col and plat and store:
        indexes.append((f"idx_{table_name}_query", [date_col, plat, store]))
    elif date_col and store:
        indexes.append((f"idx_{table_name}_date_store", [date_col, store]))
    elif date_col:
        indexes.append((f"idx_{table_name}_date", [date_col]))

    if store and ttype in ("account", "order", "product", "exposure"):
        indexes.append((f"idx_{table_name}_store", [store]))

    meal = next((c for c in ("下单分类", "下单时间分类") if c in cols), None)
    if meal and ttype == "order":
        indexes.append((f"idx_{table_name}_meal", [meal]))

    order_id = next((c for c in ("订单编号", "订单单号") if c in cols), None)
    if order_id:
        indexes.append((f"idx_{table_name}_oid", [order_id]))

    return indexes


def _stringify_id(series: pd.Series) -> pd.Series:
    """门店/订单 ID 统一成干净字符串（去掉 Excel 读入的 .0）。"""
    def _one(v):
        if pd.isna(v):
            return None
        if isinstance(v, float):
            if v.is_integer():
                return str(int(v))
            return str(v).rstrip("0").rstrip(".") if "." in str(v) else str(v)
        s = str(v).strip()
        if re.fullmatch(r"\d+\.0+", s):
            return s.split(".", 1)[0]
        return s or None

    return series.map(_one)


def normalize_dataframe(df: pd.DataFrame, table_name: str = "") -> pd.DataFrame:
    """导入前规范化：列名对齐 config、ID 字符串化、日期类型、去首尾空格。"""
    out = df.copy()
    out = out.rename(columns=EXPOSURE_RENAME)

    for col in out.select_dtypes(include=["object", "string"]).columns:
        out[col] = out[col].map(lambda x: x.rstrip() if isinstance(x, str) else x)

    for col in out.columns:
        if col in ID_COLUMNS:
            out[col] = _stringify_id(out[col])
        elif col in DATE_COLUMNS:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.normalize()
            out[col] = out[col].dt.date
        elif col in DATETIME_COLUMNS:
            out[col] = pd.to_datetime(out[col], errors="coerce")
            ttype = _table_type(table_name)
            # xj_product 的「下单时间」在 config 里当日期用
            if ttype == "product" and col == "下单时间":
                out[col] = out[col].dt.normalize()

    for col in out.columns:
        if col in MONEY_COLUMNS or col in INT_COLUMNS:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    return out


def _resolve_date_column(df: pd.DataFrame, table_name: str, explicit: Optional[str] = None) -> Optional[str]:
    if explicit and explicit in df.columns:
        return explicit
    ttype = _table_type(table_name)
    preferred = TABLE_DATE_COL.get(ttype)
    if preferred and preferred in df.columns:
        return preferred
    if ttype == "product" and "下单时间" in df.columns:
        return "下单时间"
    for c in ("日期", "下单时间", "账单日期"):
        if c in df.columns:
            return c
    return None


# 最近一次导入的撤销记录。快照表只保存本次覆盖掉的旧行。
UNDO_LOG = "_import_undo"


def export_table_to_local(
    df: pd.DataFrame,
    table_name: str,
    export_dir: Path | None = None,
) -> Path:
    """把即将写入数据库的表落一份 CSV 到 data_export。没有目录则创建。

    写库失败、批次回滚都不会删除这里的文件，方便对照排查。
    """
    out_dir = export_dir or DATA_EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w]+", "_", table_name).strip("_") or "table"
    path = out_dir / f"{safe}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info("已导出本地 %s -> %s（%s 行）", table_name, path, len(df))
    return path


def begin_import_batch() -> str:
    """开始一次导入。同一批里的多张表共用这个 id，才能一次作废。"""
    return uuid.uuid4().hex


def _q(name: str) -> str:
    if not name or "`" in name or "\x00" in name:
        raise ValueError(f"非法标识符: {name!r}")
    return f"`{name}`"


def _batch_suffix(batch_id: str) -> str:
    return batch_id.replace("-", "")[:12]


def _undo_table_name(table_name: str, batch_id: str) -> str:
    return f"{table_name}__u_{_batch_suffix(batch_id)}"


def _stage_table_name(table_name: str, batch_id: str) -> str:
    return f"{table_name}__s_{_batch_suffix(batch_id)}"


def _date_window(df: pd.DataFrame, date_column: str) -> tuple[date, date]:
    """本次数据覆盖的日期区间 [start, end_exclusive)。"""
    series = df[date_column].dropna()
    if series.empty:
        raise ValueError(f"列 {date_column} 没有可用日期，无法按日覆盖")
    min_d, max_d = series.min(), series.max()
    if isinstance(min_d, datetime):
        min_d = min_d.date()
    if isinstance(max_d, datetime):
        max_d = max_d.date()
    if hasattr(min_d, "to_pydatetime"):
        min_d = min_d.to_pydatetime().date()
    if hasattr(max_d, "to_pydatetime"):
        max_d = max_d.to_pydatetime().date()
    if not isinstance(min_d, date) or not isinstance(max_d, date):
        raise ValueError(f"列 {date_column} 无法解析成日期")
    return min_d, max_d + timedelta(days=1)


class DataFrameToMySQLWithMetadata:
    """将 DataFrame 写入业务库，自动建规范类型 + 索引，支持按日覆盖。"""

    def __init__(
        self,
        host: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        port: int | None = None,
        charset: str = "utf8mb4",
    ):
        self.host = host or os.getenv("MYSQL_HOST", "127.0.0.1")
        self.user = user or os.getenv("MYSQL_USER", "root")
        self.password = password if password is not None else os.getenv("MYSQL_PASSWORD", "")
        self.database = database or os.getenv("MYSQL_DATABASE", "fastapi_db")
        self.port = port or int(os.getenv("MYSQL_PORT", "3306"))
        self.charset = charset

    def _create_sqlalchemy_engine(self):
        connection_str = (
            f"mysql+mysqlconnector://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )
        return create_engine(connection_str, echo=False, pool_pre_ping=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def _table_exists(self, engine, table_name: str) -> bool:
        with engine.connect() as conn:
            row = conn.execute(text("SHOW TABLES LIKE :t"), {"t": table_name}).fetchone()
            return row is not None

    def _create_table(
        self,
        engine,
        table_name: str,
        df: pd.DataFrame,
        id_column_name: str,
        created_at_column_name: str,
        add_id_column: bool,
        add_created_at: bool,
    ):
        defs: list[str] = []
        if add_id_column:
            defs.append(f"`{id_column_name}` BIGINT AUTO_INCREMENT PRIMARY KEY")

        for col_name, dtype in df.dtypes.items():
            if add_id_column and col_name == id_column_name:
                continue
            mysql_t = _mysql_type(col_name, dtype, df[col_name])
            # info 等表：保留 Excel 业务 id 作为主键（非自增）
            if (
                not add_id_column
                and col_name == id_column_name
                and id_column_name in df.columns
            ):
                defs.append(f"`{col_name}` {mysql_t} NOT NULL PRIMARY KEY")
            else:
                defs.append(f"`{col_name}` {mysql_t} NULL")

        # export_dataframe 已把创建时间写进 df 时，勿再追加同名列
        if add_created_at and created_at_column_name not in df.columns:
            defs.append(f"`{created_at_column_name}` DATETIME NULL")

        index_cols = [c for c in df.columns if not (add_id_column and c == id_column_name)]
        for idx_name, cols in _suggest_indexes(table_name, index_cols):
            col_sql = ", ".join(f"`{c}`" for c in cols)
            defs.append(f"KEY `{idx_name}` ({col_sql})")

        ddl = (
            f"CREATE TABLE `{table_name}` ({', '.join(defs)}) "
            f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        )
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            conn.execute(text(ddl))
        logger.info("已建表 %s（含业务索引）", table_name)

    def _ensure_indexes(self, engine, table_name: str, df: pd.DataFrame):
        """表已存在时补齐缺失索引（不改列类型，避免破坏线上数据）。"""
        with engine.connect() as conn:
            existing = {
                r[2]  # Key_name；第 0 列是表名
                for r in conn.execute(text(f"SHOW INDEX FROM `{table_name}`")).fetchall()
            }
        for idx_name, cols in _suggest_indexes(table_name, list(df.columns)):
            if idx_name in existing:
                continue
            with engine.connect() as conn:
                table_cols = {
                    r[0]
                    for r in conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`")).fetchall()
                }
            if not all(c in table_cols for c in cols):
                logger.warning("跳过索引 %s：表 %s 缺少列 %s", idx_name, table_name, cols)
                continue
            col_sql = ", ".join(f"`{c}`" for c in cols)
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"CREATE INDEX `{idx_name}` ON `{table_name}` ({col_sql})"))
                logger.info("已补索引 %s ON %s", idx_name, table_name)
            except Exception as e:
                logger.warning("创建索引 %s 失败: %s", idx_name, e)

    def _drop_table(self, engine, table_name: str | None) -> None:
        if not table_name:
            return
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {_q(table_name)}"))

    def _ensure_undo_log(self, engine) -> None:
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {_q(UNDO_LOG)} (
            `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `batch_id` VARCHAR(32) NOT NULL,
            `table_name` VARCHAR(64) NOT NULL,
            `mode` VARCHAR(16) NOT NULL,
            `date_column` VARCHAR(64) NULL,
            `range_start` DATETIME NULL,
            `range_end` DATETIME NULL,
            `undo_table` VARCHAR(64) NULL,
            `created_at` DATETIME NOT NULL,
            KEY `idx_import_undo_batch` (`batch_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        with engine.begin() as conn:
            conn.execute(text(ddl))

    def _load_chunks(self, engine, table_name: str, data: pd.DataFrame, chunksize: int) -> None:
        total = len(data)
        n_chunks = (total + chunksize - 1) // chunksize
        logger.info("导入 %s：%s 行 / %s 块", table_name, total, n_chunks)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i, start in enumerate(range(0, total, chunksize)):
                chunk = data.iloc[start : start + chunksize]
                chunk.to_sql(
                    name=table_name,
                    con=engine,
                    if_exists="append",
                    index=False,
                    method="multi",
                )
                logger.info("  %s 块 %s/%s", table_name, i + 1, n_chunks)

    def _log_undo(
        self,
        conn,
        batch_id: str,
        table_name: str,
        mode: str,
        date_column: str | None,
        range_start,
        range_end,
        undo_table: str | None,
    ) -> None:
        conn.execute(
            text(
                f"INSERT INTO {_q(UNDO_LOG)} "
                "(batch_id, table_name, mode, date_column, range_start, range_end, undo_table, created_at) "
                "VALUES (:batch_id, :table_name, :mode, :date_column, :range_start, :range_end, :undo_table, :created_at)"
            ),
            {
                "batch_id": batch_id,
                "table_name": table_name,
                "mode": mode,
                "date_column": date_column,
                "range_start": range_start,
                "range_end": range_end,
                "undo_table": undo_table,
                "created_at": _beijing_now(),
            },
        )

    def _write_new_table(self, engine, table_name, data, chunksize, id_column_name, created_at_column_name, add_id_column, add_created_at, batch_id) -> None:
        """表不存在：建表并写入。失败则删掉这张新表。"""
        try:
            self._create_table(
                engine, table_name, data,
                id_column_name, created_at_column_name,
                add_id_column, add_created_at,
            )
            self._load_chunks(engine, table_name, data, chunksize)
            with engine.begin() as conn:
                self._log_undo(conn, batch_id, table_name, "created", None, None, None, None)
        except Exception:
            self._drop_table(engine, table_name)
            raise

    def _replace_table(self, engine, table_name, data, chunksize, id_column_name, created_at_column_name, add_id_column, add_created_at, batch_id) -> None:
        """整表换成新数据。旧表改名留作撤销快照，失败时原表还在。"""
        stage = _stage_table_name(table_name, batch_id)
        undo = _undo_table_name(table_name, batch_id)
        self._drop_table(engine, stage)
        self._drop_table(engine, undo)
        try:
            self._create_table(
                engine, stage, data,
                id_column_name, created_at_column_name,
                add_id_column, add_created_at,
            )
            self._load_chunks(engine, stage, data, chunksize)
            with engine.begin() as conn:
                conn.execute(text(
                    f"RENAME TABLE {_q(table_name)} TO {_q(undo)}, {_q(stage)} TO {_q(table_name)}"
                ))
            with engine.begin() as conn:
                self._log_undo(conn, batch_id, table_name, "renamed", None, None, None, undo)
            logger.info("整表替换 %s，旧表保留为 %s", table_name, undo)
        except Exception:
            # 换名还没发生时，删掉半成品；换名成功但记账失败时把旧表换回来
            if self._table_exists(engine, undo) and self._table_exists(engine, table_name):
                discard = f"{stage}_discard"
                with engine.begin() as conn:
                    conn.execute(text(
                        f"RENAME TABLE {_q(table_name)} TO {_q(discard)}, {_q(undo)} TO {_q(table_name)}"
                    ))
                self._drop_table(engine, discard)
            self._drop_table(engine, stage)
            self._drop_table(engine, undo)
            raise

    def _replace_dates(self, engine, table_name, data, chunksize, batch_id, date_column: str) -> None:
        """只替换本次日期区间。先把旧行复制到快照，再在一个事务里删旧插新。"""
        start, end_exclusive = _date_window(data, date_column)
        stage = _stage_table_name(table_name, batch_id)
        undo = _undo_table_name(table_name, batch_id)
        cols = ", ".join(_q(c) for c in data.columns)
        self._drop_table(engine, stage)
        self._drop_table(engine, undo)
        try:
            with engine.begin() as conn:
                conn.execute(text(f"CREATE TABLE {_q(stage)} LIKE {_q(table_name)}"))
                conn.execute(text(f"CREATE TABLE {_q(undo)} LIKE {_q(table_name)}"))
                conn.execute(
                    text(
                        f"INSERT INTO {_q(undo)} SELECT * FROM {_q(table_name)} "
                        f"WHERE {_q(date_column)} >= :start AND {_q(date_column)} < :end_exclusive"
                    ),
                    {"start": start, "end_exclusive": end_exclusive},
                )
            self._load_chunks(engine, stage, data, chunksize)
            with engine.begin() as conn:
                deleted = conn.execute(
                    text(
                        f"DELETE FROM {_q(table_name)} "
                        f"WHERE {_q(date_column)} >= :start AND {_q(date_column)} < :end_exclusive"
                    ),
                    {"start": start, "end_exclusive": end_exclusive},
                )
                conn.execute(text(
                    f"INSERT INTO {_q(table_name)} ({cols}) SELECT {cols} FROM {_q(stage)}"
                ))
                self._log_undo(
                    conn, batch_id, table_name, "date_replace",
                    date_column, start, end_exclusive, undo,
                )
            logger.info(
                "按日覆盖 %s [%s, %s)：替换 %s 行，旧行在 %s",
                table_name, start, end_exclusive, deleted.rowcount, undo,
            )
        except Exception:
            self._drop_table(engine, stage)
            self._drop_table(engine, undo)
            raise
        self._drop_table(engine, stage)

    def export_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        if_exists: str = "fail",
        add_id_column: bool = True,
        id_column_name: str = "id",
        add_created_at: bool = True,
        created_at_column_name: str = "创建时间",
        created_at_value: Optional[datetime] = None,
        chunksize: Optional[int] = 5000,
        normalize: bool = True,
        replace_date_overlap: bool = True,
        date_column: Optional[str] = None,
        batch_id: str | None = None,
    ) -> bool:
        """导出 DataFrame。

        if_exists:
          - replace: 整表换成新数据，旧表留下可撤销
          - append: 默认只覆盖本次日期区间，区间外的旧数据不动
          - fail: 表已存在则失败
        成功后可调用 rollback_last_import() 只撤销这一次。
        """
        if df is None or df.empty:
            logger.warning("DataFrame 为空，跳过 %s", table_name)
            return True

        batch_id = batch_id or begin_import_batch()
        chunksize = chunksize or 5000
        data = normalize_dataframe(df, table_name) if normalize else df.copy()

        if add_id_column and id_column_name in data.columns:
            logger.warning("DataFrame 已有 %s，写入时仍用库自增主键", id_column_name)
            data = data.drop(columns=[id_column_name])

        if add_created_at:
            data[created_at_column_name] = created_at_value or _beijing_now()

        # 先落本地。后面写库失败时文件仍留在 data_export，不随数据库回滚删除。
        export_table_to_local(data, table_name)

        engine = self._create_sqlalchemy_engine()
        try:
            self._ensure_undo_log(engine)
            exists = self._table_exists(engine, table_name)
            if if_exists == "fail" and exists:
                raise ValueError(f"表 {table_name} 已存在")

            if not exists:
                self._write_new_table(
                    engine, table_name, data, chunksize,
                    id_column_name, created_at_column_name,
                    add_id_column, add_created_at, batch_id,
                )
            elif if_exists == "replace":
                self._replace_table(
                    engine, table_name, data, chunksize,
                    id_column_name, created_at_column_name,
                    add_id_column, add_created_at, batch_id,
                )
            else:
                self._ensure_indexes(engine, table_name, data)
                dcol = _resolve_date_column(data, table_name, date_column) if replace_date_overlap else None
                if dcol:
                    self._replace_dates(engine, table_name, data, chunksize, batch_id, dcol)
                else:
                    logger.warning("表 %s 无法按日覆盖，改为整表替换并保留旧表", table_name)
                    self._replace_table(
                        engine, table_name, data, chunksize,
                        id_column_name, created_at_column_name,
                        add_id_column, add_created_at, batch_id,
                    )
            logger.info("完成 %s，行数 %s", table_name, len(data))
            return True
        except Exception as e:
            logger.error("导出 %s 失败: %s", table_name, e)
            raise
        finally:
            engine.dispose()


def _load_config():
    """加载 backend app.config，用于导入前列名校验。"""
    backend = Path(__file__).resolve().parents[2] / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.config import BRANDS, brand_columns  # noqa: WPS433
    return BRANDS, brand_columns


def parse_brand_table(table_name: str) -> tuple[str, str]:
    """kp_account -> (kp, account)。"""
    brand, _, ttype = table_name.partition("_")
    return brand, ttype


def validate_df_against_config(df: pd.DataFrame, table_name: str) -> None:
    """核对接 config.brand_columns：登记且非 None 的列，导入 DataFrame 必须有（id/创建时间除外）。"""
    BRANDS, brand_columns = _load_config()
    brand, ttype = parse_brand_table(table_name)
    if brand not in BRANDS or ttype not in BRANDS[brand]["tables"]:
        logger.warning("表 %s 不在 config.BRANDS 中，跳过列校验", table_name)
        return
    required = []
    for logical, actual in brand_columns(brand, ttype).items():
        if not actual:
            continue
        if logical in ("id", "create_time"):
            continue  # 写入时自动处理
        required.append(actual)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"表 {table_name} 与 config 不一致，缺少列: {missing}；"
            f"当前列: {list(df.columns)}"
        )
    logger.info("列校验通过 %s（config 必填 %s 列）", table_name, len(required))


def export_brand_tables(
    exporter: DataFrameToMySQLWithMetadata,
    tables: dict[str, pd.DataFrame],
    *,
    info_replace: bool = True,
    chunksize: int = 5000,
    force_rebuild: bool = True,
    validate: bool = True,
    batch_id: str | None = None,
    finalize_batch: bool = False,
) -> dict[str, bool]:
    """批量导出某一品牌的多张表（新库默认 force_rebuild=True 整表重建）。

    info 表：保留 Excel 业务 id/pid/机构名称，不再套自增主键挤掉 id。
    其余表：自增 id + 创建时间；force_rebuild 后带 DATE/DECIMAL/复合索引。
    同一 batch_id 的表算一次导入。中途失败只撤销本次已写入数据库的表，data_export 里的 CSV 保留。
    """
    batch_id = batch_id or begin_import_batch()
    results = {}
    applied: list[str] = []
    try:
        for table_name, df in tables.items():
            # 校验或写库失败时也留下原始表，且回滚数据库不删这个文件
            if df is not None:
                export_table_to_local(df, table_name)

            if validate:
                validate_df_against_config(df, table_name)

            ttype = _table_type(table_name)
            if force_rebuild or (ttype == "info" and info_replace):
                if_exists = "replace"
            else:
                if_exists = "append"
            replace_overlap = ttype != "info" and if_exists == "append"

            # info：Excel 已有 id/pid/机构名称，与 config 一致，勿 drop id
            add_id = ttype != "info"

            try:
                results[table_name] = exporter.export_dataframe(
                    df=df,
                    table_name=table_name,
                    if_exists=if_exists,
                    add_id_column=add_id,
                    id_column_name="id",
                    created_at_column_name="创建时间",
                    chunksize=chunksize,
                    replace_date_overlap=replace_overlap,
                    batch_id=batch_id,
                )
            except Exception:
                # 只回滚数据库。data_export 里已写出的 CSV 保留，用来看这次失败的数据。
                applied.append(table_name)
                raise
            applied.append(table_name)
        if finalize_batch:
            discard_previous_undo(exporter, batch_id)
        return results
    except Exception:
        logger.error(
            "导入失败，撤销本次已写入数据库的表: %s。本地 CSV 保留在 %s",
            applied, DATA_EXPORT_DIR,
        )
        if applied:
            try:
                rollback_import_tables(exporter, batch_id, applied)
            except Exception:
                logger.exception("撤销本次导入失败，旧数据可能仍在快照表里")
        raise


def _undo_rows(engine, batch_id: str, table_names: list[str] | None):
    sql = f"SELECT id, table_name, mode, date_column, range_start, range_end, undo_table FROM {_q(UNDO_LOG)} WHERE batch_id = :batch_id"
    params: dict = {"batch_id": batch_id}
    if table_names is not None:
        if not table_names:
            return []
        holders = ", ".join(f":t{i}" for i in range(len(table_names)))
        sql += f" AND table_name IN ({holders})"
        params.update({f"t{i}": name for i, name in enumerate(table_names)})
    sql += " ORDER BY id DESC"
    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).mappings())


def _restore_undo_row(engine, row) -> None:
    """把一行撤销记录对应的表恢复到导入前。"""
    live = row["table_name"]
    mode = row["mode"]
    undo = row["undo_table"]
    if mode == "created":
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {_q(live)}"))
    elif mode == "renamed":
        if not undo or not _table_exists_engine(engine, undo):
            raise RuntimeError(f"找不到 {live} 的旧表快照，无法撤销")
        discard = f"{live}__discard_{_batch_suffix(str(row['id']))}"
        with engine.begin() as conn:
            conn.execute(text(
                f"RENAME TABLE {_q(live)} TO {_q(discard)}, {_q(undo)} TO {_q(live)}"
            ))
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {_q(discard)}"))
    elif mode == "date_replace":
        if not undo or not _table_exists_engine(engine, undo):
            raise RuntimeError(f"找不到 {live} 的日期快照，无法撤销")
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"DELETE FROM {_q(live)} WHERE {_q(row['date_column'])} >= :start "
                    f"AND {_q(row['date_column'])} < :end_exclusive"
                ),
                {"start": row["range_start"], "end_exclusive": row["range_end"]},
            )
            conn.execute(text(f"INSERT INTO {_q(live)} SELECT * FROM {_q(undo)}"))
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {_q(undo)}"))
    else:
        raise RuntimeError(f"未知撤销类型: {mode}")
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {_q(UNDO_LOG)} WHERE id = :id"), {"id": row["id"]})
    logger.info("已撤销 %s（%s）", live, mode)


def _table_exists_engine(engine, table_name: str) -> bool:
    with engine.connect() as conn:
        found = conn.execute(text("SHOW TABLES LIKE :t"), {"t": table_name}).fetchone()
    return found is not None


def rollback_import_tables(
    exporter: DataFrameToMySQLWithMetadata,
    batch_id: str,
    table_names: list[str],
) -> None:
    """撤销同一批导入里指定的表，其它表和更早的数据不动。"""
    engine = exporter._create_sqlalchemy_engine()
    try:
        if not _table_exists_engine(engine, UNDO_LOG):
            return
        for row in _undo_rows(engine, batch_id, table_names):
            _restore_undo_row(engine, row)
    finally:
        engine.dispose()


def rollback_last_import(exporter: DataFrameToMySQLWithMetadata | None = None) -> str | None:
    """作废最近一次导入，只恢复这次改过的行或表。"""
    exporter = exporter or DataFrameToMySQLWithMetadata()
    engine = exporter._create_sqlalchemy_engine()
    try:
        if not _table_exists_engine(engine, UNDO_LOG):
            logger.info("没有可撤销的导入")
            return None
        with engine.connect() as conn:
            batch_id = conn.execute(
                text(f"SELECT batch_id FROM {_q(UNDO_LOG)} ORDER BY id DESC LIMIT 1")
            ).scalar()
        if not batch_id:
            logger.info("没有可撤销的导入")
            return None
        rows = _undo_rows(engine, batch_id, None)
        for row in rows:
            _restore_undo_row(engine, row)
        logger.info("已作废导入批次 %s，共 %s 张表", batch_id, len(rows))
        return batch_id
    finally:
        engine.dispose()


def discard_previous_undo(exporter: DataFrameToMySQLWithMetadata, keep_batch_id: str) -> None:
    """本次导入确认保留后，删掉更早批次的撤销快照。当前这一次仍可作废。"""
    engine = exporter._create_sqlalchemy_engine()
    try:
        if not _table_exists_engine(engine, UNDO_LOG):
            return
        with engine.connect() as conn:
            rows = list(conn.execute(
                text(
                    f"SELECT id, undo_table FROM {_q(UNDO_LOG)} "
                    "WHERE batch_id <> :keep"
                ),
                {"keep": keep_batch_id},
            ).mappings())
        for row in rows:
            if row["undo_table"]:
                with engine.begin() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS {_q(row['undo_table'])}"))
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM {_q(UNDO_LOG)} WHERE id = :id"), {"id": row["id"]})
        if rows:
            logger.info("已清理更早的撤销快照 %s 条，保留批次 %s", len(rows), keep_batch_id)
    finally:
        engine.dispose()
